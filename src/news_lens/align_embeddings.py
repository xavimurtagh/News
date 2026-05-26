"""Embedding-based cross-article alignment.

Replaces the LLM-based alignment that produced empty `outlets` lists and
hallucinated outlet_domains on weak local models. Embeds every
ExtractedClaim with a SentenceTransformer, builds pairwise cosine
similarity over normalized vectors, clusters by union-find above a
threshold, and emits one CanonicalClaim per cluster.

Every field on each OutletCoverage is copied verbatim from the
originating ExtractedClaim — no LLM, no field invented. The
canonical_text for each cluster is the medoid claim (the one closest to
the cluster centroid), so it is a real claim from the corpus rather
than a synthesised "neutral" phrasing.

This module is optional. `is_available()` reports whether the
dependency is installed. The dispatcher in align.py uses it when
available and falls back to the LLM path otherwise.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Mapping

from .models import (
    AlignmentResult,
    Article,
    CanonicalClaim,
    ClaimType,
    CoverageStatus,
    ExtractionResult,
    OutletCoverage,
)

if TYPE_CHECKING:
    from .models import ExtractedClaim


DEFAULT_MODEL = "sentence-transformers/all-mpnet-base-v2"
DEFAULT_THRESHOLD = 0.65


_MODEL_CACHE: dict = {}


def is_available() -> bool:
    """True iff sentence-transformers can be imported."""
    try:
        import sentence_transformers  # noqa: F401

        return True
    except ImportError:
        return False


def _load_model(name: str):
    """Cache the model so repeated calls in one process pay the load cost once."""
    if name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer

        print(
            f"Loading embedding model {name!r} (first call downloads ~420MB)...",
            file=sys.stderr,
        )
        _MODEL_CACHE[name] = SentenceTransformer(name)
    return _MODEL_CACHE[name]


def align_claims_embeddings(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
    *,
    model_name: str = DEFAULT_MODEL,
    threshold: float = DEFAULT_THRESHOLD,
) -> AlignmentResult:
    """Cluster extracted claims across articles into canonical claims.

    Each cluster becomes one CanonicalClaim. Within a cluster, every
    article that contributed at least one claim gets an
    ASSERTED/ATTRIBUTED OutletCoverage (status copied from the
    underlying ExtractedClaim's claim_type); articles that didn't
    contribute are OMITTED. All citation fields (source_quote,
    attributed_to, position, provenance) are copied verbatim from the
    originating ExtractedClaim.
    """
    import numpy as np

    flat: list[tuple[Article, "ExtractedClaim"]] = []
    for article in articles:
        for claim in extractions[article.id].claims:
            flat.append((article, claim))

    if not flat:
        return AlignmentResult(canonical_claims=[])

    model = _load_model(model_name)
    texts = [claim.claim_text for _, claim in flat]
    embeddings = model.encode(
        texts, convert_to_numpy=True, normalize_embeddings=True
    )

    n = len(flat)
    # Cosine similarity on normalized vectors = dot product.
    sim = embeddings @ embeddings.T

    # Union-find over edges with cosine >= threshold.
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    article_ids = [a.id for a in articles]
    article_to_outlet = {a.id: a.outlet_domain for a in articles}

    canonical_claims: list[CanonicalClaim] = []
    for members in clusters.values():
        if len(members) == 1:
            medoid_idx = members[0]
        else:
            cluster_vecs = embeddings[members]
            centroid = cluster_vecs.mean(axis=0)
            norm = float(np.linalg.norm(centroid))
            if norm < 1e-12:
                medoid_idx = members[0]
            else:
                centroid_unit = centroid / norm
                scores = cluster_vecs @ centroid_unit
                medoid_idx = members[int(np.argmax(scores))]

        canonical_text = flat[medoid_idx][1].claim_text

        # Per-article best representative — closest to the medoid. An
        # article can contribute multiple claims to one cluster; we only
        # want one OutletCoverage per (claim, article) pair.
        per_article: dict[str, tuple[int, float]] = {}
        for m in members:
            article = flat[m][0]
            score = float(embeddings[m] @ embeddings[medoid_idx])
            existing = per_article.get(article.id)
            if existing is None or score > existing[1]:
                per_article[article.id] = (m, score)

        outlets: list[OutletCoverage] = []
        for aid in article_ids:
            entry = per_article.get(aid)
            if entry is None:
                outlets.append(
                    OutletCoverage(
                        outlet_domain=article_to_outlet[aid],
                        article_id=aid,
                        status=CoverageStatus.OMITTED,
                    )
                )
                continue
            m_idx, _ = entry
            claim = flat[m_idx][1]
            status = (
                CoverageStatus.ATTRIBUTED
                if claim.claim_type == ClaimType.ATTRIBUTED
                else CoverageStatus.ASSERTED
            )
            outlets.append(
                OutletCoverage(
                    outlet_domain=article_to_outlet[aid],
                    article_id=aid,
                    status=status,
                    source_quote=claim.source_quote,
                    attributed_to=claim.attributed_to,
                    provenance=claim.provenance,
                    position=claim.position,
                )
            )

        canonical_claims.append(
            CanonicalClaim(canonical_text=canonical_text, outlets=outlets)
        )

    return AlignmentResult(canonical_claims=canonical_claims)
