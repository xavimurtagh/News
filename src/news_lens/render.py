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
from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable

from .models import (
    Article,
    ArticleLens,
    ConsensusTier,
    CoverageMatrix,
    CoverageStatus,
    FramingDevice,
    FramingDeviceType,
    GroundingFlag,
    HeadlineFraming,
    LoadedTerm,
    OutletCoverage,
    Provenance,
    SyndicationGroup,
    TieredClaim,
)
from .outlets import SPECTRUM_ORDER
from .outlets import display_name as _outlet_display_name
from .outlets import lookup as _outlet_lookup
from .outlets import ownership_summary as _ownership_summary


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
    ConsensusTier.UNIVERSAL: (
        "Every outlet asserts this as fact and none question it. Shared "
        "ground like this is the least scrutinised by readers — and "
        "therefore the most worth examining."
    ),
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

# Short pill labels for the per-outlet provenance of a claim.
_PROVENANCE_LABEL = {
    Provenance.PRIMARY: "Primary source",
    Provenance.NAMED: "Named source",
    Provenance.ANONYMOUS: "Anonymous source",
    Provenance.MEDIA: "Other media",
    Provenance.UNCITED: "Uncited",
}

_GROUNDING_LABEL = {
    GroundingFlag.WELL_GROUNDED: "Grounded",
    GroundingFlag.SINGLE_ORIGIN: "Single origin",
    GroundingFlag.THINLY_SOURCED: "Thinly sourced",
}

_GROUNDING_DESC = {
    GroundingFlag.WELL_GROUNDED: (
        "At least one outlet ties this claim to a primary document or a "
        "named source."
    ),
    GroundingFlag.SINGLE_ORIGIN: (
        "Several outlets carry this claim, but every one attributes it to "
        "the same named source — shared wording, not independent "
        "confirmation."
    ),
    GroundingFlag.THINLY_SOURCED: (
        "No outlet ties this claim to a primary document or a named "
        "source. It rests on anonymous sourcing, other media, or bare "
        "assertion — weigh it accordingly."
    ),
}

_DEVICE_LABEL = {
    FramingDeviceType.SELECTIVE_HEDGING: "Selective hedging",
    FramingDeviceType.PASSIVE_VOICE_ASYMMETRY: "Passive-voice asymmetry",
    FramingDeviceType.CHARGED_ATTRIBUTION: "Charged attribution",
    FramingDeviceType.LEDE_BURYING: "Lede burying",
    FramingDeviceType.SOURCE_ASYMMETRY: "Source asymmetry",
    FramingDeviceType.IMPLIED_CONSENSUS: "Implied consensus",
    FramingDeviceType.SCARE_QUOTES: "Scare quotes",
    FramingDeviceType.NUMERICAL_FRAMING: "Numerical framing",
    FramingDeviceType.EUPHEMISM: "Euphemism",
    FramingDeviceType.OMISSION_FLAG: "Omission",
}

# Coarse grouping for color: vocabulary-adjacent / structural / meta
_DEVICE_GROUP = {
    FramingDeviceType.CHARGED_ATTRIBUTION: "vocab",
    FramingDeviceType.SCARE_QUOTES: "vocab",
    FramingDeviceType.EUPHEMISM: "vocab",
    FramingDeviceType.PASSIVE_VOICE_ASYMMETRY: "structure",
    FramingDeviceType.LEDE_BURYING: "structure",
    FramingDeviceType.SOURCE_ASYMMETRY: "structure",
    FramingDeviceType.NUMERICAL_FRAMING: "structure",
    FramingDeviceType.SELECTIVE_HEDGING: "meta",
    FramingDeviceType.IMPLIED_CONSENSUS: "meta",
    FramingDeviceType.OMISSION_FLAG: "meta",
}

_SUMMARY_HEADINGS = {
    ConsensusTier.UNIVERSAL: "Shared assumptions — asserted by all, questioned by none",
    ConsensusTier.MAJORITY: "What most outlets agreed on",
    ConsensusTier.DISPUTED: "Where outlets disagreed",
    ConsensusTier.ATTRIBUTED_ONLY: "Quoted positions only — no outlet asserted as fact",
    ConsensusTier.SINGLE_SOURCED: "One-outlet exclusives",
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
.section-note {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0 0 12px;
  max-width: 64ch;
}

.sample-banner {
  border: 1px solid var(--border-strong);
  border-left: 3px solid var(--accent);
  background: #f4f6f9;
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 24px;
}
.sample-banner-head {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 6px;
}
.sample-stats {
  font-size: 13px;
  color: var(--text);
  margin-bottom: 8px;
}
.sample-notes {
  margin: 8px 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}
.sample-notes li { margin: 3px 0; }
.sample-caveat {
  font-size: 12px;
  font-style: italic;
  color: var(--text-muted);
  line-height: 1.5;
  border-top: 1px solid var(--border);
  padding-top: 8px;
  margin-top: 8px;
}

.toc {
  display: flex;
  align-items: baseline;
  gap: 14px;
  flex-wrap: wrap;
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 4px;
  padding: 10px 14px;
  margin-bottom: 24px;
  font-size: 12px;
}
.toc .toc-label {
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.toc .toc-links {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.toc a {
  color: var(--accent);
  text-decoration: none;
  white-space: nowrap;
}
.toc a:hover { text-decoration: underline; }
html { scroll-behavior: smooth; }
:target { scroll-margin-top: 14px; }

.ownership-stats {
  font-size: 13px;
  color: var(--text);
  margin-bottom: 4px;
}
.ownership-groups {
  display: grid;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
  margin-top: 12px;
}
.owner-group {
  background: var(--surface);
  padding: 12px 14px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
}
.owner-group.unknown { background: #fbfbf6; }
.owner-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.owner-group.unknown .owner-label { color: var(--text-subtle); font-weight: 500; }
.owner-share {
  font-family: -apple-system, system-ui, sans-serif;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  padding: 1px 7px;
  border-radius: 10px;
  background: #fef3c7;
  color: #92400e;
  text-transform: uppercase;
}
.owner-outlets {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 2px;
  font-size: 13px;
}
.owner-outlets li {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.owner-outlets .outlet-name {
  color: var(--text);
  font-weight: 500;
}
.owner-outlets .outlet-domain {
  color: var(--text-subtle);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.voices-stats {
  font-size: 13px;
  color: var(--text);
  margin-bottom: 12px;
}
.voices-list {
  display: grid;
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.voice-row {
  background: var(--surface);
  display: grid;
  grid-template-columns: minmax(140px, 220px) minmax(140px, 200px) 1fr;
  gap: 14px;
  padding: 10px 14px;
  align-items: center;
  font-size: 13px;
}
.voice-name {
  font-weight: 600;
  color: var(--text);
}
.voice-row.single .voice-name { color: var(--text-muted); font-weight: 500; }
.voice-share {
  display: flex;
  align-items: center;
  gap: 8px;
}
.voice-bar {
  height: 8px;
  border-radius: 4px;
  background: #c5d8ee;
  flex-shrink: 0;
  min-width: 8px;
}
.voice-row.majority .voice-bar { background: #4ea16a; }
.voice-row.minority .voice-bar { background: #d1a45b; }
.voice-row.single .voice-bar { background: #b3786b; }
.voice-count {
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.voice-outlets {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}
@media (max-width: 720px) {
  .voice-row { grid-template-columns: 1fr; gap: 4px; }
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
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.article .outlet .name {
  font-weight: 600;
  color: var(--accent);
  line-height: 1.2;
}
.article .outlet .domain {
  font-size: 11px;
  color: var(--text-subtle);
}
.article .outlet .meta {
  font-size: 11px;
  color: var(--text-subtle);
}
.article .title {
  font-family: Georgia, "Times New Roman", serif;
  color: var(--text);
}
.article .title-line {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
}
.article .date {
  color: var(--text-subtle);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.article-framing-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 1px 7px;
  border-radius: 10px;
  color: #fff;
  white-space: nowrap;
  vertical-align: middle;
}
.article-framing-badge[data-framing="positive"] { background: #2563eb; }
.article-framing-badge[data-framing="neutral"] { background: #6b7280; }
.article-framing-badge[data-framing="negative"] { background: #c0392b; }
.article-framing-badge[data-framing="mixed"] { background: #7c3aed; }
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
details.claim .claim-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}
.grounding-chip {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 7px;
  border-radius: 9px;
  white-space: nowrap;
  cursor: help;
}
.grounding-chip.single_origin { background: #fef3c7; color: #92400e; }
.grounding-chip.thinly_sourced { background: #fde2e1; color: #b3261e; }

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
  grid-template-columns: 160px 1fr;
  gap: 14px;
  font-size: 14px;
  align-items: baseline;
  border-left: 2px solid var(--border);
  padding-left: 10px;
}
.citation[data-framing="positive"] { border-left-color: #2563eb; }
.citation[data-framing="neutral"] { border-left-color: #6b7280; }
.citation[data-framing="negative"] { border-left-color: #c0392b; }
.citation[data-framing="mixed"] { border-left-color: #7c3aed; }
.citation .outlet-cell {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
  font-weight: 600;
  font-size: 13px;
  flex-wrap: wrap;
}
.citation .framing-pill {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 1px 6px;
  border-radius: 8px;
  color: #fff;
}
.citation[data-framing="positive"] .framing-pill { background: #2563eb; }
.citation[data-framing="neutral"] .framing-pill { background: #6b7280; }
.citation[data-framing="negative"] .framing-pill { background: #c0392b; }
.citation[data-framing="mixed"] .framing-pill { background: #7c3aed; }
.citation blockquote mark {
  background: #fef3c7;
  color: #92400e;
  padding: 0 2px;
  border-radius: 2px;
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
.prov-pill {
  padding: 1px 7px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  cursor: help;
}
.prov-pill.primary { background: #e6f4ea; color: #1e6b32; }
.prov-pill.named { background: #e0ecfb; color: #1f3a5f; }
.prov-pill.anonymous { background: #fef3c7; color: #92400e; }
.prov-pill.media { background: #ededea; color: #6b6b66; }
.prov-pill.uncited { background: #fde2e1; color: #b3261e; }
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
.legend .legend-label {
  font-weight: 700;
  color: var(--text);
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.04em;
}
.legend.grounding-legend {
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}
.legend.grounding-legend .item { align-items: baseline; }

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

.summary {
  display: grid;
  gap: 14px;
}
.summary-tier {
  border-left: 3px solid var(--border-strong);
  padding-left: 14px;
}
.summary-tier[data-tier="universal"] { border-left-color: var(--tier-universal); }
.summary-tier[data-tier="majority"] { border-left-color: var(--tier-majority); }
.summary-tier[data-tier="disputed"] { border-left-color: var(--tier-disputed); }
.summary-tier[data-tier="attributed_only"] { border-left-color: var(--tier-attributed); }
.summary-tier[data-tier="single_sourced"] { border-left-color: var(--tier-single); }
.summary-tier h3 {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0 0 6px;
  color: var(--text-muted);
}
.summary-tier ul { margin: 0; padding: 0; list-style: none; }
.summary-tier li {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  line-height: 1.5;
  padding: 3px 0;
  display: flex;
  gap: 8px;
}
.summary-tier li::before {
  content: "•";
  color: var(--text-subtle);
  font-family: -apple-system, system-ui, sans-serif;
  flex-shrink: 0;
}
.summary-tier .source-attr {
  font-family: -apple-system, system-ui, sans-serif;
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
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

.framing-devices { display: grid; gap: 10px; }
.framing-device {
  font-size: 13px;
  line-height: 1.4;
  border-left: 2px solid var(--border-strong);
  padding-left: 10px;
}
.framing-device[data-group="vocab"] { border-left-color: #c0392b; }
.framing-device[data-group="structure"] { border-left-color: #6d28d9; }
.framing-device[data-group="meta"] { border-left-color: #d97706; }
.framing-device .device-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  flex-wrap: wrap;
  margin-bottom: 3px;
}
.framing-device .device-type-pill {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 1px 7px;
  border-radius: 8px;
  color: #fff;
  white-space: nowrap;
}
.framing-device[data-group="vocab"] .device-type-pill { background: #c0392b; }
.framing-device[data-group="structure"] .device-type-pill { background: #6d28d9; }
.framing-device[data-group="meta"] .device-type-pill { background: #d97706; }
.framing-device .device-desc {
  color: var(--text-muted);
  font-size: 12px;
  font-style: italic;
}
.framing-device blockquote {
  margin: 4px 0 0;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 13px;
  color: var(--text);
  border-left: 2px solid var(--border);
  padding-left: 10px;
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

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1a18;
    --surface: #232320;
    --border: #3a3a35;
    --border-strong: #4d4d47;
    --text: #ededeb;
    --text-muted: #b0b0a8;
    --text-subtle: #828278;
    --accent: #7aa3d8;

    --tier-universal: #4ade80;
    --tier-majority: #84cc16;
    --tier-disputed: #f87171;
    --tier-attributed: #fbbf24;
    --tier-single: #a78bfa;

    --status-asserted-bg: #1d3a25;
    --status-asserted-fg: #4ade80;
    --status-attributed-bg: #3d2e0c;
    --status-attributed-fg: #fbbf24;
    --status-contradicted-bg: #3d1816;
    --status-contradicted-fg: #f87171;
    --status-omitted-bg: #2a2a26;
    --status-omitted-fg: #6a6a64;
  }

  .matrix-head { background: #2a2a26; }
  details.tier > summary { background: #232320; }
  details.claim > summary:hover { background: #2a2a26; }
  .citations { background: #1d1d1a; }

  .lens-card[data-framing="positive"] { border-left-color: #60a5fa; }
  .lens-card[data-framing="neutral"] { border-left-color: #9ca3af; }
  .lens-card[data-framing="negative"] { border-left-color: #f87171; }
  .lens-card[data-framing="mixed"] { border-left-color: #a78bfa; }
  .lens-card[data-framing="positive"] .framing-badge { background: #2563eb; }
  .lens-card[data-framing="neutral"] .framing-badge { background: #4b5563; }
  .lens-card[data-framing="negative"] .framing-badge { background: #b91c1c; }
  .lens-card[data-framing="mixed"] .framing-badge { background: #6d28d9; }

  .article-framing-badge[data-framing="positive"] { background: #2563eb; }
  .article-framing-badge[data-framing="neutral"] { background: #4b5563; }
  .article-framing-badge[data-framing="negative"] { background: #b91c1c; }
  .article-framing-badge[data-framing="mixed"] { background: #6d28d9; }

  .citation[data-framing="positive"] { border-left-color: #60a5fa; }
  .citation[data-framing="neutral"] { border-left-color: #9ca3af; }
  .citation[data-framing="negative"] { border-left-color: #f87171; }
  .citation[data-framing="mixed"] { border-left-color: #a78bfa; }
  .citation[data-framing="positive"] .framing-pill { background: #2563eb; }
  .citation[data-framing="neutral"] .framing-pill { background: #4b5563; }
  .citation[data-framing="negative"] .framing-pill { background: #b91c1c; }
  .citation[data-framing="mixed"] .framing-pill { background: #6d28d9; }

  .syndication-badge {
    background: #1e1b4b;
    color: #c7d2fe;
    border-color: #312e81;
  }

  .loaded-term .term { color: #fbbf24; }
  .loaded-term blockquote mark,
  .citation blockquote mark {
    background: #3d2e0c;
    color: #fbbf24;
  }
  .sources-quoted .source { background: #2a2a26; }

  .summary-tier li::before { color: var(--text-subtle); }
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
    lenses: list[ArticleLens],
) -> str:
    by_outlet = {a.outlet_domain: a for a in articles}
    articles_by_id = {a.id: a for a in articles}
    lens_by_id = {l.article_id: l for l in lenses}
    rows = []
    for outlet in outlet_order:
        a = by_outlet[outlet]
        date = a.published_at.date().isoformat() if a.published_at else "—"
        title = a.title or a.url

        info = _outlet_lookup(outlet)
        friendly_name = info.name if info else outlet
        meta_line = ""
        if info:
            meta_parts = [info.country, info.outlet_type]
            if info.lean:
                meta_parts.append(info.lean)
            meta_line = (
                f'<span class="meta">{_esc(" · ".join(meta_parts))}</span>'
            )
        outlet_block = (
            f'<div class="outlet">'
            f'<span class="name">{_esc(friendly_name)}</span>'
            f'<span class="domain">{_esc(outlet)}</span>'
            f"{meta_line}"
            f"</div>"
        )

        framing_badge = ""
        lens = lens_by_id.get(a.id)
        if lens is not None:
            framing = lens.signals.headline_framing
            framing_badge = (
                f'<span class="article-framing-badge" data-framing="{framing.value}">'
                f"{_esc(_FRAMING_LABEL[framing])}"
                f"</span>"
            )

        title_inner = (
            f'<a href="{_esc(a.url)}" target="_blank" rel="noopener">{_esc(title)}</a>'
        )
        title_line = (
            f'<div class="title-line">{title_inner}{framing_badge}</div>'
        )

        partners = _syndication_partners(a, syndication_groups, articles_by_id)
        if partners:
            partners_str = ", ".join(_esc(p) for p in partners)
            title_line += (
                f'<span class="syndication-badge">'
                f"Syndicated copy — overlaps with {partners_str}"
                f"</span>"
            )

        rows.append(
            f'<div class="article">'
            f"{outlet_block}"
            f'<div class="title">{title_line}</div>'
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
    lenses_by_id: dict[str, ArticleLens],
) -> str:
    by_outlet = _coverage_by_outlet(claim.outlets)
    parts = []
    for outlet in outlet_order:
        cov = by_outlet.get(outlet)
        if cov is None:
            continue
        status_label = _STATUS_LABEL[cov.status]
        status_cls = cov.status.value

        lens = lenses_by_id.get(cov.article_id)
        framing_attr = ""
        framing_html = ""
        if lens is not None:
            framing = lens.signals.headline_framing
            framing_attr = f' data-framing="{framing.value}"'
            framing_html = (
                f'<span class="framing-pill">{_esc(_FRAMING_LABEL[framing])}</span>'
            )

        if cov.source_quote:
            terms_to_highlight: list[str] = []
            if lens is not None:
                terms_to_highlight = [
                    t.term for t in lens.signals.loaded_terms if t.term
                ]
            quote_inner = _highlight_terms(cov.source_quote, terms_to_highlight)
            quote_html = f"<blockquote>{quote_inner}</blockquote>"
        else:
            quote_html = (
                f'<blockquote class="empty">— ({status_label.lower()})</blockquote>'
            )

        prov_html = ""
        if cov.provenance is not None:
            prov_html = (
                f'<span class="prov-pill {cov.provenance.value}" '
                f'title="How this outlet sources the claim">'
                f"{_esc(_PROVENANCE_LABEL[cov.provenance])}</span>"
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

        outlet_friendly = _outlet_display_name(outlet)
        parts.append(
            f'<div class="citation"{framing_attr}>'
            f'<div class="outlet-cell">'
            f'<span>{_esc(outlet_friendly)}</span>'
            f'<span class="status-pill {status_cls}">{_esc(status_label)}</span>'
            f"{prov_html}"
            f"{framing_html}"
            f"{position_html}"
            f"</div>"
            f"<div>{quote_html}{attr_html}</div>"
            f"</div>"
        )
    return f'<div class="citations">{"".join(parts)}</div>'


def _grounding_chip(grounding: GroundingFlag | None) -> str:
    """A warning chip for thinly-sourced or single-origin claims.

    Well-grounded claims get no chip — the absence is the signal, and a
    chip on every row would just be noise.
    """
    if grounding is None or grounding == GroundingFlag.WELL_GROUNDED:
        return ""
    return (
        f'<span class="grounding-chip {grounding.value}" '
        f'title="{_esc(_GROUNDING_DESC[grounding])}">'
        f"{_esc(_GROUNDING_LABEL[grounding])}</span>"
    )


def _render_claim(
    claim: TieredClaim,
    outlet_order: list[str],
    articles_by_id: dict[str, Article],
    lenses_by_id: dict[str, ArticleLens],
) -> str:
    grid = _grid_template(len(outlet_order))
    cells = _render_cells(claim, outlet_order)
    return (
        f'<details class="claim">'
        f'<summary style="{grid}">'
        f'<span class="claim-head">'
        f'<span class="canonical">{_esc(claim.canonical_text)}</span>'
        f"{_grounding_chip(claim.grounding)}"
        f"</span>"
        f"{cells}"
        f"</summary>"
        f"{_render_citations(claim, outlet_order, articles_by_id, lenses_by_id)}"
        f"</details>"
    )


def _render_tier_section(
    tier: ConsensusTier,
    claims: list[TieredClaim],
    outlet_order: list[str],
    articles_by_id: dict[str, Article],
    lenses_by_id: dict[str, ArticleLens],
) -> str:
    rows = "".join(
        _render_claim(c, outlet_order, articles_by_id, lenses_by_id) for c in claims
    )
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
    lenses_by_id = {l.article_id: l for l in matrix.lenses}
    sections = []
    for tier in _TIER_ORDER:
        if tier in by_tier:
            sections.append(
                _render_tier_section(
                    tier, by_tier[tier], outlet_order, articles_by_id, lenses_by_id
                )
            )
    return f'<div class="matrix-frame">{_render_matrix_head(outlet_order)}{"".join(sections)}</div>'


def _render_summary(matrix: CoverageMatrix) -> str:
    if not matrix.claims:
        return ""

    # Defense in depth: never render an outlet attribution that doesn't
    # match an article in the matrix. align.py drops hallucinated
    # outlet_domain values up front, but a cached pre-fix alignment or a
    # future regression could still produce one — the render must not
    # silently surface phrases like "— example.com" as a source.
    valid_domains = {a.outlet_domain for a in matrix.articles}

    by_tier: dict[ConsensusTier, list[TieredClaim]] = defaultdict(list)
    for c in matrix.claims:
        by_tier[c.tier].append(c)

    sections = []
    for tier in _TIER_ORDER:
        claims = by_tier.get(tier, [])
        if not claims:
            continue
        bullets = []
        for c in claims:
            attr_html = ""
            if tier == ConsensusTier.SINGLE_SOURCED:
                # Identify the one outlet that has this claim
                for cov in c.outlets:
                    if cov.status == CoverageStatus.OMITTED:
                        continue
                    if cov.outlet_domain not in valid_domains:
                        continue
                    attr_html = (
                        f' <span class="source-attr">— '
                        f"{_esc(_outlet_display_name(cov.outlet_domain))}"
                        f"</span>"
                    )
                    break
            elif tier == ConsensusTier.ATTRIBUTED_ONLY:
                # List the named sources behind the claim
                attributors: list[str] = []
                for cov in c.outlets:
                    if cov.status == CoverageStatus.ATTRIBUTED and cov.attributed_to:
                        if cov.attributed_to not in attributors:
                            attributors.append(cov.attributed_to)
                if attributors:
                    attr_html = (
                        f' <span class="source-attr">— attributed to '
                        f"{_esc(', '.join(attributors))}"
                        f"</span>"
                    )
            bullets.append(
                f"<li><span>{_esc(c.canonical_text)}{attr_html}</span></li>"
            )
        sections.append(
            f'<div class="summary-tier" data-tier="{tier.value}">'
            f"<h3>{_esc(_SUMMARY_HEADINGS[tier])}</h3>"
            f'<ul>{"".join(bullets)}</ul>'
            f"</div>"
        )

    return f'<div class="summary">{"".join(sections)}</div>'


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
    status_row = f'<div class="legend">{"".join(items)}</div>'

    prov_items = ['<span class="legend-label">Sourcing</span>']
    for prov in (
        Provenance.PRIMARY,
        Provenance.NAMED,
        Provenance.ANONYMOUS,
        Provenance.MEDIA,
        Provenance.UNCITED,
    ):
        prov_items.append(
            f'<span class="item">'
            f'<span class="prov-pill {prov.value}">'
            f"{_esc(_PROVENANCE_LABEL[prov])}</span>"
            f"</span>"
        )
    prov_row = f'<div class="legend">{"".join(prov_items)}</div>'

    grounding_items = []
    for flag in (GroundingFlag.SINGLE_ORIGIN, GroundingFlag.THINLY_SOURCED):
        grounding_items.append(
            f'<span class="item">'
            f'<span class="grounding-chip {flag.value}">'
            f"{_esc(_GROUNDING_LABEL[flag])}</span>"
            f"<span>{_esc(_GROUNDING_DESC[flag])}</span>"
            f"</span>"
        )
    grounding_row = f'<div class="legend grounding-legend">{"".join(grounding_items)}</div>'

    return status_row + prov_row + grounding_row


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


def _highlight_terms(sentence: str, terms: list[str]) -> str:
    """Wrap every occurrence of any term from `terms` in <mark>.

    Longer terms are tried first so a phrase like "rule of law" doesn't get
    pre-empted by partial matches on "rule" or "law".
    """
    cleaned = [t for t in terms if t]
    if not cleaned:
        return _esc(sentence)
    sorted_terms = sorted(set(cleaned), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(t) for t in sorted_terms), re.IGNORECASE)
    parts: list[str] = []
    last = 0
    for m in pattern.finditer(sentence):
        parts.append(_esc(sentence[last : m.start()]))
        parts.append(f"<mark>{_esc(sentence[m.start() : m.end()])}</mark>")
        last = m.end()
    parts.append(_esc(sentence[last:]))
    return "".join(parts)


def _highlight_term(sentence: str, term: str) -> str:
    """Single-term highlight helper retained for the lens cards."""
    return _highlight_terms(sentence, [term] if term else [])


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


def _render_framing_devices(devices: list[FramingDevice]) -> str:
    if not devices:
        return ""
    rows = []
    for d in devices:
        group = _DEVICE_GROUP.get(d.device_type, "meta")
        label = _DEVICE_LABEL.get(d.device_type, d.device_type.value)
        if d.in_sentence:
            blockquote_html = f"<blockquote>{_esc(d.in_sentence)}</blockquote>"
        else:
            blockquote_html = ""
        rows.append(
            f'<div class="framing-device" data-group="{group}">'
            f'<div class="device-head">'
            f'<span class="device-type-pill">{_esc(label)}</span>'
            f'<span class="device-desc">{_esc(d.description)}</span>'
            f"</div>"
            f"{blockquote_html}"
            f"</div>"
        )
    return (
        f'<div class="lens-section-label">Framing devices ({len(devices)})</div>'
        f'<div class="framing-devices">{"".join(rows)}</div>'
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
        f'<span class="outlet">{_esc(_outlet_display_name(lens.outlet_domain))}</span>'
        f'<span class="framing-badge">{_esc(_FRAMING_LABEL[lens.signals.headline_framing])}</span>'
        f"</div>"
        f'<p class="stance">{_esc(lens.signals.stance_summary)}</p>'
        f"{_render_loaded_terms(lens.signals.loaded_terms)}"
        f"{_render_framing_devices(lens.signals.framing_devices)}"
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


def _render_sample_banner(matrix: CoverageMatrix) -> str:
    """Describe the shape of the sampled outlets, honestly and up front.

    A coverage analysis can only reflect the outlets it drew from. If the
    sample is all one lean, all commercial-mainstream, or mostly
    unclassified, the reader needs to know that before reading any
    "every outlet agreed" line — otherwise the report quietly implies a
    breadth it doesn't have.
    """
    domains: list[str] = []
    seen: set[str] = set()
    for a in matrix.articles:
        if a.outlet_domain not in seen:
            seen.add(a.outlet_domain)
            domains.append(a.outlet_domain)
    n = len(domains)
    if n == 0:
        return ""

    infos = {d: _outlet_lookup(d) for d in domains}
    known = [i for i in infos.values() if i is not None]
    untagged = [d for d, i in infos.items() if i is None]

    lean_counts = Counter(i.lean for i in known if i.lean)
    tier_counts = Counter(i.tier for i in known)
    countries = sorted({i.country for i in known})

    lean_parts = [f"{lean_counts[l]} {l}" for l in SPECTRUM_ORDER if lean_counts[l]]
    lean_str = ", ".join(lean_parts) if lean_parts else "none rated"
    tier_str = (
        ", ".join(f"{c} {t}" for t, c in tier_counts.most_common())
        if tier_counts
        else "none classified"
    )

    stat_bits = [
        f"<strong>{n}</strong> outlet{'' if n == 1 else 's'}",
        f"lean: {_esc(lean_str)}",
        f"institutional tier: {_esc(tier_str)}",
    ]
    if countries:
        stat_bits.append(f"countries: {_esc(', '.join(countries))}")
    stats_html = " · ".join(stat_bits)

    notes: list[str] = []
    # The whole tool is a cross-outlet comparison; with only one outlet
    # there is nothing to compare. Say so loudly — otherwise the
    # "Universal" tier reads as consensus when it's really just one
    # voice asserted as fact.
    if n == 1:
        notes.append(
            "Only one outlet is in this sample. Cross-outlet tiers and the "
            "coverage matrix can't say anything about consensus or omission "
            "with a single voice — what follows is effectively a per-article "
            "framing analysis. Re-run with more sources to compare across "
            "outlets."
        )

    left_present = bool(lean_counts["left"] or lean_counts["center-left"])
    right_present = bool(lean_counts["center-right"] or lean_counts["right"])
    if known and n > 1:
        if not left_present and not right_present:
            notes.append(
                "Every rated outlet sits at the centre — neither the left "
                "nor the right of the spectrum is represented."
            )
        elif not right_present:
            notes.append(
                "No outlet right of centre is represented; on the "
                "left–right axis this sample leans left."
            )
        elif not left_present:
            notes.append(
                "No outlet left of centre is represented; on the "
                "left–right axis this sample leans right."
            )

    non_mainstream = sum(c for t, c in tier_counts.items() if t != "mainstream")
    if known and non_mainstream == 0 and n > 1:
        notes.append(
            "Every classified outlet is commercial-mainstream — no "
            "independent, public-broadcast, advocacy, or state outlet is "
            "represented. Agreement across this sample can still reflect "
            "assumptions shared across the mainstream press."
        )

    if untagged:
        verb = "is" if len(untagged) == 1 else "are"
        notes.append(
            f"{len(untagged)} of the {n} outlets {verb} not in the registry, "
            "so their lean and institutional tier are unknown and they were "
            "excluded from the figures above."
        )

    if len(countries) == 1:
        notes.append(
            f"All classified outlets are based in one country "
            f"({_esc(countries[0])}); non-domestic perspectives are absent."
        )

    notes_html = ""
    if notes:
        items = "".join(f"<li>{_esc(t)}</li>" for t in notes)
        notes_html = f'<ul class="sample-notes">{items}</ul>'

    return (
        '<div class="sample-banner">'
        '<div class="sample-banner-head">About this sample</div>'
        f'<div class="sample-stats">{stats_html}</div>'
        f"{notes_html}"
        '<div class="sample-caveat">'
        "A coverage analysis can only reflect the outlets it sampled. Read "
        "the agreements, disputes, and omissions below in light of who is — "
        "and who is not — represented here."
        "</div>"
        "</div>"
    )


def _render_table_of_contents(matrix: CoverageMatrix) -> str:
    """Jump list to each section, mirroring the sections render_html builds.

    The report is long once ownership, voices, and per-article framing all
    fire. The TOC is rendered right after the sample banner so the reader
    can land on the section they care about without scrolling through
    every other one.
    """
    items: list[tuple[str, str]] = [("articles", "Articles")]
    if matrix.articles:
        items.append(("ownership", "Who owns these outlets"))
    if matrix.claims:
        items.append(("summary", "Story at a Glance"))
        items.append(("matrix", "Coverage Matrix"))
    if matrix.lenses:
        items.append(("voices", "Voices in the story"))
        items.append(("framing", "Per-Article Framing"))
    items.append(("profile", "Outlet Coverage Profile"))

    links = "".join(
        f'<a href="#{_id}">{_esc(label)}</a>'
        for _id, label in items
    )
    return (
        '<nav class="toc">'
        '<span class="toc-label">Jump to</span>'
        f'<div class="toc-links">{links}</div>'
        "</nav>"
    )


_OWNERSHIP_INTRO = (
    "Manufacturing Consent calls ownership the propaganda model's first "
    "filter — who owns a paper shapes who its editors answer to and what "
    "they may quietly avoid covering. This section shows the corporate "
    "or family parent for every outlet in the sample, grouped together "
    "where two or more outlets share an ultimate owner. \"Independent\" "
    "outlets are tagged too: trusts, cooperatives, nonprofits, and "
    "reader-funded operations sit alongside the corporate-owned ones so "
    "the distinction is visible at a glance."
)


def _render_ownership_section(matrix: CoverageMatrix) -> str:
    """Group outlets in this sample by ultimate owner.

    Surfaces ownership concentration (e.g. \"five of these are News Corp
    papers\") and tags the independents (Scott Trust, nonprofits,
    cooperatives) honestly so the reader can weigh independence claims.
    """
    if not matrix.articles:
        return ""

    seen: set[str] = set()
    domains: list[str] = []
    for a in matrix.articles:
        if a.outlet_domain not in seen:
            seen.add(a.outlet_domain)
            domains.append(a.outlet_domain)
    summary = _ownership_summary(domains)
    n = summary["n_outlets"]

    # Sort groups largest-first; unknowns last (we mark them with the
    # __unknown__ prefix to make this easy).
    sorted_groups = sorted(
        summary["by_owner_key"].items(),
        key=lambda kv: (kv[0].startswith("__unknown__"), -kv[1]["n"], kv[1]["label"]),
    )

    largest_share = summary["largest_share"]
    largest_pct = largest_share / n if n else 0
    # Pick a single sentence to name the most-concentrated owner.
    top_group = sorted_groups[0][1] if sorted_groups else None
    if top_group and not sorted_groups[0][0].startswith("__unknown__") and top_group["n"] > 1:
        concentration_sentence = (
            f"The most concentrated single owner in this sample is "
            f"<strong>{_esc(top_group['label'])}</strong>, holding "
            f"{top_group['n']} of {n} outlets ({largest_pct:.0%})."
        )
    else:
        concentration_sentence = (
            "No two outlets in this sample share an ultimate owner — "
            "concentration is not a concern here."
        )

    n_known_owners = summary["n_owners"] - summary["n_unknown"]
    stats_html = (
        f"<div class=\"ownership-stats\"><strong>{n}</strong> outlet"
        f"{'' if n == 1 else 's'} · "
        f"<strong>{n_known_owners}</strong> distinct known owner"
        f"{'' if n_known_owners == 1 else 's'}"
        f" · {summary['n_unknown']} unclassified</div>"
        f"<p class=\"section-note\">{concentration_sentence}</p>"
    )

    group_html_parts = []
    for key, group in sorted_groups:
        is_unknown = key.startswith("__unknown__")
        css_class = "owner-group" + (" unknown" if is_unknown else "")
        outlet_lis = "".join(
            f"<li><span class=\"outlet-name\">{_esc(_outlet_display_name(d))}</span>"
            f" <span class=\"outlet-domain\">{_esc(d)}</span></li>"
            for d in group["domains"]
        )
        # Highlight the count for groups that actually share an owner.
        share_html = ""
        if not is_unknown and group["n"] > 1:
            share_html = (
                f"<span class=\"owner-share\">"
                f"{group['n']} of {n} outlets ({group['n'] / n:.0%})"
                f"</span>"
            )
        group_html_parts.append(
            f"<div class=\"{css_class}\">"
            f"<div class=\"owner-label\">{_esc(group['label'])}{share_html}</div>"
            f"<ul class=\"owner-outlets\">{outlet_lis}</ul>"
            f"</div>"
        )

    groups_html = "".join(group_html_parts)
    return (
        '<section id="ownership" class="ownership">'
        "<h2>Who owns these outlets</h2>"
        f"<p class=\"section-note\">{_OWNERSHIP_INTRO}</p>"
        f"{stats_html}"
        f"<div class=\"ownership-groups\">{groups_html}</div>"
        "</section>"
    )


_VOICES_INTRO = (
    "Named sources quoted across this sample, with the outlets that quoted "
    "each. A source quoted by most outlets shapes what the \"official\" "
    "account of the story looks like; a source quoted by only one or two "
    "shapes the margins. Sources quoted by NO outlet in your sample don't "
    "appear here — they are visible only by the questions you find yourself "
    "asking. Use this section to spot one-source consensus and structural "
    "absences."
)


def _normalize_source_name(name: str) -> str:
    """Lowercase + collapse punctuation/whitespace for grouping near-duplicates.

    The lens prompt asks the model to name sources, but the same person
    can come back as \"Keir Starmer\", \"Sir Keir Starmer\", \"PM Keir
    Starmer\", or \"Starmer\". Even simple lowercasing collapses many of
    those into one another for aggregation purposes; we keep the
    longest original spelling as the display label so the reader sees a
    full name rather than the shortest reference.
    """
    return " ".join(name.lower().split())


def _render_voices_section(matrix: CoverageMatrix, outlet_order: list[str]) -> str:
    """Aggregate `sources_quoted` across all lenses; show who's quoted by whom."""
    if not matrix.lenses:
        return ""

    # name_key -> { display, outlets: set[str] }
    voices: dict[str, dict] = {}
    for lens in matrix.lenses:
        for source in lens.signals.sources_quoted:
            source = (source or "").strip()
            if not source:
                continue
            key = _normalize_source_name(source)
            if not key:
                continue
            entry = voices.setdefault(key, {"display": source, "outlets": set()})
            entry["outlets"].add(lens.outlet_domain)
            # Keep the longest spelling as the display label.
            if len(source) > len(entry["display"]):
                entry["display"] = source

    if not voices:
        return ""

    n_outlets = len(outlet_order)
    rows = sorted(
        voices.values(),
        key=lambda v: (-len(v["outlets"]), v["display"].lower()),
    )

    # Headline metric: how many sources reached >half the outlets vs only one.
    n_majority = sum(1 for r in rows if len(r["outlets"]) > n_outlets / 2)
    n_single = sum(1 for r in rows if len(r["outlets"]) == 1)
    stats_html = (
        f"<div class=\"voices-stats\"><strong>{len(rows)}</strong> distinct "
        f"named sources · <strong>{n_majority}</strong> quoted by a majority "
        f"of outlets · <strong>{n_single}</strong> quoted by only one</div>"
    )

    row_parts = []
    for entry in rows:
        n = len(entry["outlets"])
        pct = n / n_outlets if n_outlets else 0
        outlets_html = ", ".join(
            _esc(_outlet_display_name(d))
            for d in outlet_order if d in entry["outlets"]
        )
        share_class = "majority" if n > n_outlets / 2 else (
            "single" if n == 1 else "minority"
        )
        row_parts.append(
            f"<div class=\"voice-row {share_class}\">"
            f"<div class=\"voice-name\">{_esc(entry['display'])}</div>"
            f"<div class=\"voice-share\">"
            f"<div class=\"voice-bar\" style=\"width: {max(pct * 100, 6):.0f}%\"></div>"
            f"<span class=\"voice-count\">{n} of {n_outlets}</span>"
            f"</div>"
            f"<div class=\"voice-outlets\">{outlets_html}</div>"
            f"</div>"
        )

    return (
        '<section id="voices" class="voices">'
        "<h2>Voices in the story</h2>"
        f"<p class=\"section-note\">{_VOICES_INTRO}</p>"
        f"{stats_html}"
        f"<div class=\"voices-list\">{''.join(row_parts)}</div>"
        "</section>"
    )


def render_html(matrix: CoverageMatrix) -> str:
    outlet_order = _outlet_order(matrix.articles)
    n_articles = len(matrix.articles)
    n_outlets = len(outlet_order)
    n_claims = len(matrix.claims)
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    voices_section = _render_voices_section(matrix, outlet_order)

    framing_section = ""
    if matrix.lenses:
        framing_section = (
            '<section id="framing">'
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
        f"{_render_sample_banner(matrix)}"
        f"{_render_table_of_contents(matrix)}"
        '<section id="articles">'
        "<h2>Articles</h2>"
        f"{_render_articles(matrix.articles, outlet_order, matrix.syndication_groups, matrix.lenses)}"
        "</section>"
        f"{_render_ownership_section(matrix)}"
        '<section id="summary">'
        "<h2>Story at a Glance</h2>"
        f"{_render_summary(matrix)}"
        "</section>"
        '<section id="matrix">'
        "<h2>Coverage Matrix</h2>"
        '<p class="section-note">'
        "Each row is a claim some outlet made. The bold line is a plain "
        "descriptive handle used only to group outlets covering the same "
        "point — it is not a neutral or verified version of the claim. "
        "Expand any row to read the verbatim wording each outlet actually "
        "used, side by side."
        "</p>"
        f"{_render_matrix(matrix, outlet_order)}"
        f"{_render_legend()}"
        "</section>"
        f"{voices_section}"
        f"{framing_section}"
        '<section id="profile">'
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
