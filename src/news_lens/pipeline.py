"""End-to-end pipeline: URLs in, coverage matrix out.

Concurrency model:
- All article fetches run in parallel.
- Per article, claim extraction and lens analysis run in parallel.
- Cross-article alignment is sequential (depends on every extraction).

The LLM is provided as a `StructuredLLM` backend (Claude / local Llama /
etc.) — the pipeline doesn't care which. See backends/.

`run_pipeline` is the sync entrypoint and calls asyncio.run on the
coroutine, so callers don't need to know about the event loop.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from .align import align_claims
from .backends.base import StructuredLLM
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
    GroundingFlag,
    OutletCoverage,
    Provenance,
    SyndicationGroup,
    TieredClaim,
)
from .syndication import detect_syndication


_STATUS_PRIORITY = {
    CoverageStatus.CONTRADICTED: 3,
    CoverageStatus.ASSERTED: 2,
    CoverageStatus.ATTRIBUTED: 1,
    CoverageStatus.OMITTED: 0,
}


def _collapse_syndication(
    coverage: list[OutletCoverage],
    n_articles: int,
    syndication_groups: list[SyndicationGroup] | None,
) -> tuple[list[OutletCoverage], int]:
    """Treat syndicated outlets as one voice for tier purposes.

    Three outlets running the same wire copy aren't three independent
    assertions. This collapses each syndication group's coverage entries to
    one representative — the strongest non-omitted status, with
    contradiction beating assertion (an outlet that edited a wire to
    disagree is meaningful news).
    """
    if not syndication_groups:
        return coverage, n_articles

    rep_of: dict[str, str] = {}
    for group in syndication_groups:
        rep = group.article_ids[0]
        for aid in group.article_ids:
            rep_of[aid] = rep

    by_rep: dict[str, OutletCoverage] = {}
    for c in coverage:
        rep = rep_of.get(c.article_id, c.article_id)
        existing = by_rep.get(rep)
        if existing is None or _STATUS_PRIORITY[c.status] > _STATUS_PRIORITY[existing.status]:
            by_rep[rep] = c

    n_voices = n_articles - sum(len(g.article_ids) - 1 for g in syndication_groups)
    return list(by_rep.values()), n_voices


def _compute_tier(
    coverage: list[OutletCoverage],
    n_articles: int,
    syndication_groups: list[SyndicationGroup] | None = None,
) -> ConsensusTier:
    coverage_, n_voices = _collapse_syndication(coverage, n_articles, syndication_groups)

    asserted = sum(1 for c in coverage_ if c.status == CoverageStatus.ASSERTED)
    attributed = sum(1 for c in coverage_ if c.status == CoverageStatus.ATTRIBUTED)
    contradicted = sum(1 for c in coverage_ if c.status == CoverageStatus.CONTRADICTED)

    if contradicted > 0:
        return ConsensusTier.DISPUTED
    if asserted == n_voices:
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

_CARRYING_STATUSES = (
    CoverageStatus.ASSERTED,
    CoverageStatus.ATTRIBUTED,
    CoverageStatus.CONTRADICTED,
)


def _compute_grounding(coverage: list[OutletCoverage]) -> GroundingFlag:
    """Classify how well-grounded and how independent a canonical claim is.

    Reads the provenance each outlet attached to its version of the
    claim:
    - THINLY_SOURCED — no outlet ties the claim to a primary document or
      a named, on-the-record source. The whole consensus rests on
      anonymous sources, other media, or bare assertion.
    - SINGLE_ORIGIN — two or more outlets carry the claim, but every one
      attributes it to the same named source. The apparent agreement is
      one source echoed, not independent confirmation — a key way thin
      or false claims pick up a veneer of consensus.
    - WELL_GROUNDED — at least one outlet ties it to a primary document
      or a named source, and it is not single-origin.

    Grounding is independent of ConsensusTier on purpose: a claim every
    outlet repeats can still be thinly sourced or single-origin.
    """
    carrying = [c for c in coverage if c.status in _CARRYING_STATUSES]
    if not carrying:
        return GroundingFlag.THINLY_SOURCED

    has_primary = any(c.provenance == Provenance.PRIMARY for c in carrying)
    named_sources = {
        c.attributed_to.strip().lower()
        for c in carrying
        if c.provenance == Provenance.NAMED and c.attributed_to
    }

    if not has_primary and not named_sources:
        return GroundingFlag.THINLY_SOURCED
    if (
        len(carrying) >= 2
        and not has_primary
        and len(named_sources) == 1
        and all(c.provenance == Provenance.NAMED for c in carrying)
    ):
        return GroundingFlag.SINGLE_ORIGIN
    return GroundingFlag.WELL_GROUNDED


def _partition_results(
    items: list,
    results: list,
    label_fn=str,
) -> tuple[list, list]:
    """Drop exceptions from an asyncio.gather(return_exceptions=True) result.

    Returns (surviving_items, surviving_results) where the two lists stay
    aligned. Failed items get a warning line on stderr keyed off label_fn.
    """
    keep_items = []
    keep_results = []
    for item, result in zip(items, results):
        if isinstance(result, BaseException):
            print(f"WARN: skipping {label_fn(item)}: {result}", file=sys.stderr)
            continue
        keep_items.append(item)
        keep_results.append(result)
    return keep_items, keep_results


async def _analyze_article(
    article: Article,
    llm: StructuredLLM,
    cache: Cache,
) -> tuple[ExtractionResult, ArticleLens]:
    print(f"[{article.outlet_domain}] analyzing", file=sys.stderr)
    extraction, lens = await asyncio.gather(
        extract_claims(article, llm, cache),
        analyze_lens(article, llm, cache),
    )
    print(
        f"[{article.outlet_domain}] {len(extraction.claims)} claims, "
        f"{len(lens.signals.loaded_terms)} loaded terms",
        file=sys.stderr,
    )
    return extraction, lens


async def _run_async(
    urls: list[str],
    llm: StructuredLLM,
    cache: Cache,
) -> CoverageMatrix:
    print(f"Fetching {len(urls)} article(s)", file=sys.stderr)
    fetch_results = await asyncio.gather(
        *[fetch_article(url) for url in urls],
        return_exceptions=True,
    )
    _, articles = _partition_results(urls, fetch_results, label_fn=lambda u: u)
    if not articles:
        raise RuntimeError("All article fetches failed; nothing to analyze.")

    analysis_results = await asyncio.gather(
        *[_analyze_article(a, llm, cache) for a in articles],
        return_exceptions=True,
    )
    surviving, ext_lens_pairs = _partition_results(
        articles,
        analysis_results,
        label_fn=lambda a: f"analysis of {a.outlet_domain}",
    )
    articles = surviving
    if not articles:
        raise RuntimeError("All article analyses failed; nothing to align.")

    extractions: dict[str, ExtractionResult] = {
        article.id: extraction
        for article, (extraction, _) in zip(articles, ext_lens_pairs)
    }
    lenses: list[ArticleLens] = [lens for _, lens in ext_lens_pairs]

    syndication_groups = detect_syndication(articles)
    if syndication_groups:
        print(
            f"Detected {len(syndication_groups)} syndication group(s)",
            file=sys.stderr,
        )

    print(f"Aligning claims across {len(articles)} article(s)", file=sys.stderr)
    alignment = await align_claims(articles, extractions, llm, cache)
    print(
        f"  -> {len(alignment.canonical_claims)} canonical claims",
        file=sys.stderr,
    )

    tiered = [
        TieredClaim(
            canonical_text=cc.canonical_text,
            tier=_compute_tier(cc.outlets, len(articles), syndication_groups),
            grounding=_compute_grounding(cc.outlets),
            outlets=cc.outlets,
        )
        for cc in alignment.canonical_claims
    ]
    tiered.sort(key=lambda c: _TIER_ORDER[c.tier])

    return CoverageMatrix(
        articles=articles,
        claims=tiered,
        lenses=lenses,
        syndication_groups=syndication_groups,
    )


def run_pipeline(
    urls: list[str],
    backend: StructuredLLM | None = None,
    cache_dir: Path | None = None,
    api_key: str | None = None,
) -> CoverageMatrix:
    """Run the pipeline end-to-end.

    `backend` is any StructuredLLM (see news_lens.backends). If None,
    constructs a ClaudeBackend using ANTHROPIC_API_KEY (compatible with
    the original behavior).
    """
    cache = Cache(cache_dir or Path(".cache"))
    if backend is None:
        import anthropic

        from .backends.claude import ClaudeBackend

        backend = ClaudeBackend(
            client=anthropic.AsyncAnthropic(
                api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
            )
        )
    return asyncio.run(_run_async(urls, backend, cache))
