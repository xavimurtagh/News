"""CLI flag wiring tests.

These exercise argument parsing and backend selection without spinning up
an HTTP server or calling out to any real LLM. We patch the OpenAICompatible
constructor so we can read what arguments it would have received.
"""

from __future__ import annotations

import argparse
import sys
from unittest.mock import patch

from news_lens.__main__ import _build_backend


def _ns(**overrides):
    base = dict(
        backend="claude",
        ollama=False,
        base_url=None,
        model=None,
        api_key_env=None,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_ollama_shortcut_picks_default_base_url_and_model():
    captured = {}

    class _Stub:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.name = "stub"

    with patch(
        "news_lens.backends.openai_compatible.OpenAICompatibleBackend", _Stub
    ):
        _build_backend(_ns(ollama=True))

    assert captured["base_url"] == "http://localhost:11434/v1"
    assert captured["model"] == "llama3.2:3b"


def test_ollama_shortcut_accepts_model_override():
    captured = {}

    class _Stub:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.name = "stub"

    with patch(
        "news_lens.backends.openai_compatible.OpenAICompatibleBackend", _Stub
    ):
        _build_backend(_ns(ollama=True, model="llama3.1:8b"))

    assert captured["model"] == "llama3.1:8b"
    assert captured["base_url"] == "http://localhost:11434/v1"


def test_openai_compatible_requires_base_url():
    try:
        _build_backend(_ns(backend="openai-compatible", model="llama3.1:8b"))
    except SystemExit as e:
        assert "--base-url" in str(e)
        return
    raise AssertionError("expected SystemExit when --base-url missing")


def test_openai_compatible_requires_model():
    try:
        _build_backend(
            _ns(
                backend="openai-compatible",
                base_url="http://localhost:11434/v1",
            )
        )
    except SystemExit as e:
        assert "--model" in str(e)
        return
    raise AssertionError("expected SystemExit when --model missing")


def test_claude_backend_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        _build_backend(_ns(backend="claude"))
    except SystemExit as e:
        assert "ANTHROPIC_API_KEY" in str(e)
        # The error message should also point at the local-LLM escape hatch.
        assert "ollama" in str(e).lower()
        return
    raise AssertionError("expected SystemExit when API key absent")
