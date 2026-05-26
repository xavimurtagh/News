"""Tests for news discovery and source selection.

Network-touching code (the actual GDELT fetch) is mocked. The selection
logic is pure and tested directly.
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from news_lens.cache import Cache
from news_lens.discover import (
    NewsResult,
    _fetch_gdelt,
    _normalize_domain,
    _parse_retry_after,
    _serialize_result,
    _deserialize_result,
    select_diverse,
)


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


def test_parse_retry_after_numeric_seconds():
    assert _parse_retry_after("5") == 5.0
    assert _parse_retry_after("0.5") == 0.5


def test_parse_retry_after_garbage_returns_none():
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("") is None
    # HTTP-date format isn't parsed; we fall back to exponential backoff.
    assert _parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None


def test_parse_retry_after_negative_clamped_to_zero():
    assert _parse_retry_after("-3") == 0.0


def _make_429(retry_after: str | None = None) -> urllib.error.HTTPError:
    """Construct a synthetic HTTPError matching urlopen's failure shape."""
    import email.message

    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="https://api.gdeltproject.org/api/v2/doc/doc",
        code=429,
        msg="Too Many Requests",
        hdrs=headers,  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )


def test_fetch_gdelt_retries_on_429_then_succeeds():
    """First call 429s, second call succeeds; we get the success body."""
    success_body = json.dumps({"articles": [{"url": "x", "domain": "y.com"}]}).encode()
    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _make_429(retry_after="0.01")

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *args):
                return None

            def read(self_inner):
                return success_body

        return _Resp()

    sleeps: list[float] = []
    with patch("news_lens.discover.urllib.request.urlopen", fake_urlopen):
        result = _fetch_gdelt("x", 5, max_retries=3, sleep=sleeps.append)

    assert call_count["n"] == 2
    assert result == {"articles": [{"url": "x", "domain": "y.com"}]}
    # Slept for the Retry-After value, not the default backoff.
    assert sleeps == [0.01]


def test_fetch_gdelt_gives_up_after_max_retries():
    def always_429(req, timeout):
        raise _make_429(retry_after="0.01")

    with patch("news_lens.discover.urllib.request.urlopen", always_429):
        try:
            _fetch_gdelt("x", 5, max_retries=2, sleep=lambda _: None)
        except RuntimeError as e:
            assert "rate-limiting" in str(e).lower()
            return
    raise AssertionError("expected RuntimeError after exhausting retries")


def test_fetch_gdelt_propagates_non_retryable():
    """A 404 isn't worth retrying; raise immediately."""
    not_found = urllib.error.HTTPError(
        url="x", code=404, msg="Not Found", hdrs=None, fp=io.BytesIO(b"")
    )

    def always_404(req, timeout):
        raise not_found

    with patch("news_lens.discover.urllib.request.urlopen", always_404):
        try:
            _fetch_gdelt("x", 5, max_retries=4, sleep=lambda _: None)
        except urllib.error.HTTPError as e:
            assert e.code == 404
            return
    raise AssertionError("expected HTTPError 404")


def test_search_uses_cache_on_repeat(tmp_path: Path):
    """Second search with the same query and the same cache skips the network."""
    import asyncio

    from news_lens.discover import search

    cached_payload = {
        "articles": [
            {
                "url": "https://nytimes.com/a",
                "domain": "nytimes.com",
                "title": "Headline",
                "seendate": "20260508T120000Z",
                "sourcecountry": "United States",
            }
        ]
    }
    call_count = {"n": 0}

    def fake_fetch(query, max_records, days=14, now=None, max_retries=4, sleep=None):
        call_count["n"] += 1
        return cached_payload

    cache = Cache(tmp_path)
    with patch("news_lens.discover._fetch_gdelt", fake_fetch):
        first = asyncio.run(search("topic", max_results=5, cache=cache))
        second = asyncio.run(search("topic", max_results=5, cache=cache))

    assert call_count["n"] == 1  # second call hits the cache
    assert [r.outlet_domain for r in first] == ["nytimes.com"]
    assert [r.outlet_domain for r in second] == ["nytimes.com"]


def test_serialize_deserialize_roundtrip():
    """Datetimes round-trip through the cache via isoformat."""
    r = NewsResult(
        title="t",
        url="https://x/y",
        outlet_domain="x",
        published_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        country="GB",
    )
    restored = _deserialize_result(_serialize_result(r))
    assert restored.title == r.title
    assert restored.url == r.url
    assert restored.outlet_domain == r.outlet_domain
    assert restored.published_at == r.published_at
    assert restored.country == r.country


def test_serialize_handles_no_publish_date():
    r = NewsResult(title="t", url="u", outlet_domain="x")
    restored = _deserialize_result(_serialize_result(r))
    assert restored.published_at is None


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


def test_balance_tier_picks_one_per_tier():
    """With one outlet per institutional tier, tier-balanced picks all five."""
    results = [
        _r("nytimes.com"),     # mainstream
        _r("bbc.com"),         # public
        _r("propublica.org"),  # independent
        _r("breitbart.com"),   # advocacy
        _r("rt.com"),          # state
    ]
    selected = select_diverse(results, n=5, balance_tier=True)
    assert {r.outlet_domain for r in selected} == {
        "nytimes.com", "bbc.com", "propublica.org", "breitbart.com", "rt.com",
    }


def test_balance_tier_distributes_when_one_tier_dominates():
    """Non-mainstream tiers get reached before mainstream is piled on."""
    results = [
        _r("nytimes.com"),     # mainstream
        _r("wsj.com"),         # mainstream
        _r("foxnews.com"),     # mainstream
        _r("cnn.com"),         # mainstream
        _r("propublica.org"),  # independent
    ]
    selected = select_diverse(results, n=2, balance_tier=True)
    domains = {r.outlet_domain for r in selected}
    # Whichever single mainstream outlet was picked, the independent must be in.
    assert "propublica.org" in domains


def test_balance_tier_unknown_outlets_picked_last():
    """Registered outlets fill tier buckets first; unknowns come after."""
    results = [
        _r("unknown-site.example"),
        _r("nytimes.com"),     # mainstream
        _r("bbc.com"),         # public
    ]
    selected = select_diverse(results, n=3, balance_tier=True)
    assert {r.outlet_domain for r in selected} == {
        "unknown-site.example", "nytimes.com", "bbc.com",
    }
    first_two = {r.outlet_domain for r in selected[:2]}
    assert "unknown-site.example" not in first_two


def test_balance_tier_require_known_drops_unknowns():
    results = [
        _r("unknown-site.example"),
        _r("nytimes.com"),
    ]
    selected = select_diverse(
        results, n=5, balance_tier=True, require_known=True
    )
    assert [r.outlet_domain for r in selected] == ["nytimes.com"]


def test_fetch_gdelt_default_window_includes_dates():
    """The default 14-day window passes start/end datetime to GDELT."""
    captured: dict = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *args):
                return None

            def read(self_inner):
                return b'{"articles": []}'

        return _Resp()

    fixed_now = datetime(2026, 5, 20, 12, 0, 0)
    with patch("news_lens.discover.urllib.request.urlopen", fake_urlopen):
        _fetch_gdelt("hello", 5, days=14, now=fixed_now, sleep=lambda _: None)

    url = captured["url"]
    assert "startdatetime=20260506120000" in url
    assert "enddatetime=20260520120000" in url


def test_fetch_gdelt_days_none_disables_window():
    """`days=None` omits the GDELT date params entirely."""
    captured: dict = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *args):
                return None

            def read(self_inner):
                return b'{"articles": []}'

        return _Resp()

    with patch("news_lens.discover.urllib.request.urlopen", fake_urlopen):
        _fetch_gdelt("hello", 5, days=None, sleep=lambda _: None)

    url = captured["url"]
    assert "startdatetime" not in url
    assert "enddatetime" not in url


def test_search_cache_keys_separate_by_window(tmp_path: Path):
    """Different `days` windows must not collide in the search cache."""
    import asyncio as _asyncio

    from news_lens.cache import Cache
    from news_lens.discover import search

    call_count = {"n": 0}

    def fake_fetch(query, max_records, days=14, now=None, max_retries=4, sleep=None):
        call_count["n"] += 1
        return {"articles": [{"url": f"https://x/{days}", "domain": "x.com"}]}

    cache = Cache(tmp_path)
    with patch("news_lens.discover._fetch_gdelt", fake_fetch):
        _asyncio.run(search("topic", max_results=5, days=7, cache=cache))
        _asyncio.run(search("topic", max_results=5, days=14, cache=cache))
        # Repeat the 7-day window — should hit the cache, not the network.
        _asyncio.run(search("topic", max_results=5, days=7, cache=cache))

    assert call_count["n"] == 2  # two distinct windows hit the network once each
