"""Programmatic WCAG contrast audit for the report's pills and chips.

Catches future colour-tweak regressions: every hard-coded
background+foreground pair that carries text gets its WCAG 2.1
contrast ratio computed against the WCAG AA threshold (4.5:1 for
normal text, 3:1 for large text).

The pairs are listed inline rather than parsed out of the CSS string,
because the CSS uses CSS variables for some colours and parsing those
would re-implement the variable resolver. The trade-off is that
adding a new pill requires adding it to this list; the trade-off is
deliberate — that gate is exactly the regression we want.
"""

from __future__ import annotations

import pytest


def _srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return (
        0.2126 * _srgb_to_linear(r)
        + 0.7152 * _srgb_to_linear(g)
        + 0.0722 * _srgb_to_linear(b)
    )


def _contrast_ratio(fg: str, bg: str) -> float:
    l1, l2 = _luminance(fg), _luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# (label, foreground, background, threshold).
# Threshold 4.5 for normal-size text. 3.0 for pill labels in some cases
# is permissible under WCAG AA for large text (>=14pt bold or 18pt) but
# we hold the stricter 4.5 line where the type is small.
_LIGHT_MODE_PAIRS: list[tuple[str, str, str, float]] = [
    # Provenance pills (small text, must meet 4.5:1).
    ("prov-pill.primary", "#1e6b32", "#e6f4ea", 4.5),
    ("prov-pill.named", "#1f3a5f", "#e0ecfb", 4.5),
    ("prov-pill.anonymous", "#7c2d12", "#fef3c7", 4.5),
    ("prov-pill.media", "#404040", "#e6e6e2", 4.5),
    ("prov-pill.uncited", "#991f15", "#fde2e1", 4.5),

    # Grounding chips.
    ("grounding-chip.single_origin", "#7c2d12", "#fef3c7", 4.5),
    ("grounding-chip.thinly_sourced", "#991f15", "#fde2e1", 4.5),

    # Ownership concentration badge.
    ("owner-share", "#7c2d12", "#fef3c7", 4.5),

    # Outlet meta pills.
    ("outlet-listed", "#1f3a5f", "#e0ecfb", 4.5),

    # Framing badges (white on coloured background — large bold text).
    ("article-framing-badge[positive]", "#ffffff", "#2563eb", 4.5),
    ("article-framing-badge[neutral]", "#ffffff", "#4b5563", 4.5),
    ("article-framing-badge[negative]", "#ffffff", "#c0392b", 4.5),
    ("article-framing-badge[mixed]", "#ffffff", "#6d28d9", 4.5),

    # Status pill backgrounds (legend + citation pills).
    ("status-pill.asserted", "#1e6b32", "#e6f4ea", 4.5),
    ("status-pill.attributed", "#92400e", "#fef3c7", 4.5),
    ("status-pill.contradicted", "#b3261e", "#fde2e1", 4.5),
]


_DARK_MODE_PAIRS: list[tuple[str, str, str, float]] = [
    ("prov-pill.primary [dark]", "#4ade80", "#1d3a25", 4.5),
    ("prov-pill.named [dark]", "#93c5fd", "#1c2e4d", 4.5),
    ("prov-pill.anonymous [dark]", "#fbbf24", "#3d2e0c", 4.5),
    ("prov-pill.media [dark]", "#d1d1c9", "#2a2a26", 4.5),
    ("prov-pill.uncited [dark]", "#fca5a5", "#3d1816", 4.5),

    ("grounding-chip.single_origin [dark]", "#fbbf24", "#3d2e0c", 4.5),
    ("grounding-chip.thinly_sourced [dark]", "#fca5a5", "#3d1816", 4.5),

    ("owner-share [dark]", "#fbbf24", "#3d2e0c", 4.5),
    ("outlet-listed [dark]", "#93c5fd", "#1c2e4d", 4.5),

    ("framing-badge[neutral] [dark]", "#ffffff", "#4b5563", 4.5),
]


@pytest.mark.parametrize("label,fg,bg,threshold", _LIGHT_MODE_PAIRS)
def test_light_mode_contrast_meets_aa(label, fg, bg, threshold):
    ratio = _contrast_ratio(fg, bg)
    assert ratio >= threshold, (
        f"{label}: contrast {ratio:.2f}:1 between {fg} and {bg} "
        f"fails WCAG AA threshold {threshold}:1"
    )


@pytest.mark.parametrize("label,fg,bg,threshold", _DARK_MODE_PAIRS)
def test_dark_mode_contrast_meets_aa(label, fg, bg, threshold):
    ratio = _contrast_ratio(fg, bg)
    assert ratio >= threshold, (
        f"{label}: contrast {ratio:.2f}:1 between {fg} and {bg} "
        f"fails WCAG AA threshold {threshold}:1"
    )


def test_audit_includes_every_pill_class_in_css():
    """Catch the case where a new pill type is added to render.py without
    being added to the audit list."""
    import re
    from pathlib import Path

    css_text = Path("src/news_lens/render.py").read_text()
    declared_classes: set[str] = set()
    # Find every class name in the form ".foo-pill.bar" used in a
    # background-or-color CSS rule. Just spot-check the pill/chip
    # families we care about.
    for family in ("prov-pill", "grounding-chip"):
        matches = re.findall(rf"\.{family}\.(\w+)\s*\{{", css_text)
        for m in matches:
            declared_classes.add(f"{family}.{m}")

    audited = {label.split(" ")[0] for label, *_ in _LIGHT_MODE_PAIRS}
    missing = declared_classes - audited
    assert not missing, (
        "These pill classes exist in the CSS but aren't in the contrast "
        f"audit: {sorted(missing)}. Add them to tests/test_a11y.py."
    )
