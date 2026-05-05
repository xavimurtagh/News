"""End-to-end pipeline: URLs in, coverage matrix out."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anthropic

from .align import align_claims
from .cache import Cache
from .extract import extract_claims
from .ingest import fetch_article
from .lens import analyze_lens
from .models import (
    Article,
    ArticleLens,
    ConsensusTier,
    CoverageMatrix,
    CoverageStatus,
    OutletCoverage,
    TieredClaim,
)


def _compute_tier(coverage: list[OutletCoverage], n_articles: int) -> ConsensusTier:
    asserted = sum(1 for c in coverage if c.status == CoverageStatus.ASSERTED)
    attributed = sum(1 for c in coverage if c.status == CoverageStatus.ATTRIBUTED)
    contradicted = sum(1 for c in coverage if c.status == CoverageStatus.CONTRADICTED)

    if contradicted > 0:
        return ConsensusTier.DISPUTED
    if asserted == n_articles:
        return ConsensusTier.UNIVERSAL
    if asserted + attributed == 1:
        return ConsensusTier.SINGLE_SOURCED
    if asserted == 0 and attributed > 0:
        return ConsensusTier.ATTRIBUTED_ONLY
    return ConsensusTier.MAJORITY


_TIER_ORDER = {
    ConsensusTier.UNIVERSAL: 0,
    ConsensusTier.MAJORITY: 1,
    ConsensusTier.DISPUTED: 2,
    ConsensusTier.ATTRIBUTED_ONLY: 3,
    ConsensusTier.SINGLE_SOURCED: 4,
}


def run_pipeline(
    urls: list[str],
    cache_dir: Path | None = None,
    api_key: str | None = None,
) -> CoverageMatrix:
    cache = Cache(cache_dir or Path(".cache"))
    client = anthropic.Anthropic(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
    )

    articles: list[Article] = []
    for url in urls:
        print(f"Fetching {url}", file=sys.stderr)
        articles.append(fetch_article(url))

    extractions = {}
    lenses: list[ArticleLens] = []
    for article in articles:
        print(
            f"Analyzing {article.outlet_domain} ({len(article.body)} chars)",
            file=sys.stderr,
        )
        extractions[article.id] = extract_claims(article, client, cache)
        lenses.append(analyze_lens(article, client, cache))
        print(
            f"  -> {len(extractions[article.id].claims)} claims, "
            f"{len(lenses[-1].signals.loaded_terms)} loaded terms",
            file=sys.stderr,
        )

    print(f"Aligning claims across {len(articles)} articles", file=sys.stderr)
    alignment = align_claims(articles, extractions, client, cache)
    print(
        f"  -> {len(alignment.canonical_claims)} canonical claims",
        file=sys.stderr,
    )

    tiered = [
        TieredClaim(
            canonical_text=cc.canonical_text,
            tier=_compute_tier(cc.outlets, len(articles)),
            outlets=cc.outlets,
        )
        for cc in alignment.canonical_claims
    ]
    tiered.sort(key=lambda c: _TIER_ORDER[c.tier])

    return CoverageMatrix(articles=articles, claims=tiered, lenses=lenses)
