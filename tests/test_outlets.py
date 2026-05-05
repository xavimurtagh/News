"""Tests for the outlet registry."""

from __future__ import annotations

from news_lens.outlets import display_name, lookup


def test_lookup_known_outlet():
    info = lookup("nytimes.com")
    assert info is not None
    assert info.name == "The New York Times"
    assert info.country == "US"
    assert info.outlet_type == "newspaper"


def test_lookup_unknown_outlet_returns_none():
    assert lookup("unknown-blog.example") is None


def test_display_name_falls_back_to_domain():
    assert display_name("unknown-blog.example") == "unknown-blog.example"


def test_display_name_returns_friendly_for_known():
    assert display_name("reuters.com") == "Reuters"


def test_registry_includes_wire_services():
    """The wire-syndication detector relies on knowing AP/Reuters/AFP exist."""
    for wire in ("apnews.com", "reuters.com", "afp.com"):
        info = lookup(wire)
        assert info is not None
        assert info.outlet_type == "wire"


def test_country_diversity():
    """Registry should span multiple countries to support international comparison."""
    countries = {info.country for d in (
        "nytimes.com", "bbc.com", "lemonde.fr", "spiegel.de",
        "globeandmail.com", "abc.net.au", "japantimes.co.jp",
    ) if (info := lookup(d)) is not None}
    assert len(countries) >= 5
