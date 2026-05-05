"""Render a CoverageMatrix as a self-contained HTML page.

The page is a single file with inlined CSS and no JavaScript. Tier sections
and per-claim citation panels collapse via native <details>. Designed to be
shareable as-is and to print cleanly.

Layout, top to bottom:
    - Header (story summary)
    - Articles (one row per source with title + outlet + link)
    - Coverage Matrix (rows = canonical claims grouped by tier;
      columns = outlets; cells = status icons; each row expands to show the
      verbatim citations side-by-side)
    - Outlet Lens (per-outlet fingerprint derived from the matrix:
      assertion rate, attribution rate, omission rate, scoops)
"""

from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from .models import (
    Article,
    ArticleLens,
    ConsensusTier,
    CoverageMatrix,
    CoverageStatus,
    HeadlineFraming,
    LoadedTerm,
    OutletCoverage,
    SyndicationGroup,
    TieredClaim,
)


def _esc(value: str | None) -> str:
    return html.escape(value or "", quote=True)


_TIER_LABELS = {
    ConsensusTier.UNIVERSAL: "Universal",
    ConsensusTier.MAJORITY: "Majority",
    ConsensusTier.DISPUTED: "Disputed",
    ConsensusTier.ATTRIBUTED_ONLY: "Attributed only",
    ConsensusTier.SINGLE_SOURCED: "Single-sourced",
}

_TIER_DESCRIPTIONS = {
    ConsensusTier.UNIVERSAL: "Asserted as fact by every covering outlet.",
    ConsensusTier.MAJORITY: "Asserted by most outlets; some omit it.",
    ConsensusTier.DISPUTED: "At least one outlet contradicts another.",
    ConsensusTier.ATTRIBUTED_ONLY: "No outlet asserts as fact; only quoted from sources.",
    ConsensusTier.SINGLE_SOURCED: "Only one outlet covers this claim.",
}

_TIER_ORDER = [
    ConsensusTier.UNIVERSAL,
    ConsensusTier.MAJORITY,
    ConsensusTier.DISPUTED,
    ConsensusTier.ATTRIBUTED_ONLY,
    ConsensusTier.SINGLE_SOURCED,
]

_STATUS_GLYPH = {
    CoverageStatus.ASSERTED: "●",
    CoverageStatus.ATTRIBUTED: "◐",
    CoverageStatus.CONTRADICTED: "✕",
    CoverageStatus.OMITTED: "○",
}

_STATUS_LABEL = {
    CoverageStatus.ASSERTED: "Asserted",
    CoverageStatus.ATTRIBUTED: "Attributed",
    CoverageStatus.CONTRADICTED: "Contradicted",
    CoverageStatus.OMITTED: "Omitted",
}

_FRAMING_LABEL = {
    HeadlineFraming.POSITIVE: "Positive framing",
    HeadlineFraming.NEUTRAL: "Neutral framing",
    HeadlineFraming.NEGATIVE: "Negative framing",
    HeadlineFraming.MIXED: "Mixed framing",
}


def _outlet_order(articles: list[Article]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for article in articles:
        if article.outlet_domain not in seen:
            seen.add(article.outlet_domain)
            order.append(article.outlet_domain)
    return order


def _coverage_by_outlet(
    coverage: Iterable[OutletCoverage],
) -> dict[str, OutletCoverage]:
    out: dict[str, OutletCoverage] = {}
    for c in coverage:
        out[c.outlet_domain] = c
    return out


_CSS = """\
:root {
  --bg: #fafaf7;
  --surface: #ffffff;
  --border: #e5e5e0;
  --border-strong: #c7c7be;
  --text: #1a1a1a;
  --text-muted: #6b6b66;
  --text-subtle: #9a9a93;
  --accent: #1f3a5f;

  --tier-universal: #2e7d32;
  --tier-majority: #5d8c4a;
  --tier-disputed: #c0392b;
  --tier-attributed: #d97706;
  --tier-single: #6d28d9;

  --status-asserted-bg: #e6f4ea;
  --status-asserted-fg: #1e6b32;
  --status-attributed-bg: #fef3c7;
  --status-attributed-fg: #92400e;
  --status-contradicted-bg: #fde2e1;
  --status-contradicted-fg: #b3261e;
  --status-omitted-bg: #f4f4f0;
  --status-omitted-fg: #a8a8a0;
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 32px 24px 72px;
}

header.site {
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 24px;
}
header.site h1 {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 4px;
  letter-spacing: -0.01em;
}
header.site .meta {
  color: var(--text-muted);
  font-size: 13px;
}

section { margin-top: 32px; }
section h2 {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin: 0 0 12px;
}

.articles {
  display: grid;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.article {
  background: var(--surface);
  padding: 12px 14px;
  display: grid;
  grid-template-columns: 140px 1fr auto;
  gap: 16px;
  align-items: baseline;
  font-size: 14px;
}
.article .outlet {
  font-weight: 600;
  color: var(--accent);
}
.article .title {
  font-family: Georgia, "Times New Roman", serif;
  color: var(--text);
}
.article .date {
  color: var(--text-subtle);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.article .syndication-badge {
  display: inline-block;
  margin-top: 4px;
  font-size: 11px;
  background: #eef2ff;
  color: #3730a3;
  border: 1px solid #c7d2fe;
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 500;
}
.article a {
  color: inherit;
  text-decoration: none;
}
.article a:hover { text-decoration: underline; }

.matrix-frame {
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--surface);
  overflow: hidden;
}
.matrix-head {
  display: grid;
  align-items: end;
  padding: 12px 14px;
  background: #f4f4ef;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
  letter-spacing: 0.04em;
}
.matrix-head .outlet-col {
  text-align: center;
  font-family: -apple-system, system-ui, sans-serif;
  text-transform: lowercase;
}

details.tier {
  border-top: 1px solid var(--border);
}
details.tier:first-of-type { border-top: none; }
details.tier > summary {
  list-style: none;
  cursor: pointer;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  background: #fbfbf6;
}
details.tier > summary::-webkit-details-marker { display: none; }
details.tier > summary .badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #fff;
}
details.tier[data-tier="universal"] > summary .badge { background: var(--tier-universal); }
details.tier[data-tier="majority"] > summary .badge { background: var(--tier-majority); }
details.tier[data-tier="disputed"] > summary .badge { background: var(--tier-disputed); }
details.tier[data-tier="attributed_only"] > summary .badge { background: var(--tier-attributed); }
details.tier[data-tier="single_sourced"] > summary .badge { background: var(--tier-single); }
details.tier > summary .tier-desc {
  color: var(--text-muted);
  font-size: 12px;
}
details.tier > summary .count {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  color: var(--text-subtle);
  font-size: 12px;
}

details.claim {
  border-top: 1px solid var(--border);
}
details.claim > summary {
  list-style: none;
  cursor: pointer;
  display: grid;
  align-items: center;
  padding: 10px 14px;
  gap: 12px;
}
details.claim > summary::-webkit-details-marker { display: none; }
details.claim > summary:hover { background: #fbfbf6; }
details.claim .canonical {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 15px;
  line-height: 1.4;
  color: var(--text);
}

.cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 28px;
  border-radius: 4px;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  margin: 0 auto;
}
.cell.asserted { background: var(--status-asserted-bg); color: var(--status-asserted-fg); }
.cell.attributed { background: var(--status-attributed-bg); color: var(--status-attributed-fg); }
.cell.contradicted { background: var(--status-contradicted-bg); color: var(--status-contradicted-fg); }
.cell.omitted { background: var(--status-omitted-bg); color: var(--status-omitted-fg); }

.citations {
  background: #fbfbf6;
  border-top: 1px solid var(--border);
  padding: 12px 14px 18px 14px;
  display: grid;
  gap: 10px;
}
.citation {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 14px;
  font-size: 14px;
  align-items: baseline;
}
.citation .outlet-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--accent);
  font-weight: 600;
  font-size: 13px;
}
.citation .status-pill {
  padding: 1px 7px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.citation .status-pill.asserted { background: var(--status-asserted-bg); color: var(--status-asserted-fg); }
.citation .status-pill.attributed { background: var(--status-attributed-bg); color: var(--status-attributed-fg); }
.citation .status-pill.contradicted { background: var(--status-contradicted-bg); color: var(--status-contradicted-fg); }
.citation .status-pill.omitted { background: var(--status-omitted-bg); color: var(--status-omitted-fg); }
.citation blockquote {
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  color: var(--text);
  border-left: 2px solid var(--border-strong);
  padding-left: 10px;
  line-height: 1.5;
}
.citation blockquote.empty {
  color: var(--text-subtle);
  font-style: italic;
  border-left-color: var(--border);
}
.citation .attributed-to {
  display: block;
  margin-top: 4px;
  font-family: -apple-system, system-ui, sans-serif;
  font-size: 12px;
  color: var(--text-muted);
}
.citation .position-label {
  font-size: 11px;
  color: var(--text-subtle);
  font-variant-numeric: tabular-nums;
  margin-left: 6px;
  white-space: nowrap;
}

.legend {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 10px;
}
.legend .item { display: inline-flex; align-items: center; gap: 6px; }

.fingerprints {
  display: grid;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.fingerprint {
  background: var(--surface);
  padding: 14px;
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 16px;
}
.fingerprint .outlet-name {
  font-weight: 600;
  color: var(--accent);
}
.fingerprint .stats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  font-size: 13px;
}
.fingerprint .stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.fingerprint .stat .num {
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.fingerprint .stat .label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

footer.site {
  margin-top: 48px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-subtle);
}

.lens-cards {
  display: grid;
  gap: 14px;
  grid-template-columns: 1fr;
}
@media (min-width: 900px) {
  .lens-cards.split-2 { grid-template-columns: 1fr 1fr; }
  .lens-cards.split-3 { grid-template-columns: repeat(3, 1fr); }
}

.lens-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border-strong);
  border-radius: 4px;
  padding: 14px 16px;
}
.lens-card[data-framing="positive"] { border-left-color: #2563eb; }
.lens-card[data-framing="neutral"] { border-left-color: #6b7280; }
.lens-card[data-framing="negative"] { border-left-color: #c0392b; }
.lens-card[data-framing="mixed"] { border-left-color: #7c3aed; }

.lens-card .head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.lens-card .outlet { font-weight: 600; color: var(--accent); }
.lens-card .framing-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 2px 8px;
  border-radius: 10px;
  color: #fff;
}
.lens-card[data-framing="positive"] .framing-badge { background: #2563eb; }
.lens-card[data-framing="neutral"] .framing-badge { background: #6b7280; }
.lens-card[data-framing="negative"] .framing-badge { background: #c0392b; }
.lens-card[data-framing="mixed"] .framing-badge { background: #7c3aed; }

.lens-card .stance {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  line-height: 1.5;
  margin: 0 0 14px;
  color: var(--text);
}

.lens-section-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin: 12px 0 6px;
}
.lens-section-label:first-of-type { margin-top: 0; }

.loaded-terms { display: grid; gap: 10px; }
.loaded-term { font-size: 13px; line-height: 1.4; }
.loaded-term .term-pair { margin-bottom: 2px; }
.loaded-term .term {
  font-weight: 600;
  color: #92400e;
}
.loaded-term .arrow { color: var(--text-subtle); margin: 0 6px; }
.loaded-term .alternative { color: var(--text-muted); }
.loaded-term blockquote {
  margin: 4px 0 0;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 13px;
  color: var(--text);
  border-left: 2px solid var(--border);
  padding-left: 10px;
}
.loaded-term blockquote mark {
  background: #fef3c7;
  color: #92400e;
  padding: 0 2px;
  border-radius: 2px;
}

.sources-quoted { display: flex; flex-wrap: wrap; gap: 6px; }
.sources-quoted .source {
  font-size: 12px;
  background: #f4f4ef;
  border: 1px solid var(--border);
  padding: 2px 8px;
  border-radius: 12px;
  color: var(--text-muted);
}
.sources-quoted .empty {
  font-size: 12px;
  color: var(--text-subtle);
  font-style: italic;
}

@media (max-width: 720px) {
  .article { grid-template-columns: 1fr; gap: 4px; }
  .citation { grid-template-columns: 1fr; }
  .fingerprint { grid-template-columns: 1fr; }
  .fingerprint .stats { grid-template-columns: repeat(3, 1fr); }
  .lens-cards.split-2, .lens-cards.split-3 { grid-template-columns: 1fr; }
}

@media print {
  body { background: white; }
  details { break-inside: avoid; }
  details[open] > summary { background: white; }
}
"""


def _grid_template(n_outlets: int) -> str:
    # Canonical-text column flexes; outlet columns are fixed.
    return f"grid-template-columns: 1fr repeat({n_outlets}, 60px);"


def _syndication_partners(
    article: Article,
    syndication_groups: list[SyndicationGroup],
    articles_by_id: dict[str, Article],
) -> list[str]:
    """Return outlet domains of articles syndicated with `article` (excluding itself)."""
    for group in syndication_groups:
        if article.id in group.article_ids:
            return [
                articles_by_id[aid].outlet_domain
                for aid in group.article_ids
                if aid != article.id and aid in articles_by_id
            ]
    return []


def _render_articles(
    articles: list[Article],
    outlet_order: list[str],
    syndication_groups: list[SyndicationGroup],
) -> str:
    by_outlet = {a.outlet_domain: a for a in articles}
    articles_by_id = {a.id: a for a in articles}
    rows = []
    for outlet in outlet_order:
        a = by_outlet[outlet]
        date = a.published_at.date().isoformat() if a.published_at else "—"
        title = a.title or a.url
        partners = _syndication_partners(a, syndication_groups, articles_by_id)
        title_block = (
            f'<a href="{_esc(a.url)}" target="_blank" rel="noopener">{_esc(title)}</a>'
        )
        if partners:
            partners_str = ", ".join(_esc(p) for p in partners)
            title_block += (
                f'<br><span class="syndication-badge">'
                f"Syndicated copy — overlaps with {partners_str}"
                f"</span>"
            )
        rows.append(
            f'<div class="article">'
            f'<div class="outlet">{_esc(outlet)}</div>'
            f'<div class="title">{title_block}</div>'
            f'<div class="date">{_esc(date)}</div>'
            f"</div>"
        )
    return f'<div class="articles">{"".join(rows)}</div>'


def _render_matrix_head(outlet_order: list[str]) -> str:
    grid = _grid_template(len(outlet_order))
    cols = "".join(
        f'<div class="outlet-col">{_esc(o)}</div>' for o in outlet_order
    )
    return (
        f'<div class="matrix-head" style="{grid}">'
        f'<div>Canonical claim</div>{cols}'
        f"</div>"
    )


def _render_cells(claim: TieredClaim, outlet_order: list[str]) -> str:
    by_outlet = _coverage_by_outlet(claim.outlets)
    cells = []
    for outlet in outlet_order:
        cov = by_outlet.get(outlet)
        if cov is None:
            cells.append('<span class="cell omitted">○</span>')
            continue
        glyph = _STATUS_GLYPH[cov.status]
        cls = cov.status.value
        cells.append(f'<span class="cell {cls}">{glyph}</span>')
    return "".join(cells)


def _position_label(position: int | None, total: int) -> str:
    if position is None or position <= 0:
        return ""
    if total <= 0:
        return f"¶ {position}"
    if total < 3:
        # Banding by thirds is meaningless for very short articles.
        return f"¶ {position}/{total}"
    third = total / 3
    band = "early" if position <= third else "middle" if position <= 2 * third else "late"
    return f"¶ {position}/{total} · {band}"


def _render_citations(
    claim: TieredClaim,
    outlet_order: list[str],
    articles_by_id: dict[str, Article],
) -> str:
    by_outlet = _coverage_by_outlet(claim.outlets)
    parts = []
    for outlet in outlet_order:
        cov = by_outlet.get(outlet)
        if cov is None:
            continue
        status_label = _STATUS_LABEL[cov.status]
        status_cls = cov.status.value
        if cov.source_quote:
            quote_html = f"<blockquote>{_esc(cov.source_quote)}</blockquote>"
        else:
            quote_html = (
                f'<blockquote class="empty">— ({status_label.lower()})</blockquote>'
            )
        attr_html = ""
        if cov.attributed_to:
            attr_html = (
                f'<span class="attributed-to">attributed to '
                f"{_esc(cov.attributed_to)}</span>"
            )
        position_html = ""
        article = articles_by_id.get(cov.article_id)
        if article and cov.position:
            label = _position_label(cov.position, article.paragraph_count)
            if label:
                position_html = (
                    f' <span class="position-label">{_esc(label)}</span>'
                )
        parts.append(
            f'<div class="citation">'
            f'<div class="outlet-cell">'
            f'<span>{_esc(outlet)}</span>'
            f'<span class="status-pill {status_cls}">{_esc(status_label)}</span>'
            f"{position_html}"
            f"</div>"
            f"<div>{quote_html}{attr_html}</div>"
            f"</div>"
        )
    return f'<div class="citations">{"".join(parts)}</div>'


def _render_claim(
    claim: TieredClaim,
    outlet_order: list[str],
    articles_by_id: dict[str, Article],
) -> str:
    grid = _grid_template(len(outlet_order))
    cells = _render_cells(claim, outlet_order)
    return (
        f'<details class="claim">'
        f'<summary style="{grid}">'
        f'<span class="canonical">{_esc(claim.canonical_text)}</span>'
        f"{cells}"
        f"</summary>"
        f"{_render_citations(claim, outlet_order, articles_by_id)}"
        f"</details>"
    )


def _render_tier_section(
    tier: ConsensusTier,
    claims: list[TieredClaim],
    outlet_order: list[str],
    articles_by_id: dict[str, Article],
) -> str:
    rows = "".join(_render_claim(c, outlet_order, articles_by_id) for c in claims)
    return (
        f'<details class="tier" data-tier="{tier.value}" open>'
        f"<summary>"
        f'<span class="badge">{_esc(_TIER_LABELS[tier])}</span>'
        f'<span class="tier-desc">{_esc(_TIER_DESCRIPTIONS[tier])}</span>'
        f'<span class="count">{len(claims)} claim{"" if len(claims) == 1 else "s"}</span>'
        f"</summary>"
        f"{rows}"
        f"</details>"
    )


def _render_matrix(matrix: CoverageMatrix, outlet_order: list[str]) -> str:
    by_tier: dict[ConsensusTier, list[TieredClaim]] = defaultdict(list)
    for c in matrix.claims:
        by_tier[c.tier].append(c)

    articles_by_id = {a.id: a for a in matrix.articles}
    sections = []
    for tier in _TIER_ORDER:
        if tier in by_tier:
            sections.append(
                _render_tier_section(tier, by_tier[tier], outlet_order, articles_by_id)
            )
    return f'<div class="matrix-frame">{_render_matrix_head(outlet_order)}{"".join(sections)}</div>'


def _render_legend() -> str:
    items = []
    for status in (
        CoverageStatus.ASSERTED,
        CoverageStatus.ATTRIBUTED,
        CoverageStatus.CONTRADICTED,
        CoverageStatus.OMITTED,
    ):
        items.append(
            f'<span class="item">'
            f'<span class="cell {status.value}">{_STATUS_GLYPH[status]}</span>'
            f"{_esc(_STATUS_LABEL[status])}"
            f"</span>"
        )
    return f'<div class="legend">{"".join(items)}</div>'


def _compute_fingerprints(
    matrix: CoverageMatrix, outlet_order: list[str]
) -> dict[str, dict[str, int]]:
    """Per-outlet stats derived from the coverage matrix.

    Stats: covered (asserted+attributed+contradicted), asserted, attributed,
    contradicted, omitted, scoops (single-sourced claims this outlet had).
    """
    stats: dict[str, dict[str, int]] = {
        outlet: {
            "covered": 0,
            "asserted": 0,
            "attributed": 0,
            "contradicted": 0,
            "omitted": 0,
            "scoops": 0,
        }
        for outlet in outlet_order
    }
    for claim in matrix.claims:
        for cov in claim.outlets:
            outlet = cov.outlet_domain
            if outlet not in stats:
                continue
            if cov.status == CoverageStatus.OMITTED:
                stats[outlet]["omitted"] += 1
            else:
                stats[outlet]["covered"] += 1
                stats[outlet][cov.status.value] += 1
        if claim.tier == ConsensusTier.SINGLE_SOURCED:
            for cov in claim.outlets:
                if cov.status != CoverageStatus.OMITTED and cov.outlet_domain in stats:
                    stats[cov.outlet_domain]["scoops"] += 1
    return stats


def _highlight_term(sentence: str, term: str) -> str:
    if not term:
        return _esc(sentence)
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    parts: list[str] = []
    last = 0
    for m in pattern.finditer(sentence):
        parts.append(_esc(sentence[last : m.start()]))
        parts.append(f"<mark>{_esc(sentence[m.start() : m.end()])}</mark>")
        last = m.end()
    parts.append(_esc(sentence[last:]))
    return "".join(parts)


def _render_loaded_terms(terms: list[LoadedTerm]) -> str:
    if not terms:
        return (
            '<div class="lens-section-label">Loaded terms</div>'
            '<div class="sources-quoted"><span class="empty">none flagged</span></div>'
        )
    rows = []
    for t in terms:
        sentence_html = _highlight_term(t.in_sentence, t.term)
        rows.append(
            f'<div class="loaded-term">'
            f'<div class="term-pair">'
            f'<span class="term">{_esc(t.term)}</span>'
            f'<span class="arrow">→</span>'
            f'<span class="alternative">{_esc(t.neutral_alternative)}</span>'
            f"</div>"
            f"<blockquote>{sentence_html}</blockquote>"
            f"</div>"
        )
    return (
        f'<div class="lens-section-label">Loaded terms ({len(terms)})</div>'
        f'<div class="loaded-terms">{"".join(rows)}</div>'
    )


def _render_sources(sources: list[str]) -> str:
    if not sources:
        return (
            '<div class="lens-section-label">Sources quoted</div>'
            '<div class="sources-quoted"><span class="empty">none identified</span></div>'
        )
    chips = "".join(f'<span class="source">{_esc(s)}</span>' for s in sources)
    return (
        f'<div class="lens-section-label">Sources quoted ({len(sources)})</div>'
        f'<div class="sources-quoted">{chips}</div>'
    )


def _render_lens_card(lens: ArticleLens) -> str:
    framing = lens.signals.headline_framing.value
    return (
        f'<article class="lens-card" data-framing="{framing}">'
        f'<div class="head">'
        f'<span class="outlet">{_esc(lens.outlet_domain)}</span>'
        f'<span class="framing-badge">{_esc(_FRAMING_LABEL[lens.signals.headline_framing])}</span>'
        f"</div>"
        f'<p class="stance">{_esc(lens.signals.stance_summary)}</p>'
        f"{_render_loaded_terms(lens.signals.loaded_terms)}"
        f"{_render_sources(lens.signals.sources_quoted)}"
        f"</article>"
    )


def _render_lenses(lenses: list[ArticleLens], outlet_order: list[str]) -> str:
    by_outlet = {l.outlet_domain: l for l in lenses}
    cards = [
        _render_lens_card(by_outlet[outlet])
        for outlet in outlet_order
        if outlet in by_outlet
    ]
    if not cards:
        return ""
    cls = "lens-cards"
    if len(cards) == 2:
        cls += " split-2"
    elif len(cards) == 3:
        cls += " split-3"
    return f'<div class="{cls}">{"".join(cards)}</div>'


def _render_fingerprints(matrix: CoverageMatrix, outlet_order: list[str]) -> str:
    stats = _compute_fingerprints(matrix, outlet_order)
    rows = []
    for outlet in outlet_order:
        s = stats[outlet]
        rows.append(
            f'<div class="fingerprint">'
            f'<div class="outlet-name">{_esc(outlet)}</div>'
            f'<div class="stats">'
            f'<div class="stat"><span class="num">{s["asserted"]}</span><span class="label">Asserted</span></div>'
            f'<div class="stat"><span class="num">{s["attributed"]}</span><span class="label">Attributed</span></div>'
            f'<div class="stat"><span class="num">{s["contradicted"]}</span><span class="label">Contradicted</span></div>'
            f'<div class="stat"><span class="num">{s["omitted"]}</span><span class="label">Omitted</span></div>'
            f'<div class="stat"><span class="num">{s["scoops"]}</span><span class="label">Scoops</span></div>'
            f"</div>"
            f"</div>"
        )
    return f'<div class="fingerprints">{"".join(rows)}</div>'


def render_html(matrix: CoverageMatrix) -> str:
    outlet_order = _outlet_order(matrix.articles)
    n_articles = len(matrix.articles)
    n_outlets = len(outlet_order)
    n_claims = len(matrix.claims)
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    framing_section = ""
    if matrix.lenses:
        framing_section = (
            "<section>"
            "<h2>Per-Article Framing</h2>"
            f"{_render_lenses(matrix.lenses, outlet_order)}"
            "</section>"
        )

    n_voices = n_articles - sum(
        len(g.article_ids) - 1 for g in matrix.syndication_groups
    )
    voices_part = (
        f" · {n_voices} independent voice{'' if n_voices == 1 else 's'}"
        if n_voices != n_articles
        else ""
    )

    body = (
        '<header class="site">'
        "<h1>News Lens — Coverage Matrix</h1>"
        f'<div class="meta">{n_articles} article{"" if n_articles == 1 else "s"}'
        f' · {n_outlets} outlet{"" if n_outlets == 1 else "s"}'
        f"{voices_part}"
        f' · {n_claims} canonical claim{"" if n_claims == 1 else "s"}'
        f" · generated {_esc(generated)}</div>"
        "</header>"
        "<section>"
        "<h2>Articles</h2>"
        f"{_render_articles(matrix.articles, outlet_order, matrix.syndication_groups)}"
        "</section>"
        "<section>"
        "<h2>Coverage Matrix</h2>"
        f"{_render_matrix(matrix, outlet_order)}"
        f"{_render_legend()}"
        "</section>"
        f"{framing_section}"
        "<section>"
        "<h2>Outlet Coverage Profile</h2>"
        f"{_render_fingerprints(matrix, outlet_order)}"
        "</section>"
        '<footer class="site">'
        "Citations link back to verbatim spans from the source articles. "
        "Tiers reflect cross-outlet status only — they are not a truth verdict."
        "</footer>"
    )

    return (
        "<!DOCTYPE html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>News Lens — Coverage Matrix</title>"
        f"<style>{_CSS}</style>"
        "</head>"
        '<body><div class="page">'
        f"{body}"
        "</div></body>"
        "</html>"
    )
