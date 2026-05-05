"""Tests for syndication detection and tier collapsing."""

from __future__ import annotations

from datetime import datetime, timezone

from news_lens.models import (
    Article,
    ConsensusTier,
    CoverageStatus,
    OutletCoverage,
    SyndicationGroup,
)
from news_lens.pipeline import _collapse_syndication, _compute_tier
from news_lens.syndication import _jaccard, _sentences, detect_syndication


_NOW = datetime(2026, 5, 4, tzinfo=timezone.utc)


def _article(aid: str, body: str, outlet: str = "x.com") -> Article:
    return Article(
        id=aid, url=f"https://{outlet}/a/{aid}", outlet_domain=outlet,
        title=None, fetched_at=_NOW, body=body, paragraph_count=1,
    )


def _cov(aid: str, status: CoverageStatus) -> OutletCoverage:
    return OutletCoverage(outlet_domain="x.com", article_id=aid, status=status)


def test_sentences_filters_short_fragments():
    body = "Yes. Short. The President signed Executive Order 14123 at a Rose Garden ceremony on Saturday."
    sents = _sentences(body)
    # "Yes." and "Short." are too short to count; only the long sentence remains.
    assert len(sents) == 1
    assert "The President signed" in next(iter(sents))


def test_jaccard_disjoint_is_zero():
    assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_identical_is_one():
    assert _jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_detect_syndication_finds_overlapping_pair():
    shared = (
        "U.S. President signed an executive order on border policy on Saturday, the White House said. "
        "The order takes effect immediately, the White House said. "
        "A senior administration official said the policy could affect up to 5 million people."
    )
    a = _article("a", shared)
    b = _article("b", "Different intro paragraph from outlet B. " + shared)
    c = _article(
        "c",
        "Completely independent reporting on the same event with no shared sentences. "
        "The administration faces legal challenges from civil liberties groups. "
        "Lawmakers debated the policy for months before the signing.",
    )
    groups = detect_syndication([a, b, c])
    assert len(groups) == 1
    assert set(groups[0].article_ids) == {"a", "b"}
    assert groups[0].similarity > 0.5


def test_detect_syndication_emits_no_groups_for_distinct_articles():
    a = _article("a", "The President signed Executive Order 14123 at a Rose Garden ceremony on Saturday afternoon, capping months of debate.")
    b = _article("b", "Markets reacted with a muted decline as analysts focused on the order's labor-market implications and corporate costs.")
    assert detect_syndication([a, b]) == []


def test_collapse_syndication_treats_group_as_one_voice():
    """3 articles, 2 syndicated → 2 independent voices."""
    coverage = [
        _cov("a", CoverageStatus.ASSERTED),
        _cov("b", CoverageStatus.ASSERTED),
        _cov("c", CoverageStatus.ASSERTED),
    ]
    groups = [SyndicationGroup(article_ids=["a", "b"], similarity=0.9)]
    collapsed, n_voices = _collapse_syndication(coverage, 3, groups)
    assert n_voices == 2
    assert len(collapsed) == 2


def test_collapse_picks_strongest_status():
    """Inside a syndication group, strongest non-omitted status wins."""
    coverage = [
        _cov("a", CoverageStatus.OMITTED),
        _cov("b", CoverageStatus.ASSERTED),
    ]
    groups = [SyndicationGroup(article_ids=["a", "b"], similarity=0.9)]
    collapsed, n_voices = _collapse_syndication(coverage, 2, groups)
    assert n_voices == 1
    assert collapsed[0].status == CoverageStatus.ASSERTED


def test_contradiction_in_group_dominates():
    """If one outlet edited the wire to contradict, the edit IS the news."""
    coverage = [
        _cov("a", CoverageStatus.ASSERTED),
        _cov("b", CoverageStatus.CONTRADICTED),
    ]
    groups = [SyndicationGroup(article_ids=["a", "b"], similarity=0.9)]
    collapsed, _ = _collapse_syndication(coverage, 2, groups)
    assert collapsed[0].status == CoverageStatus.CONTRADICTED


def test_tier_universal_collapses_syndicated_voices():
    """3 outlets, 2 syndicated, all assert → UNIVERSAL because 2 independent voices both assert."""
    coverage = [
        _cov("a", CoverageStatus.ASSERTED),
        _cov("b", CoverageStatus.ASSERTED),
        _cov("c", CoverageStatus.ASSERTED),
    ]
    groups = [SyndicationGroup(article_ids=["a", "b"], similarity=0.9)]
    assert _compute_tier(coverage, 3, groups) is ConsensusTier.UNIVERSAL


def test_tier_no_syndication_uses_full_count():
    """Without syndication groups, behavior matches the original sync semantics."""
    coverage = [
        _cov("a", CoverageStatus.ASSERTED),
        _cov("b", CoverageStatus.ASSERTED),
        _cov("c", CoverageStatus.OMITTED),
    ]
    assert _compute_tier(coverage, 3) is ConsensusTier.MAJORITY
    assert _compute_tier(coverage, 3, []) is ConsensusTier.MAJORITY
