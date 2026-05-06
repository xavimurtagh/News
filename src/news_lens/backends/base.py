"""Backend protocol for structured-output LLM calls."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class StructuredLLM(Protocol):
    """An LLM client that returns Pydantic-validated structured outputs.

    Each call is "given a system prompt and a user message, return a
    validated instance of the requested Pydantic schema." Backends are
    responsible for prompt formatting, schema enforcement, retries, and
    any model-specific knobs (temperature, thinking, effort, etc.).

    Backends MUST expose a `name` attribute used as a cache namespace key
    so swapping backends doesn't collide cached outputs from a previous
    run.
    """

    name: str

    async def parse(self, *, system: str, user: str, schema: type[T]) -> T:
        ...
