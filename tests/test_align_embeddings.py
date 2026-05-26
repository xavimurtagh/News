"""Tests for the embedding-based alignment.

These tests stub out the SentenceTransformer entirely so they don't
depend on a heavyweight ML download. The clustering, medoid pick, and
field-copying logic in align_embeddings.py is what matters here.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

np = pytest.importorskip("numpy")

from news_lens.align_embeddings import align_claims_embeddings
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


def _claim(text: str, claim_type: ClaimType = ClaimType.ASSERTED,
           provenance: Provenance = Provenance.UNCITED,
           attributed_to: str | None = None) -> ExtractedClaim:
    return ExtractedClaim(
        claim_text=text,
        claim_type=claim_type,
        attributed_to=attributed_to,
        source_quote=text,
        provenance=provenance,
        position=1,
    )


class _StubModel:
    """Returns fixed normalized vectors keyed by text. Used to drive clustering."""

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = {}
        for text, vec in vectors.items():
            arr = np.array(vec, dtype=np.float32)
            arr = arr / (np.linalg.norm(arr) + 1e-12)
            self.vectors[text] = arr

    def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
        return np.stack([self.vectors[t] for t in texts])


def _patch_model(stub):
    return patch("news_lens.align_embeddings._load_model", return_value=stub)


def test_embeddings_cluster_similar_claims_across_outlets():
    """Two near-identical claims from two outlets end up in one cluster."""
    articles = [_article("a1", "left.example"), _article("a2", "right.example")]
    extractions = {
        "a1": ExtractionResult(claims=[
            _claim("Minister announced a new tax policy.", provenance=Provenance.NAMED),
        ]),
        "a2": ExtractionResult(claims=[
            _claim("A new tax policy was announced by the minister.",
                   ClaimType.ATTRIBUTED, provenance=Provenance.NAMED),
        ]),
    }
    stub = _StubModel({
        "Minister announced a new tax policy.": [1.0, 0.05],
        "A new tax policy was announced by the minister.": [0.98, 0.02],
    })

    with _patch_model(stub):
        result = align_claims_embeddings(articles, extractions, threshold=0.6)

    assert len(result.canonical_claims) == 1
    cc = result.canonical_claims[0]
    by_id = {oc.article_id: oc for oc in cc.outlets}
    assert by_id["a1"].status == CoverageStatus.ASSERTED
    assert by_id["a2"].status == CoverageStatus.ATTRIBUTED
    # Source quotes, attributions, provenance are copied verbatim.
    assert by_id["a1"].source_quote == "Minister announced a new tax policy."
    assert by_id["a2"].provenance == Provenance.NAMED


def test_embeddings_keep_distinct_topics_separate():
    """Unrelated claims become separate canonical claims, others OMITTED."""
    articles = [_article("a1", "left.example"), _article("a2", "right.example")]
    extractions = {
        "a1": ExtractionResult(claims=[_claim("Sky is blue.")]),
        "a2": ExtractionResult(claims=[_claim("Sports team wins championship.")]),
    }
    stub = _StubModel({
        "Sky is blue.": [1.0, 0.0],
        "Sports team wins championship.": [0.0, 1.0],
    })

    with _patch_model(stub):
        result = align_claims_embeddings(articles, extractions, threshold=0.5)

    assert len(result.canonical_claims) == 2
    by_text = {cc.canonical_text: cc for cc in result.canonical_claims}
    sky_by_id = {oc.article_id: oc.status for oc in by_text["Sky is blue."].outlets}
    assert sky_by_id == {
        "a1": CoverageStatus.ASSERTED, "a2": CoverageStatus.OMITTED,
    }
    sports_by_id = {oc.article_id: oc.status for oc in by_text["Sports team wins championship."].outlets}
    assert sports_by_id == {
        "a1": CoverageStatus.OMITTED, "a2": CoverageStatus.ASSERTED,
    }


def test_embeddings_no_hallucinated_outlets():
    """The embedding path can only emit outlet_domains that exist in `articles`."""
    articles = [_article("a1", "real-outlet.com")]
    extractions = {"a1": ExtractionResult(claims=[_claim("Hello.")])}
    stub = _StubModel({"Hello.": [1.0]})

    with _patch_model(stub):
        result = align_claims_embeddings(articles, extractions)

    all_domains = {oc.outlet_domain for cc in result.canonical_claims for oc in cc.outlets}
    assert all_domains == {"real-outlet.com"}


def test_embeddings_medoid_picks_central_claim_text():
    """Among three similar claims, the canonical_text is the one closest to centroid."""
    articles = [
        _article("a1", "x.example"),
        _article("a2", "y.example"),
        _article("a3", "z.example"),
    ]
    extractions = {
        "a1": ExtractionResult(claims=[_claim("Edge phrasing A.")]),
        "a2": ExtractionResult(claims=[_claim("Central phrasing.")]),
        "a3": ExtractionResult(claims=[_claim("Edge phrasing B.")]),
    }
    # a2's vector sits between a1 and a3 -> closest to centroid.
    stub = _StubModel({
        "Edge phrasing A.": [1.0, 0.1],
        "Central phrasing.": [1.0, 0.0],
        "Edge phrasing B.": [1.0, -0.1],
    })

    with _patch_model(stub):
        result = align_claims_embeddings(articles, extractions, threshold=0.7)

    assert len(result.canonical_claims) == 1
    assert result.canonical_claims[0].canonical_text == "Central phrasing."


def test_embeddings_empty_extractions_returns_empty():
    articles = [_article("a1", "x.example")]
    extractions = {"a1": ExtractionResult(claims=[])}
    with _patch_model(_StubModel({})):
        result = align_claims_embeddings(articles, extractions)
    assert result.canonical_claims == []
