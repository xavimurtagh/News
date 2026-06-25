"""Tests for the headline-divergence module.

Stubs out the SentenceTransformer entirely so the cosine arithmetic and
the centroid logic can be exercised without a heavyweight ML download.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

np = pytest.importorskip("numpy")

from news_lens.headline_divergence import compute_headline_divergence
from news_lens.models import Article


def _article(article_id: str, title: str) -> Article:
    return Article(
        id=article_id,
        url=f"https://example.test/{article_id}",
        outlet_domain="example.test",
        title=title,
        fetched_at=datetime(2026, 5, 28),
        body="b",
        paragraph_count=2,
    )


class _StubModel:
    """Returns fixed normalized vectors keyed by title."""

    def __init__(self, vectors: dict[str, list[float]]):
        self.vectors = {}
        for text, vec in vectors.items():
            arr = np.array(vec, dtype=np.float32)
            arr = arr / (np.linalg.norm(arr) + 1e-12)
            self.vectors[text] = arr

    def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
        return np.stack([self.vectors[t] for t in texts])


def _patch(stub: _StubModel):
    return [
        patch("news_lens.align_embeddings.is_available", return_value=True),
        patch("news_lens.align_embeddings._load_model", return_value=stub),
    ]


def test_compute_divergence_returns_empty_for_one_article():
    """A single article has no centroid to compare to."""
    result = compute_headline_divergence([_article("a1", "hello")])
    assert result == []


def test_compute_divergence_ranks_outlier_highest():
    """Three near-identical headlines and one outlier — outlier ranks first."""
    arts = [
        _article("a1", "Minister announces tax reform"),
        _article("a2", "Tax reform announced by minister"),
        _article("a3", "Minister sets out tax overhaul"),
        _article("a4", "Football team wins championship"),  # off-topic
    ]
    stub = _StubModel({
        "Minister announces tax reform": [1.0, 0.05],
        "Tax reform announced by minister": [0.98, 0.05],
        "Minister sets out tax overhaul": [0.97, 0.05],
        "Football team wins championship": [0.0, 1.0],
    })
    with _patch(stub)[0], _patch(stub)[1]:
        result = compute_headline_divergence(arts)

    assert len(result) == 4
    # The outlier sits at the top with a high divergence score.
    assert result[0].article_id == "a4"
    assert result[0].divergence_score > 0.4
    # The three on-topic titles all score lower than the outlier.
    for r in result[1:]:
        assert r.divergence_score < result[0].divergence_score


def test_compute_divergence_returns_empty_when_embeddings_unavailable():
    """No sentence-transformers → no divergence; the section gets skipped."""
    arts = [_article("a1", "t1"), _article("a2", "t2")]
    with patch("news_lens.align_embeddings.is_available", return_value=False):
        result = compute_headline_divergence(arts)
    assert result == []


def test_compute_divergence_handles_empty_titles():
    """All-empty titles → empty list (no signal)."""
    arts = [_article("a1", ""), _article("a2", "")]
    stub = _StubModel({})
    with _patch(stub)[0], _patch(stub)[1]:
        result = compute_headline_divergence(arts)
    assert result == []


def test_compute_divergence_results_are_sorted_descending():
    """The renderer assumes desc-sort; the function guarantees it."""
    arts = [
        _article("a1", "Centre"),
        _article("a2", "Edge A"),
        _article("a3", "Edge B"),
    ]
    stub = _StubModel({
        "Centre": [1.0, 0.0],
        "Edge A": [0.7, 0.7],
        "Edge B": [0.7, -0.7],
    })
    with _patch(stub)[0], _patch(stub)[1]:
        result = compute_headline_divergence(arts)

    scores = [r.divergence_score for r in result]
    assert scores == sorted(scores, reverse=True)
    # The "Centre" article is closest to the centroid (with two
    # symmetric outliers), so it should score lowest.
    by_id = {r.article_id: r.divergence_score for r in result}
    assert by_id["a1"] < by_id["a2"]
    assert by_id["a1"] < by_id["a3"]
