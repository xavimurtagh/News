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
    # The synthetic _matrix has a single universal claim. The universal
    # tier is framed as shared, unexamined assumptions rather than
    # "what everyone agreed on".
    assert "Shared assumptions" in html_doc
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


def _banner_matrix(domains: list[str]) -> CoverageMatrix:
    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    articles = [
        Article(
            id=f"a{i}", url=f"https://{d}/x", outlet_domain=d,
            title=f"Story {i}", fetched_at=now, body="b", paragraph_count=2,
        )
        for i, d in enumerate(domains)
    ]
    return CoverageMatrix(articles=articles, claims=[])


def test_sample_banner_flags_left_skewed_sample():
    """A sample with no right-of-centre outlet says so."""
    from news_lens.render import _render_sample_banner

    banner = _render_sample_banner(
        _banner_matrix(["theguardian.com", "msnbc.com", "vox.com"])
    )
    assert "About this sample" in banner
    assert "leans left" in banner


def test_sample_banner_flags_all_mainstream():
    """A sample with only mainstream-tier outlets is flagged."""
    from news_lens.render import _render_sample_banner

    banner = _render_sample_banner(
        _banner_matrix(["nytimes.com", "wsj.com", "foxnews.com"])
    )
    assert "commercial-mainstream" in banner


def test_sample_banner_flags_untagged_outlets():
    """Outlets not in the registry are surfaced as unclassified."""
    from news_lens.render import _render_sample_banner

    banner = _render_sample_banner(
        _banner_matrix(["nytimes.com", "some-random-blog.example"])
    )
    assert "not in the registry" in banner


def test_sample_banner_appears_in_full_render():
    html_doc = render_html(_banner_matrix(["nytimes.com", "foxnews.com"]))
    assert "About this sample" in html_doc


def test_summary_skips_unknown_outlet_domains():
    """A coverage entry with an outlet_domain not in the article set is dropped."""
    from news_lens.render import _render_summary

    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    article = Article(
        id="a1", url="https://real-outlet.com/x", outlet_domain="real-outlet.com",
        title="t", fetched_at=now, body="b", paragraph_count=2,
    )
    # A single-sourced canonical claim, but the asserting outlet domain
    # doesn't match the one real article — render must NOT show it.
    claim = TieredClaim(
        canonical_text="Some single-sourced fact.",
        tier=ConsensusTier.SINGLE_SOURCED,
        outlets=[
            OutletCoverage(
                outlet_domain="example.com", article_id="a1",
                status=CoverageStatus.ASSERTED,
                source_quote="x", position=1,
            ),
        ],
    )
    matrix = CoverageMatrix(articles=[article], claims=[claim])
    html = _render_summary(matrix)
    assert "example.com" not in html
    # The claim text is still in the summary, just without the bad attribution.
    assert "Some single-sourced fact." in html


def test_sample_banner_flags_single_outlet_runs():
    """A 1-outlet sample must say loudly that no comparison is possible."""
    from news_lens.render import _render_sample_banner

    banner = _render_sample_banner(_banner_matrix(["nytimes.com"]))
    assert "Only one outlet" in banner
    # Spectrum-gap notes should NOT fire alongside the single-outlet note.
    assert "leans left" not in banner
    assert "commercial-mainstream" not in banner


def _multi_outlet_matrix(domains: list[str]) -> CoverageMatrix:
    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    articles = [
        Article(
            id=f"a{i}", url=f"https://{d}/x", outlet_domain=d,
            title=f"{d} story", fetched_at=now, body="b", paragraph_count=2,
        )
        for i, d in enumerate(domains)
    ]
    return CoverageMatrix(articles=articles, claims=[])


def test_ownership_section_groups_shared_owners():
    """Murdoch-controlled News Corp papers collapse into one owner group."""
    html_doc = render_html(_multi_outlet_matrix(
        ["wsj.com", "nypost.com", "thetimes.com", "theguardian.com"]
    ))
    assert "Who owns these outlets" in html_doc
    # News Corp owns 3 of 4 outlets in this sample.
    assert "News Corp" in html_doc
    assert "3 of 4 outlets" in html_doc
    # Guardian appears in its own (Scott Trust) group.
    assert "Scott Trust" in html_doc


def test_ownership_section_flags_unknown_outlets():
    """An outlet not in the registry shows up as 'Unknown' rather than being silently dropped."""
    html_doc = render_html(_multi_outlet_matrix([
        "nytimes.com", "some-random-blog.example",
    ]))
    assert "Unknown" in html_doc
    assert "some-random-blog.example" in html_doc


def test_ownership_section_states_concentration_metric():
    """The headline sentence quantifies the largest single owner."""
    html_doc = render_html(_multi_outlet_matrix([
        "wsj.com", "foxnews.com", "thetimes.com", "nytimes.com",
    ]))
    # WSJ + Times share News Corp (both Murdoch). Fox is a separate
    # corporate entity (also Murdoch). NYT stands alone.
    # The most-concentrated single corporate parent owns 2 of 4.
    assert "2 of 4" in html_doc


def _lensed_matrix() -> CoverageMatrix:
    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    arts = [
        Article(id="a1", url="https://nytimes.com/x", outlet_domain="nytimes.com",
                title="t1", fetched_at=now, body="b", paragraph_count=2),
        Article(id="a2", url="https://wsj.com/x", outlet_domain="wsj.com",
                title="t2", fetched_at=now, body="b", paragraph_count=2),
        Article(id="a3", url="https://theguardian.com/x", outlet_domain="theguardian.com",
                title="t3", fetched_at=now, body="b", paragraph_count=2),
    ]
    def _lens(aid, dom, sources):
        return ArticleLens(article_id=aid, outlet_domain=dom,
            signals=LensSignals(headline_framing=HeadlineFraming.NEUTRAL,
                                loaded_terms=[], sources_quoted=sources,
                                stance_summary="s"))
    lenses = [
        _lens("a1", "nytimes.com", ["Keir Starmer", "Wes Streeting", "Andy Burnham"]),
        _lens("a2", "wsj.com", ["Keir Starmer", "keir starmer", "Treasury source"]),
        _lens("a3", "theguardian.com", ["Wes Streeting", "Andy Burnham", "Paul Nowak"]),
    ]
    return CoverageMatrix(articles=arts, claims=[], lenses=lenses)


def test_voices_section_normalizes_and_aggregates():
    html_doc = render_html(_lensed_matrix())
    assert "Voices in the story" in html_doc
    # Same source quoted twice in one article (Keir Starmer + lowercase variant)
    # collapses to ONE row, quoted by 2 outlets total.
    assert html_doc.count("Keir Starmer") >= 1
    # 5 distinct sources total — Starmer, Streeting, Burnham, Nowak, Treasury source.
    assert "<strong>5</strong> distinct named sources" in html_doc
    # 3 quoted by majority (Starmer, Streeting, Burnham at 2 of 3 each)
    assert "<strong>3</strong> quoted by a majority of outlets" in html_doc
    assert "<strong>2</strong> quoted by only one" in html_doc


def test_voices_section_omitted_when_no_lenses():
    """No lens data means no voices section."""
    matrix = _multi_outlet_matrix(["nytimes.com", "wsj.com"])
    html_doc = render_html(matrix)
    assert "Voices in the story" not in html_doc


def test_table_of_contents_links_to_sections():
    """The TOC links to whatever sections are present in the report."""
    matrix = _lensed_matrix()
    html_doc = render_html(matrix)
    assert 'class="toc"' in html_doc
    assert 'href="#articles"' in html_doc
    assert 'href="#ownership"' in html_doc
    assert 'href="#profile"' in html_doc
    # No claims in this matrix -> no jumps for summary / matrix.
    assert 'href="#summary"' not in html_doc
    # Lenses present -> voices and framing are linked.
    assert 'href="#voices"' in html_doc
    assert 'href="#framing"' in html_doc


def test_table_of_contents_omits_links_for_absent_sections():
    """When there are no lenses, the TOC drops voices and framing entries."""
    html_doc = render_html(_multi_outlet_matrix(["nytimes.com", "wsj.com"]))
    assert 'href="#voices"' not in html_doc
    assert 'href="#framing"' not in html_doc
    # Articles + ownership + profile still present.
    assert 'href="#articles"' in html_doc
    assert 'href="#ownership"' in html_doc
    assert 'href="#profile"' in html_doc


def _syndication_matrix() -> CoverageMatrix:
    """Three Newsquest papers running identical wire copy, plus a Guardian outlier."""
    from news_lens.models import SyndicationGroup

    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    arts = [
        Article(id="a1", url="https://theguardian.com/x", outlet_domain="theguardian.com",
                title="Guardian", fetched_at=now, body="b", paragraph_count=2),
        Article(id="a2", url="https://theargus.co.uk/x", outlet_domain="theargus.co.uk",
                title="wire", fetched_at=now, body="b", paragraph_count=2),
        Article(id="a3", url="https://salisburyjournal.co.uk/x", outlet_domain="salisburyjournal.co.uk",
                title="wire", fetched_at=now, body="b", paragraph_count=2),
    ]
    syn = SyndicationGroup(article_ids=["a2", "a3"], similarity=0.95)
    oc = [
        OutletCoverage(outlet_domain="theguardian.com", article_id="a1",
                       status=CoverageStatus.ASSERTED, source_quote="Guardian sentence.", position=1),
        OutletCoverage(outlet_domain="theargus.co.uk", article_id="a2",
                       status=CoverageStatus.ASSERTED, source_quote="Wire sentence.", position=1),
        OutletCoverage(outlet_domain="salisburyjournal.co.uk", article_id="a3",
                       status=CoverageStatus.ASSERTED, source_quote="Wire sentence.", position=1),
    ]
    claim = TieredClaim(canonical_text="X happened.", tier=ConsensusTier.MAJORITY, outlets=oc)
    return CoverageMatrix(articles=arts, claims=[claim], syndication_groups=[syn])


def test_matrix_collapses_syndicated_outlets_into_one_column():
    html_doc = render_html(_syndication_matrix())
    # The matrix head: 2 columns now, not 3 — the Newsquest pair collapses.
    matrix_head_html = html_doc.split('matrix-head" style=')[1].split("</div></div>")[0]
    assert matrix_head_html.count("outlet-col") == 2
    # The rep column shows the +N badge.
    assert "+1" in html_doc
    # Citation block names the other syndicated outlet.
    assert "Also asserted by" in html_doc
    assert "salisburyjournal.co.uk" in html_doc


def test_matrix_unchanged_when_no_syndication():
    """A matrix with no syndication groups renders one column per outlet, as before."""
    html_doc = render_html(_multi_outlet_matrix(["nytimes.com", "wsj.com", "theguardian.com"]))
    matrix_head_html = html_doc.split('matrix-head" style=')[1].split("</div></div>")[0]
    assert matrix_head_html.count("outlet-col") == 3
    assert "+1" not in matrix_head_html  # no syndication badge


def test_matrix_shows_internal_divergence_within_syndication_group():
    """If one Newsquest paper contradicts the wire, the cell flags it."""
    from news_lens.models import SyndicationGroup

    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    arts = [
        Article(id="a1", url="https://a.example/x", outlet_domain="a.example",
                title="t", fetched_at=now, body="b", paragraph_count=2),
        Article(id="a2", url="https://b.example/x", outlet_domain="b.example",
                title="t", fetched_at=now, body="b", paragraph_count=2),
    ]
    syn = SyndicationGroup(article_ids=["a1", "a2"], similarity=0.92)
    oc = [
        OutletCoverage(outlet_domain="a.example", article_id="a1",
                       status=CoverageStatus.ASSERTED,
                       source_quote="Q.", position=1),
        OutletCoverage(outlet_domain="b.example", article_id="a2",
                       status=CoverageStatus.CONTRADICTED,
                       source_quote="Not Q.", position=1),
    ]
    claim = TieredClaim(canonical_text="X.", tier=ConsensusTier.DISPUTED, outlets=oc)
    matrix = CoverageMatrix(articles=arts, claims=[claim], syndication_groups=[syn])
    html_doc = render_html(matrix)
    # The cell carries the mixed-syndication outline class.
    assert "mixed-syndication" in html_doc
    # The citation block names the diverging member explicitly.
    assert "diverges" in html_doc


def _omissions_matrix() -> CoverageMatrix:
    """A matrix carrying a small OmissionAnalysis for render testing."""
    from news_lens.models import (
        OmissionAnalysis, OmissionCategory, StructuralOmission,
    )

    base = _multi_outlet_matrix(["nytimes.com", "wsj.com", "theguardian.com"])
    base.omissions = OmissionAnalysis(omissions=[
        StructuralOmission(
            category=OmissionCategory.SOURCE_CLASS,
            description="No frontline aid worker quoted in any article.",
            why_relevant="A humanitarian story without frontline accounts elides distribution realities.",
        ),
        StructuralOmission(
            category=OmissionCategory.COUNTERFACT,
            description="None of the articles cite the 2024 OECD report on the policy's net effect.",
            why_relevant="The OECD figures directly complicate the consensus framing.",
        ),
    ])
    return base


def test_omissions_section_renders_when_analysis_present():
    html_doc = render_html(_omissions_matrix())
    assert "Structural omissions" in html_doc
    assert "frontline aid worker" in html_doc
    assert "OECD" in html_doc
    # Categories show as labels.
    assert "Source class not quoted" in html_doc
    assert "Counter-fact elided" in html_doc
    # TOC links to the section.
    assert 'href="#omissions"' in html_doc


def test_omissions_section_hidden_when_no_analysis():
    """Matrix without OmissionAnalysis renders no omissions section."""
    html_doc = render_html(_multi_outlet_matrix(["nytimes.com", "wsj.com"]))
    assert "Structural omissions" not in html_doc
    assert 'href="#omissions"' not in html_doc


def test_omissions_section_shows_sample_caveat_only():
    """When the LLM couldn't ground the analysis, the section shows the caveat."""
    from news_lens.models import OmissionAnalysis

    matrix = _multi_outlet_matrix(["nytimes.com", "wsj.com", "theguardian.com"])
    matrix.omissions = OmissionAnalysis(
        omissions=[],
        sample_caveat="Sample too narrow to support structural-omissions claims.",
    )
    html_doc = render_html(matrix)
    assert "Structural omissions" in html_doc
    assert "Sample too narrow" in html_doc
    # No omission cards, just the caveat.
    assert 'class="omission-card"' not in html_doc
