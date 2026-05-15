"""Tests for the alignment stage, focused on the LLM-failure fallback."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from news_lens.align import align_claims
from news_lens.cache import Cache
from news_lens.models import (
    Article,
    ClaimType,
    CoverageStatus,
    ExtractedClaim,
    ExtractionResult,
    Provenance,
)


def _article(article_id: str, outlet: str) -> Article:
    return Article(
        id=article_id,
        url=f"https://{outlet}/{article_id}",
        outlet_domain=outlet,
        title=f"{outlet} story",
        fetched_at=datetime(2026, 5, 14),
        body="body",
        paragraph_count=1,
    )


def _claim(
    text: str,
    claim_type: ClaimType = ClaimType.ASSERTED,
    provenance: Provenance = Provenance.UNCITED,
) -> ExtractedClaim:
    return ExtractedClaim(
        claim_text=text,
        claim_type=claim_type,
        source_quote=text,
        provenance=provenance,
        position=1,
    )


class _BrokenLLM:
    name = "broken"

    async def parse(self, *, system, user, schema):  # noqa: ANN001 - duck-typed
        raise RuntimeError("model returned the JSON schema instead of an instance")


def test_align_claims_falls_back_when_llm_fails(tmp_path: Path, capsys):
    articles = [_article("a1", "left.example"), _article("a2", "right.example")]
    extractions = {
        "a1": ExtractionResult(
            claims=[_claim("Sky is blue.", provenance=Provenance.PRIMARY)]
        ),
        "a2": ExtractionResult(
            claims=[
                _claim(
                    "Tax was raised.",
                    ClaimType.ATTRIBUTED,
                    provenance=Provenance.NAMED,
                )
            ]
        ),
    }

    result = asyncio.run(
        align_claims(articles, extractions, _BrokenLLM(), Cache(tmp_path))
    )

    captured = capsys.readouterr()
    assert "alignment LLM call failed" in captured.err

    # Two canonical claims (one per input claim), each carrying one
    # asserting/attributing outlet plus an omitted entry for the other.
    assert len(result.canonical_claims) == 2

    by_text = {cc.canonical_text: cc for cc in result.canonical_claims}
    sky = by_text["Sky is blue."]
    sky_statuses = {oc.article_id: oc.status for oc in sky.outlets}
    assert sky_statuses == {
        "a1": CoverageStatus.ASSERTED,
        "a2": CoverageStatus.OMITTED,
    }

    tax = by_text["Tax was raised."]
    tax_statuses = {oc.article_id: oc.status for oc in tax.outlets}
    assert tax_statuses == {
        "a1": CoverageStatus.OMITTED,
        "a2": CoverageStatus.ATTRIBUTED,
    }

    # The fallback must carry provenance through from the extracted claim.
    sky_prov = {oc.article_id: oc.provenance for oc in sky.outlets}
    assert sky_prov == {"a1": Provenance.PRIMARY, "a2": None}
    tax_prov = {oc.article_id: oc.provenance for oc in tax.outlets}
    assert tax_prov == {"a1": None, "a2": Provenance.NAMED}


def test_align_claims_fallback_handles_empty_extractions(tmp_path: Path):
    articles = [_article("a1", "left.example")]
    extractions = {"a1": ExtractionResult(claims=[])}

    result = asyncio.run(
        align_claims(articles, extractions, _BrokenLLM(), Cache(tmp_path))
    )
    assert result.canonical_claims == []
