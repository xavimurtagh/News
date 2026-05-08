"""Tests for the HTML renderer."""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser

from news_lens.models import (
    Article,
    ArticleLens,
    ConsensusTier,
    CoverageMatrix,
    CoverageStatus,
    HeadlineFraming,
    LensSignals,
    LoadedTerm,
    OutletCoverage,
    TieredClaim,
)
from news_lens.render import _highlight_term, _highlight_terms, _position_label, render_html


def _well_formed(html_doc: str) -> tuple[list[str], list[str]]:
    """Return (unclosed_tags, errors) for a parsed HTML document."""

    class Checker(HTMLParser):
        VOID = {"br", "meta", "img", "input", "link", "hr"}

        def __init__(self) -> None:
            super().__init__()
            self.stack: list[str] = []
            self.errors: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag not in self.VOID:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if not self.stack:
                self.errors.append(f"close {tag} with empty stack")
                return
            if self.stack[-1] != tag:
                self.errors.append(f"mismatch: open {self.stack[-1]} vs close {tag}")
            else:
                self.stack.pop()

    checker = Checker()
    checker.feed(html_doc)
    return checker.stack, checker.errors


def test_position_label_bands_by_thirds():
    assert _position_label(None, 10) == ""
    assert _position_label(0, 10) == ""
    assert _position_label(1, 0) == "¶ 1"
    assert _position_label(1, 1) == "¶ 1/1"
    assert _position_label(2, 2) == "¶ 2/2"
    assert _position_label(1, 9) == "¶ 1/9 · early"
    assert _position_label(3, 9) == "¶ 3/9 · early"
    assert _position_label(4, 9) == "¶ 4/9 · middle"
    assert _position_label(7, 9) == "¶ 7/9 · late"
    assert _position_label(9, 9) == "¶ 9/9 · late"


def test_highlight_term_wraps_each_occurrence():
    html_str = _highlight_term("The sweeping order was sweeping in scope.", "sweeping")
    assert html_str.count("<mark>") == 2
    assert html_str.count("</mark>") == 2


def test_highlight_term_escapes_html():
    html_str = _highlight_term("Said <b>this</b> is fine.", "fine")
    assert "<b>" not in html_str
    assert "&lt;b&gt;" in html_str


def test_highlight_terms_handles_multiple():
    html_str = _highlight_terms("The bold action took crackdown to a new level.", ["bold action", "crackdown"])
    assert html_str.count("<mark>") == 2


def test_highlight_terms_prefers_longer_overlap():
    """A longer phrase should win over a shorter substring it contains."""
    html_str = _highlight_terms("rule of law was restored", ["rule of law", "law"])
    # We expect one mark wrapping "rule of law", not two overlapping marks.
    assert html_str.count("<mark>") == 1
    assert "<mark>rule of law</mark>" in html_str


def test_highlight_terms_empty_terms():
    assert _highlight_terms("hello world", []) == "hello world"


def _matrix(with_lens: bool = True) -> CoverageMatrix:
    now = datetime(2026, 5, 4, 16, 30, tzinfo=timezone.utc)
    a1 = Article(
        id="a1", url="https://nytimes.com/x", outlet_domain="nytimes.com",
        title="Headline A", fetched_at=now, body="p1\n\np2\n\np3",
        paragraph_count=3,
    )
    a2 = Article(
        id="a2", url="https://wsj.com/x", outlet_domain="wsj.com",
        title="Headline B", fetched_at=now, body="p1\n\np2",
        paragraph_count=2,
    )
    claim = TieredClaim(
        canonical_text="Something happened.",
        tier=ConsensusTier.UNIVERSAL,
        outlets=[
            OutletCoverage(
                outlet_domain="nytimes.com", article_id="a1",
                status=CoverageStatus.ASSERTED,
                source_quote="Something happened.", position=1,
            ),
            OutletCoverage(
                outlet_domain="wsj.com", article_id="a2",
                status=CoverageStatus.ASSERTED,
                source_quote="Something happened.", position=2,
            ),
        ],
    )
    lenses: list[ArticleLens] = []
    if with_lens:
        lenses = [
            ArticleLens(
                article_id="a1", outlet_domain="nytimes.com",
                signals=LensSignals(
                    headline_framing=HeadlineFraming.NEGATIVE,
                    loaded_terms=[],
                    sources_quoted=["aide"],
                    stance_summary="Critical of subject.",
                ),
            ),
        ]
    return CoverageMatrix(articles=[a1, a2], claims=[claim], lenses=lenses)


def test_render_produces_well_formed_html():
    html_doc = render_html(_matrix())
    unclosed, errors = _well_formed(html_doc)
    assert unclosed == []
    assert errors == []


def test_render_includes_expected_sections():
    html_doc = render_html(_matrix())
    assert "<h1>News Lens — Coverage Matrix</h1>" in html_doc
    assert "Articles" in html_doc
    assert "Story at a Glance" in html_doc
    assert "Coverage Matrix" in html_doc
    assert "Per-Article Framing" in html_doc
    assert "Outlet Coverage Profile" in html_doc


def test_summary_groups_by_tier():
    html_doc = render_html(_matrix())
    # The synthetic _matrix has a single universal claim.
    assert "What every outlet agreed on" in html_doc
    assert "summary-tier" in html_doc
    # Ensure the canonical text appears in the summary section, not just the matrix.
    assert html_doc.count("Something happened.") >= 2  # summary + matrix


def test_render_omits_framing_section_when_no_lenses():
    html_doc = render_html(_matrix(with_lens=False))
    assert "Per-Article Framing" not in html_doc
    # The other sections still render.
    assert "Coverage Matrix" in html_doc


def test_render_shows_position_labels():
    html_doc = render_html(_matrix())
    # 3-paragraph article with claim at position 1 → early band
    assert "¶ 1/3 · early" in html_doc
    # 2-paragraph article: too short for thirds, just show position/total
    assert "¶ 2/2" in html_doc


def test_render_outputs_one_lens_card_per_outlet_with_lens():
    html_doc = render_html(_matrix())
    assert html_doc.count('class="lens-card"') == 1


def test_render_outputs_three_fingerprint_rows():
    """Two articles → two outlets → two fingerprint rows."""
    html_doc = render_html(_matrix())
    assert html_doc.count('class="fingerprint"') == 2


def test_render_framing_devices():
    """When a lens carries framing devices, they show as labelled blocks."""
    from news_lens.models import FramingDevice, FramingDeviceType

    matrix = _matrix()
    # Inject a framing device on the existing NYT lens.
    matrix.lenses[0].signals.framing_devices = [
        FramingDevice(
            device_type=FramingDeviceType.SELECTIVE_HEDGING,
            description="Hedge words applied only to one side's claims.",
            in_sentence="Critics allege X while supporters confirm Y.",
        ),
        FramingDevice(
            device_type=FramingDeviceType.OMISSION_FLAG,
            description="No mention of the counter-statistic.",
            in_sentence="",
        ),
    ]
    html_doc = render_html(matrix)
    assert "Selective hedging" in html_doc
    assert "Omission" in html_doc
    assert html_doc.count('class="framing-device"') == 2
    # Selective hedging is a "meta" group; its border should be amber.
    assert 'data-group="meta"' in html_doc
