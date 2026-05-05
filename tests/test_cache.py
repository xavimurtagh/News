"""Tests for the on-disk JSON cache."""

from __future__ import annotations

from pathlib import Path

from news_lens.cache import Cache


def test_set_get_roundtrip(tmp_path: Path):
    cache = Cache(tmp_path)
    cache.set("ns", {"hello": "world"}, "key1")
    assert cache.get("ns", "key1") == {"hello": "world"}


def test_miss_returns_none(tmp_path: Path):
    cache = Cache(tmp_path)
    assert cache.get("ns", "missing") is None


def test_prompt_change_invalidates(tmp_path: Path):
    """A different prompt hash gives a different cache key."""
    cache = Cache(tmp_path)
    cache.set("ns", {"v": 1}, "id1", "prompt-hash-A")
    assert cache.get("ns", "id1", "prompt-hash-A") == {"v": 1}
    assert cache.get("ns", "id1", "prompt-hash-B") is None


def test_namespaces_isolated(tmp_path: Path):
    cache = Cache(tmp_path)
    cache.set("a", "in_a", "key")
    cache.set("b", "in_b", "key")
    assert cache.get("a", "key") == "in_a"
    assert cache.get("b", "key") == "in_b"


def test_persists_across_instances(tmp_path: Path):
    """Cache files survive across new Cache() instances."""
    Cache(tmp_path).set("ns", {"persisted": True}, "id")
    assert Cache(tmp_path).get("ns", "id") == {"persisted": True}
