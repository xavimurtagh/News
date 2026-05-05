"""End-to-end pipeline: URLs in, coverage matrix out.

Concurrency model:
- All article fetches run in parallel.
- Per article, claim extraction and lens analysis run in parallel.
- Cross-article alignment is sequential (depends on every extraction).

`run_pipeline` is the sync entrypoint and calls asyncio.run on the coroutine,
so callers don't need to know about the event loop.
"""

from __future__ import annotations

import asyncio
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
    ExtractionResult,
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


async def _analyze_article(
    article: Article,
    client: anthropic.AsyncAnthropic,
    cache: Cache,
) -> tuple[ExtractionResult, ArticleLens]:
    print(f"[{article.outlet_domain}] analyzing", file=sys.stderr)
    extraction, lens = await asyncio.gather(
        extract_claims(article, client, cache),
        analyze_lens(article, client, cache),
    )
    print(
        f"[{article.outlet_domain}] {len(extraction.claims)} claims, "
        f"{len(lens.signals.loaded_terms)} loaded terms",
        file=sys.stderr,
    )
    return extraction, lens


async def _run_async(
    urls: list[str],
    client: anthropic.AsyncAnthropic,
    cache: Cache,
) -> CoverageMatrix:
    print(f"Fetching {len(urls)} article(s)", file=sys.stderr)
    articles = list(
        await asyncio.gather(*[fetch_article(url) for url in urls])
    )

    per_article = await asyncio.gather(
        *[_analyze_article(a, client, cache) for a in articles]
    )
    extractions = {
        article.id: extraction
        for article, (extraction, _) in zip(articles, per_article)
    }
    lenses = [lens for _, lens in per_article]

    print(f"Aligning claims across {len(articles)} article(s)", file=sys.stderr)
    alignment = await align_claims(articles, extractions, client, cache)
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


def run_pipeline(
    urls: list[str],
    cache_dir: Path | None = None,
    api_key: str | None = None,
) -> CoverageMatrix:
    cache = Cache(cache_dir or Path(".cache"))
    client = anthropic.AsyncAnthropic(
        api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
    )
    return asyncio.run(_run_async(urls, client, cache))
