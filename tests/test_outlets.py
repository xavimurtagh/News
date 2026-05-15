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


def test_lean_field_present_for_well_known_outlets():
    """Major outlets should have a lean rating; spot-check a few."""
    for domain in ("nytimes.com", "wsj.com", "foxnews.com", "msnbc.com"):
        info = lookup(domain)
        assert info is not None
        assert info.lean is not None, f"{domain} should have a lean rating"


def test_lean_values_are_in_spectrum():
    """Every assigned lean must be one of the canonical spectrum values."""
    from news_lens.outlets import SPECTRUM_ORDER, _REGISTRY
    valid = set(SPECTRUM_ORDER) | {None}
    for domain, info in _REGISTRY.items():
        assert info.lean in valid, (
            f"{domain} has invalid lean {info.lean!r}; "
            f"must be one of {SPECTRUM_ORDER} or None"
        )


def test_lean_omitted_for_contested_outlets():
    """Outlets without a clear consensus should be left None, not assigned."""
    # Al Jazeera's lean is contested (different desks, different framings);
    # the registry deliberately leaves it None.
    info = lookup("aljazeera.com")
    assert info is not None
    assert info.lean is None


def test_spectrum_includes_both_ends():
    """Sanity: at least one outlet on each end so balanced selection has options."""
    from news_lens.outlets import _REGISTRY
    leans = {info.lean for info in _REGISTRY.values() if info.lean is not None}
    assert "left" in leans
    assert "right" in leans
    assert "center" in leans


def test_tier_defaults_to_mainstream():
    """An outlet constructed without an explicit tier is mainstream."""
    info = lookup("nytimes.com")
    assert info is not None
    assert info.tier == "mainstream"


def test_tier_values_are_valid():
    """Every assigned tier must be one of the canonical institutional tiers."""
    from news_lens.outlets import INSTITUTIONAL_TIERS, _REGISTRY
    valid = set(INSTITUTIONAL_TIERS)
    for domain, info in _REGISTRY.items():
        assert info.tier in valid, (
            f"{domain} has invalid tier {info.tier!r}; "
            f"must be one of {INSTITUTIONAL_TIERS}"
        )


def test_registry_spans_multiple_tiers():
    """The institutional axis needs more than one tier represented."""
    from news_lens.outlets import _REGISTRY
    tiers = {info.tier for info in _REGISTRY.values()}
    for expected in ("mainstream", "public", "independent", "advocacy", "state"):
        assert expected in tiers, f"no outlet tagged tier={expected!r}"


def test_public_broadcasters_tagged():
    """Licence-fee / appropriation-funded broadcasters carry the public tier."""
    for domain in ("bbc.com", "npr.org", "pbs.org", "cbc.ca"):
        info = lookup(domain)
        assert info is not None
        assert info.tier == "public", f"{domain} should be tier=public"

