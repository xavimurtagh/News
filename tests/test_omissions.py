"""Tests for the structural-omissions LLM pass."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from news_lens.cache import Cache
from news_lens.models import (
    AlignmentResult,
    Article,
    ArticleLens,
    CanonicalClaim,
    ClaimType,
    CoverageStatus,
    ExtractedClaim,
    ExtractionResult,
    HeadlineFraming,
    LensSignals,
    OmissionAnalysis,
    OmissionCategory,
    OutletCoverage,
    Provenance,
    StructuralOmission,
)
from news_lens.omissions import analyze_omissions


def _article(article_id: str, outlet: str, title: str = "story") -> Article:
    return Article(
        id=article_id, url=f"https://{outlet}/{article_id}",
        outlet_domain=outlet, title=title,
        fetched_at=datetime(2026, 5, 28),
        body="b", paragraph_count=2,
    )


def _claim_text(text: str) -> ExtractedClaim:
    return ExtractedClaim(
        claim_text=text, claim_type=ClaimType.ASSERTED,
        source_quote=text, provenance=Provenance.UNCITED, position=1,
    )


def _lens(article_id: str, outlet: str, sources: list[str]) -> ArticleLens:
    return ArticleLens(
        article_id=article_id, outlet_domain=outlet,
        signals=LensSignals(
            headline_framing=HeadlineFraming.NEUTRAL,
            loaded_terms=[], framing_devices=[],
            sources_quoted=sources, stance_summary="s",
        ),
    )


class _LLM:
    name = "mock-llm"

    def __init__(self, response: OmissionAnalysis):
        self.response = response
        self.calls: list[dict] = []

    async def parse(self, *, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        return self.response


class _BrokenLLM:
    name = "mock-broken"

    async def parse(self, *, system, user, schema):
        raise RuntimeError("validation failed")


def test_analyze_omissions_returns_llm_result(tmp_path: Path):
    articles = [
        _article("a1", "left.example"),
        _article("a2", "right.example"),
        _article("a3", "centre.example"),
    ]
    extractions = {a.id: ExtractionResult(claims=[_claim_text("X.")]) for a in articles}
    alignment = AlignmentResult(canonical_claims=[
        CanonicalClaim(canonical_text="X.", outlets=[]),
    ])
    lenses = [_lens("a1", "left.example", ["Government spokesperson"])]

    response = OmissionAnalysis(omissions=[
        StructuralOmission(
            category=OmissionCategory.PERSPECTIVE,
            description="No frontline worker interviewed.",
            why_relevant="A labour story without labour voices is incomplete.",
        ),
    ])

    llm = _LLM(response)
    result = asyncio.run(
        analyze_omissions(articles, extractions, alignment, lenses, llm, Cache(tmp_path))
    )
    assert len(result.omissions) == 1
    assert result.omissions[0].category == OmissionCategory.PERSPECTIVE
    assert "labour" in result.omissions[0].why_relevant
    assert len(llm.calls) == 1


def test_analyze_omissions_skips_when_too_few_outlets(tmp_path: Path):
    """A 2-outlet sample is too small; analysis skipped with an honest caveat."""
    articles = [
        _article("a1", "left.example"),
        _article("a2", "right.example"),
    ]
    extractions = {a.id: ExtractionResult(claims=[]) for a in articles}
    alignment = AlignmentResult(canonical_claims=[])
    llm = _LLM(OmissionAnalysis(omissions=[]))
    result = asyncio.run(
        analyze_omissions(articles, extractions, alignment, [], llm, Cache(tmp_path))
    )
    assert result.omissions == []
    assert "skipped" in (result.sample_caveat or "")
    # LLM was never called.
    assert llm.calls == []


def test_analyze_omissions_survives_llm_failure(tmp_path: Path, capsys):
    """If the LLM call fails, the result is empty + a caveat. The pipeline keeps going."""
    articles = [
        _article(f"a{i}", f"o{i}.example") for i in range(3)
    ]
    extractions = {a.id: ExtractionResult(claims=[]) for a in articles}
    alignment = AlignmentResult(canonical_claims=[])

    result = asyncio.run(
        analyze_omissions(articles, extractions, alignment, [], _BrokenLLM(), Cache(tmp_path))
    )
    assert result.omissions == []
    assert result.sample_caveat is not None
    err = capsys.readouterr().err
    assert "omissions analysis failed" in err


def test_analyze_omissions_caches_results(tmp_path: Path):
    """Two identical calls hit the cache; the LLM only runs once."""
    articles = [_article(f"a{i}", f"o{i}.example") for i in range(3)]
    extractions = {a.id: ExtractionResult(claims=[]) for a in articles}
    alignment = AlignmentResult(canonical_claims=[])
    response = OmissionAnalysis(omissions=[
        StructuralOmission(
            category=OmissionCategory.CONTEXT,
            description="d", why_relevant="w",
        ),
    ])
    llm = _LLM(response)
    cache = Cache(tmp_path)
    asyncio.run(analyze_omissions(articles, extractions, alignment, [], llm, cache))
    asyncio.run(analyze_omissions(articles, extractions, alignment, [], llm, cache))
    assert len(llm.calls) == 1
