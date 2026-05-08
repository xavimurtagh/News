"""Tests for news discovery and source selection.

Network-touching code (the actual GDELT fetch) is mocked. The selection
logic is pure and tested directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from news_lens.discover import NewsResult, _normalize_domain, select_diverse


def _r(domain: str, title: str = "") -> NewsResult:
    return NewsResult(
        title=title or f"Story from {domain}",
        url=f"https://{domain}/article/x",
        outlet_domain=domain,
        published_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
    )


def test_normalize_domain_strips_www_and_lowercases():
    assert _normalize_domain("www.NYTimes.com") == "nytimes.com"
    assert _normalize_domain("BBC.co.uk ") == "bbc.co.uk"
    assert _normalize_domain("reuters.com") == "reuters.com"


def test_select_diverse_one_per_outlet():
    """Multiple results from the same outlet collapse to one."""
    results = [
        _r("nytimes.com", "first NYT story"),
        _r("nytimes.com", "second NYT story"),
        _r("bbc.com"),
        _r("reuters.com"),
    ]
    selected = select_diverse(results, n=5)
    domains = [r.outlet_domain for r in selected]
    assert domains == ["nytimes.com", "bbc.com", "reuters.com"]


def test_select_diverse_caps_at_n():
    """Stops at n even when more outlets are available."""
    results = [_r(d) for d in ("nytimes.com", "bbc.com", "reuters.com", "wsj.com")]
    selected = select_diverse(results, n=2)
    assert len(selected) == 2


def test_select_diverse_prioritizes_known_outlets():
    """Known outlets come first; unknowns fill remaining slots only after."""
    results = [
        _r("blog-noone-knows.example"),
        _r("another-unknown.example"),
        _r("nytimes.com"),
        _r("bbc.com"),
    ]
    selected = select_diverse(results, n=4)
    # Known outlets (NYT, BBC) should appear before the unknown ones.
    known_first = [r.outlet_domain for r in selected[:2]]
    assert "nytimes.com" in known_first
    assert "bbc.com" in known_first


def test_select_diverse_require_known_drops_unknowns():
    results = [
        _r("blog-noone-knows.example"),
        _r("another-unknown.example"),
        _r("nytimes.com"),
    ]
    selected = select_diverse(results, n=5, require_known=True)
    domains = [r.outlet_domain for r in selected]
    assert domains == ["nytimes.com"]


def test_select_diverse_preserves_order_within_pass():
    """GDELT's relevance ordering is preserved among same-tier results."""
    results = [
        _r("reuters.com"),
        _r("bbc.com"),
        _r("nytimes.com"),
    ]
    selected = select_diverse(results, n=3)
    assert [r.outlet_domain for r in selected] == [
        "reuters.com",
        "bbc.com",
        "nytimes.com",
    ]


def test_balance_spectrum_picks_one_per_bucket():
    """With one result per spectrum bucket available, balanced selection picks all five."""
    results = [
        _r("msnbc.com"),       # left
        _r("nytimes.com"),     # center-left
        _r("reuters.com"),     # center
        _r("nypost.com"),      # center-right
        _r("foxnews.com"),     # right
    ]
    selected = select_diverse(results, n=5, balance_spectrum=True)
    assert {r.outlet_domain for r in selected} == {
        "msnbc.com", "nytimes.com", "reuters.com", "nypost.com", "foxnews.com",
    }


def test_balance_spectrum_distributes_when_one_bucket_dominates():
    """If one bucket has many results and others have few, we still hit other buckets first."""
    # Five center-left outlets but only one right outlet.
    # Balanced selection should pick the right outlet before piling on center-left.
    results = [
        _r("nytimes.com"),     # center-left
        _r("washingtonpost.com"),  # center-left
        _r("cnn.com"),         # center-left
        _r("politico.com"),    # center-left
        _r("foxnews.com"),     # right
    ]
    selected = select_diverse(results, n=2, balance_spectrum=True)
    domains = {r.outlet_domain for r in selected}
    # Whichever single center-left was picked, foxnews must be in the result.
    assert "foxnews.com" in domains


def test_balance_spectrum_handles_no_lean_outlets():
    """Outlets without a lean rating should be selectable but picked last."""
    results = [
        _r("aljazeera.com"),  # no lean assigned in registry
        _r("nytimes.com"),     # center-left
        _r("foxnews.com"),     # right
    ]
    # n=3 should pull all three, with leaned outlets first.
    selected = select_diverse(results, n=3, balance_spectrum=True)
    assert {r.outlet_domain for r in selected} == {
        "aljazeera.com", "nytimes.com", "foxnews.com",
    }
    # First two picks must be the leaned ones.
    first_two = {r.outlet_domain for r in selected[:2]}
    assert "aljazeera.com" not in first_two


def test_balance_spectrum_require_known_drops_unleaned():
    """Even an outlet that's in the registry but has no lean is dropped under require_known."""
    # require_known in the spectrum path means "must have a lean value".
    # Wait — actually the docstring says require_known stops after Pass 1
    # which is the leaned bucket. Let's verify.
    results = [
        _r("aljazeera.com"),  # registered but no lean
        _r("nytimes.com"),     # center-left
    ]
    selected = select_diverse(
        results, n=5, balance_spectrum=True, require_known=True
    )
    # require_known should stop after the leaned-bucket pass; aljazeera dropped.
    assert [r.outlet_domain for r in selected] == ["nytimes.com"]
