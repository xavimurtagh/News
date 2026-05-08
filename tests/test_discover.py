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
