"""Tests for ingestion helpers."""

from __future__ import annotations

from news_lens.ingest import _outlet_domain, _paragraph_count


def test_outlet_domain_strips_www():
    assert _outlet_domain("https://www.nytimes.com/2026/x") == "nytimes.com"


def test_outlet_domain_lowercases():
    assert _outlet_domain("https://EXAMPLE.com/x") == "example.com"


def test_outlet_domain_keeps_subdomains():
    assert _outlet_domain("https://reuters.com/world/x") == "reuters.com"
    assert _outlet_domain("https://blogs.example.com/x") == "blogs.example.com"


def test_paragraph_count_double_newline_split():
    body = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    assert _paragraph_count(body) == 3


def test_paragraph_count_ignores_empty():
    body = "First.\n\n\n\n   \n\nSecond."
    assert _paragraph_count(body) == 2


def test_paragraph_count_minimum_one():
    assert _paragraph_count("") == 1
    assert _paragraph_count("A single line, no double newline.") == 1
