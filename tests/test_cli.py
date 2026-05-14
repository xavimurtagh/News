"""CLI flag wiring tests.

These exercise argument parsing and backend selection without spinning up
an HTTP server or calling out to any real LLM. We patch the OpenAICompatible
constructor so we can read what arguments it would have received.
"""

from __future__ import annotations

import argparse
import sys
from unittest.mock import patch

from news_lens.__main__ import _build_backend, _strip_line_continuations, _validate_url


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
    assert captured["model"] == "qwen3:8b"


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


def test_validate_url_strips_whitespace():
    assert _validate_url("  https://example.com  ") == "https://example.com"


def test_validate_url_accepts_http():
    assert _validate_url("http://example.com") == "http://example.com"
    assert _validate_url("https://example.com") == "https://example.com"


def test_validate_url_rejects_lone_backslash():
    """The Codespace paper-cut: shell line continuation passed `\\` as an arg."""
    try:
        _validate_url("\\")
    except SystemExit as e:
        msg = str(e)
        assert "not a valid URL" in msg
        assert "line continuation" in msg
        return
    raise AssertionError("expected SystemExit for a lone backslash")


def test_validate_url_rejects_bare_word():
    try:
        _validate_url("not-a-url")
    except SystemExit:
        return
    raise AssertionError("expected SystemExit for a bare word")


def test_validate_url_rejects_empty():
    try:
        _validate_url("   ")
    except SystemExit:
        return
    raise AssertionError("expected SystemExit for empty URL")


def test_strip_line_continuations_removes_lone_backslash():
    """The Windows-shell paper-cut: `\\` between flags as an arg."""
    cleaned, n = _strip_line_continuations(
        ["--search", "topic", "\\", "--ollama", "\\", "--html", "out.html"]
    )
    assert cleaned == ["--search", "topic", "--ollama", "--html", "out.html"]
    assert n == 2


def test_strip_line_continuations_passes_through_real_args():
    """Args that aren't lone backslashes are preserved exactly."""
    argv = ["--search", "trump tariffs", "--max-sources", "6", "--ollama"]
    cleaned, n = _strip_line_continuations(argv)
    assert cleaned == argv
    assert n == 0


def test_strip_line_continuations_preserves_paths_with_backslashes():
    """Windows paths embed backslashes but aren't lone backslashes."""
    argv = ["--urls-file", "C:\\Users\\x\\urls.txt"]
    cleaned, n = _strip_line_continuations(argv)
    assert cleaned == argv
    assert n == 0


def test_strip_line_continuations_handles_double_backslash():
    """Some shells double up the backslash — handle that too."""
    cleaned, n = _strip_line_continuations(["--search", "x", "\\\\", "--ollama"])
    assert cleaned == ["--search", "x", "--ollama"]
    assert n == 1
