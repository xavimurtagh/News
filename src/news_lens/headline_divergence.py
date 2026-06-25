"""Headline-divergence scoring: which outlet phrased the lead most unlike its peers.

A small but valuable Manufacturing-Consent-style signal that reuses
the sentence-transformers model already loaded for claim alignment and
title clustering. Each article's headline is embedded with MPNet; the
centroid of the sample is taken; each article scores
`1 - cosine(title, centroid)`. The top-3 most divergent titles are the
outlets most idiosyncratically framing the lead — at a glance, you can
see which paper's headline broke from the pack.

If sentence-transformers isn't installed, the pipeline calls
`is_available()` and skips the step. The returned list is sorted by
score descending so the renderer can take the top-N directly.
"""

from __future__ import annotations

import sys

from .models import Article, HeadlineDivergence


def is_available() -> bool:
    """True iff sentence-transformers can be imported (same gate as alignment)."""
    from . import align_embeddings

    return align_embeddings.is_available()


def compute_headline_divergence(
    articles: list[Article],
    *,
    model_name: str | None = None,
) -> list[HeadlineDivergence]:
    """Score each article by how unlike its headline is from the sample mean.

    Returns an empty list when:
      - fewer than 2 articles (no centroid to compare to),
      - sentence-transformers is unavailable,
      - all titles are empty/missing.

    Sorted descending by `divergence_score`.
    """
    if len(articles) < 2 or not is_available():
        return []

    from . import align_embeddings

    titles = [(a.title or "").strip() for a in articles]
    if not any(titles):
        return []

    try:
        import numpy as np

        model = align_embeddings._load_model(
            model_name or align_embeddings.DEFAULT_MODEL
        )
        embeddings = model.encode(
            titles, convert_to_numpy=True, normalize_embeddings=True
        )
    except Exception as exc:
        print(
            f"WARN: headline divergence skipped ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return []

    centroid = embeddings.mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm < 1e-12:
        return []
    centroid_unit = centroid / norm

    scores = embeddings @ centroid_unit
    rows = [
        HeadlineDivergence(
            article_id=a.id,
            divergence_score=float(max(0.0, 1.0 - sim)),
        )
        for a, sim in zip(articles, scores)
    ]
    rows.sort(key=lambda r: r.divergence_score, reverse=True)
    return rows
