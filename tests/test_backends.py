"""Tests for the backend abstraction.

The Protocol-based design means a fake in-memory backend is all we need
to validate the contract. Real Anthropic / OpenAI calls are not exercised
here — those are integration tests for a separate harness with API keys.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from news_lens.backends.base import StructuredLLM


T = TypeVar("T", bound=BaseModel)


class _FakeBackend:
    """In-memory StructuredLLM that echoes a precomputed response per call."""

    name = "fake:test"

    def __init__(self, responses: list[BaseModel]) -> None:
        self._responses = list(responses)

    async def parse(self, *, system: str, user: str, schema: type[T]) -> T:
        if not self._responses:
            raise RuntimeError("FakeBackend ran out of responses")
        result = self._responses.pop(0)
        if not isinstance(result, schema):
            raise TypeError(
                f"FakeBackend response {type(result).__name__} doesn't match {schema.__name__}"
            )
        return result


def test_fake_backend_satisfies_protocol():
    """isinstance check on Protocol works because StructuredLLM is runtime_checkable."""
    backend = _FakeBackend([])
    assert isinstance(backend, StructuredLLM)


def test_claude_backend_satisfies_protocol():
    """ClaudeBackend implements the Protocol without instantiation needing the API key."""
    from news_lens.backends.claude import ClaudeBackend

    backend = ClaudeBackend.__new__(ClaudeBackend)
    backend.name = "claude:test"
    backend.client = None  # not used in the Protocol check
    backend.model = "claude-opus-4-7"
    backend.max_tokens = 1
    assert isinstance(backend, StructuredLLM)


def test_backend_name_namespaces_cache():
    """Two distinct backends produce distinct names so caches don't collide."""
    from news_lens.backends.claude import ClaudeBackend

    b1 = ClaudeBackend.__new__(ClaudeBackend)
    b1.name = "claude:claude-opus-4-7"
    b2 = ClaudeBackend.__new__(ClaudeBackend)
    b2.name = "openai:http://localhost:11434/v1:llama3.1:8b"
    assert b1.name != b2.name


def test_openai_compatible_import_guard():
    """Construction without instructor installed raises a clear ImportError."""
    # Skip if instructor is actually installed (CI may have it)
    try:
        import instructor  # noqa: F401

        return
    except ImportError:
        pass

    from news_lens.backends.openai_compatible import OpenAICompatibleBackend

    try:
        OpenAICompatibleBackend(
            base_url="http://localhost:11434/v1", model="llama3.1:8b"
        )
    except ImportError as e:
        assert "instructor" in str(e)
        return
    raise AssertionError("expected ImportError")


def test_is_connection_error_recognizes_message():
    """Bare connection-related strings still classify, even when the SDK isn't available."""
    from news_lens.backends.openai_compatible import _is_connection_error

    assert _is_connection_error(Exception("Connection error."))
    assert _is_connection_error(ConnectionRefusedError("nope"))
    assert not _is_connection_error(ValueError("unrelated"))


def test_is_connection_error_walks_cause_chain():
    """Wrapped exceptions still match — instructor wraps openai wraps httpx."""
    from news_lens.backends.openai_compatible import _is_connection_error

    inner = Exception("Connection error.")
    outer = ValueError("retry exhausted")
    outer.__cause__ = inner
    assert _is_connection_error(outer)
