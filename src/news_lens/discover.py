"""Auto-discover news articles covering a topic.

Uses the GDELT 2.0 Doc API (no API key, no subscription, public data) to
find articles about a query across many outlets, then picks a diverse
slice using the outlet registry.

The GDELT path is deliberately the only one for now:
- It returns actual article URLs (no Google News redirects to decode).
- It's free with no rate limits worth speaking of for personal use.
- It indexes a large set of outlets globally, which gives the
  cross-outlet comparison something to work with.

For more granular searches (date ranges, language filters, etc.),
fall back to building the GDELT URL manually and passing the resolved
URLs as arguments.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .outlets import SPECTRUM_ORDER, lookup as outlet_lookup


@dataclass
class NewsResult:
    title: str
    url: str
    outlet_domain: str
    published_at: Optional[datetime] = None
    country: Optional[str] = None


_GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_USER_AGENT = "news-lens/0.1"


def _fetch_gdelt(query: str, max_records: int) -> dict:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "JSON",
        "maxrecords": str(max_records),
        "sort": "HybridRel",  # relevance + freshness
    }
    url = f"{_GDELT_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    if not body.strip():
        return {"articles": []}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # GDELT occasionally returns HTML error pages on malformed queries.
        return {"articles": []}


def _normalize_domain(domain: str) -> str:
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


async def search(
    query: str,
    *,
    max_results: int = 30,
) -> list[NewsResult]:
    """Search GDELT for articles matching the query.

    Returns up to max_results articles, ordered by GDELT's HybridRel
    score (relevance + freshness). Each result has the article URL,
    outlet domain (lowercased, www. stripped), title, and publish date
    if available.
    """
    raw = await asyncio.to_thread(_fetch_gdelt, query, max_results)
    results: list[NewsResult] = []
    for art in raw.get("articles", []):
        url = (art.get("url") or "").strip()
        domain = _normalize_domain(art.get("domain") or "")
        if not url or not domain:
            continue

        pub: Optional[datetime] = None
        seendate = art.get("seendate")
        if seendate:
            try:
                pub = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
            except ValueError:
                pub = None

        results.append(
            NewsResult(
                title=(art.get("title") or "").strip(),
                url=url,
                outlet_domain=domain,
                published_at=pub,
                country=art.get("sourcecountry"),
            )
        )
    return results


def select_diverse(
    results: list[NewsResult],
    *,
    n: int = 5,
    require_known: bool = False,
    balance_spectrum: bool = False,
) -> list[NewsResult]:
    """Pick up to n results, one per outlet, preferring known outlets.

    Strategy:
    1. First pass: keep one result per outlet that's in the registry.
    2. Second pass (if we still have room): fill with one result per
       not-yet-seen outlet, even if the outlet isn't in the registry —
       unless require_known is True, in which case we stop early.

    Preserves GDELT's relevance order within each pass.

    With balance_spectrum=True the selection round-robins across
    political-lean buckets (left → center-left → center → center-right
    → right) before filling repeats, so the result favors cross-spectrum
    coverage over the relevance-only ranking. Outlets with no lean are
    held until last.
    """
    if balance_spectrum:
        return _select_spectrum_balanced(results, n=n, require_known=require_known)

    seen_outlets: set[str] = set()
    selected: list[NewsResult] = []

    # Pass 1: known outlets only.
    for r in results:
        if len(selected) >= n:
            break
        if r.outlet_domain in seen_outlets:
            continue
        if outlet_lookup(r.outlet_domain) is None:
            continue
        seen_outlets.add(r.outlet_domain)
        selected.append(r)

    if require_known or len(selected) >= n:
        return selected

    # Pass 2: any outlet not yet selected.
    for r in results:
        if len(selected) >= n:
            break
        if r.outlet_domain in seen_outlets:
            continue
        seen_outlets.add(r.outlet_domain)
        selected.append(r)

    return selected


def _select_spectrum_balanced(
    results: list[NewsResult],
    *,
    n: int,
    require_known: bool,
) -> list[NewsResult]:
    """Round-robin across spectrum buckets to maximize cross-spectrum coverage.

    Pass 1 fills one result per (left, center-left, center, center-right,
    right) bucket. Repeats round-robin until n is reached or every bucket
    is exhausted of fresh outlets. Pass 2 (skipped if require_known) fills
    remaining slots from outlets without a lean tag.
    """
    # Group by lean. Order within each bucket preserves GDELT relevance.
    by_lean: dict[Optional[str], list[NewsResult]] = {l: [] for l in SPECTRUM_ORDER}
    by_lean[None] = []
    for r in results:
        info = outlet_lookup(r.outlet_domain)
        lean = info.lean if info else None
        by_lean[lean].append(r)

    seen_outlets: set[str] = set()
    selected: list[NewsResult] = []

    # Pass 1: round-robin across the five lean buckets, one outlet per bucket
    # per cycle, only outlets with a lean.
    while len(selected) < n:
        progress = False
        for lean in SPECTRUM_ORDER:
            picked = _take_next_unique(by_lean[lean], seen_outlets)
            if picked is not None:
                selected.append(picked)
                progress = True
                if len(selected) >= n:
                    break
        if not progress:
            break

    if require_known:
        return selected

    # Pass 2: outlets without a lean, until n is reached.
    while len(selected) < n:
        picked = _take_next_unique(by_lean[None], seen_outlets)
        if picked is None:
            break
        selected.append(picked)

    return selected


def _take_next_unique(
    bucket: list[NewsResult], seen_outlets: set[str]
) -> Optional[NewsResult]:
    """Pop and return the first result whose outlet hasn't been picked yet.

    Mutates the bucket so a later cycle skips already-considered entries.
    """
    while bucket:
        r = bucket.pop(0)
        if r.outlet_domain in seen_outlets:
            continue
        seen_outlets.add(r.outlet_domain)
        return r
    return None


def report_selection(selected: list[NewsResult]) -> None:
    """Print a one-line-per-source summary to stderr."""
    if not selected:
        print("WARN: no articles selected", file=sys.stderr)
        return
    for r in selected:
        info = outlet_lookup(r.outlet_domain)
        if info:
            lean = f" [{info.lean}]" if info.lean else " [no-lean]"
            label = f"{info.name} ({r.outlet_domain}){lean}"
        else:
            label = f"{r.outlet_domain} [unknown outlet]"
        title = r.title[:80] if r.title else "(no title)"
        print(f"  {label}: {title}", file=sys.stderr)
