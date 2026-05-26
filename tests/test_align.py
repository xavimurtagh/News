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


def _alignment_result_class():
    from news_lens.models import AlignmentResult
    return AlignmentResult


class _LLM:
    """Mock backend that returns whatever AlignmentResult we hand it."""

    def __init__(self, result):
        self.result = result
        self.name = "mock-llm"

    async def parse(self, *, system, user, schema):
        return self.result


def test_align_drops_hallucinated_outlet_domains(tmp_path: Path, capsys):
    """LLM-invented outlet_domain values that don't match any article are dropped.

    The matching extracted claim is then re-attached by similarity
    recovery — that's the intended behavior. We assert on the warning
    and on the absence of the hallucinated domain in the output, plus
    that an unrelated article still gets OMITTED.
    """
    from news_lens.models import (
        AlignmentResult,
        CanonicalClaim as _CC,
        OutletCoverage as _OC,
    )

    articles = [
        _article("a1", "real-outlet.com"),
        _article("a2", "second.example"),
    ]
    extractions = {
        "a1": ExtractionResult(claims=[_claim("X happened.")]),
        "a2": ExtractionResult(claims=[_claim("Totally unrelated topic.")]),
    }

    fake = AlignmentResult(canonical_claims=[
        _CC(
            canonical_text="X happened.",
            outlets=[
                _OC(outlet_domain="example.com", article_id="a1",
                    status=CoverageStatus.ASSERTED),
            ],
        )
    ])

    result = asyncio.run(
        align_claims(articles, extractions, _LLM(fake), Cache(tmp_path))
    )

    err = capsys.readouterr().err
    assert "hallucinated outlet_domain" in err

    cc = result.canonical_claims[0]
    assert all(oc.outlet_domain != "example.com" for oc in cc.outlets)
    by_id = {oc.article_id: oc for oc in cc.outlets}
    assert by_id["a2"].status == CoverageStatus.OMITTED


def test_align_drops_hallucinated_article_ids(tmp_path: Path, capsys):
    """LLM-invented article_id values are dropped, with a warning."""
    from news_lens.models import (
        AlignmentResult,
        CanonicalClaim as _CC,
        OutletCoverage as _OC,
    )

    articles = [
        _article("a1", "real-outlet.com"),
        _article("a2", "second.example"),
    ]
    extractions = {
        "a1": ExtractionResult(claims=[_claim("X happened.")]),
        "a2": ExtractionResult(claims=[_claim("Totally unrelated topic.")]),
    }

    fake = AlignmentResult(canonical_claims=[
        _CC(
            canonical_text="X happened.",
            outlets=[
                _OC(outlet_domain="real-outlet.com", article_id="ghost-id",
                    status=CoverageStatus.ASSERTED),
            ],
        )
    ])

    result = asyncio.run(
        align_claims(articles, extractions, _LLM(fake), Cache(tmp_path))
    )

    err = capsys.readouterr().err
    assert "hallucinated article_id" in err
    cc = result.canonical_claims[0]
    assert all(oc.article_id != "ghost-id" for oc in cc.outlets)


def test_align_repairs_mismatched_domain_for_real_article(tmp_path: Path):
    """If the LLM names the wrong domain for a real article_id, trust the id."""
    from news_lens.models import (
        AlignmentResult,
        CanonicalClaim as _CC,
        OutletCoverage as _OC,
    )

    articles = [
        _article("a1", "left.example"),
        _article("a2", "right.example"),
    ]
    extractions = {
        "a1": ExtractionResult(claims=[_claim("X.")]),
        "a2": ExtractionResult(claims=[_claim("X.")]),
    }

    # LLM names a1 but with a2's domain — repair by trusting article_id.
    fake = AlignmentResult(canonical_claims=[
        _CC(
            canonical_text="X.",
            outlets=[
                _OC(outlet_domain="right.example", article_id="a1",
                    status=CoverageStatus.ASSERTED),
            ],
        )
    ])

    result = asyncio.run(
        align_claims(articles, extractions, _LLM(fake), Cache(tmp_path))
    )
    by_id = {oc.article_id: oc for oc in result.canonical_claims[0].outlets}
    assert by_id["a1"].outlet_domain == "left.example"
    assert by_id["a1"].status == CoverageStatus.ASSERTED


def test_align_recovers_outlets_when_llm_returns_empty(tmp_path: Path, capsys):
    """If LLM returns canonical_text with outlets=[], fuzzy-match recovers them."""
    from news_lens.models import (
        AlignmentResult,
        CanonicalClaim as _CC,
    )

    articles = [
        _article("a1", "left.example"),
        _article("a2", "right.example"),
    ]
    extractions = {
        "a1": ExtractionResult(claims=[
            _claim("The minister announced new policy today.",
                   provenance=Provenance.NAMED),
        ]),
        "a2": ExtractionResult(claims=[
            _claim("Today the minister announced a new policy.",
                   ClaimType.ATTRIBUTED, provenance=Provenance.NAMED),
        ]),
    }

    fake = AlignmentResult(canonical_claims=[
        _CC(
            canonical_text="The minister announced new policy today.",
            outlets=[],
        )
    ])

    result = asyncio.run(
        align_claims(articles, extractions, _LLM(fake), Cache(tmp_path))
    )

    err = capsys.readouterr().err
    assert "recovered" in err

    cc = result.canonical_claims[0]
    by_id = {oc.article_id: oc for oc in cc.outlets}
    # a1's claim is a near-identical match -> ASSERTED with quote preserved.
    assert by_id["a1"].status == CoverageStatus.ASSERTED
    assert by_id["a1"].source_quote == "The minister announced new policy today."
    # a2's matching claim is ATTRIBUTED, so the recovered status reflects that.
    assert by_id["a2"].status == CoverageStatus.ATTRIBUTED


def test_align_recovery_skips_articles_with_no_similar_claim(tmp_path: Path):
    """Articles whose claims don't match the canonical_text stay OMITTED."""
    from news_lens.models import (
        AlignmentResult,
        CanonicalClaim as _CC,
    )

    articles = [
        _article("a1", "left.example"),
        _article("a2", "right.example"),
    ]
    extractions = {
        "a1": ExtractionResult(claims=[_claim("The minister announced new policy.")]),
        # a2's only claim is about something totally different.
        "a2": ExtractionResult(claims=[_claim("Sports league signs broadcast deal.")]),
    }

    fake = AlignmentResult(canonical_claims=[
        _CC(canonical_text="The minister announced new policy.", outlets=[])
    ])

    result = asyncio.run(
        align_claims(articles, extractions, _LLM(fake), Cache(tmp_path))
    )
    by_id = {oc.article_id: oc for oc in result.canonical_claims[0].outlets}
    assert by_id["a1"].status == CoverageStatus.ASSERTED
    assert by_id["a2"].status == CoverageStatus.OMITTED
