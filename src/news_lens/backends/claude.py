"""StructuredLLM backed by Anthropic's Claude API.

Default model is claude-opus-4-7 with adaptive thinking and high effort.
Keep this as the baseline while you have API access — the pipeline was
developed against it and other backends should be benchmarked against
its outputs (which are conveniently cached on disk).
"""

from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class ClaudeBackend:
    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        model: str = "claude-opus-4-7",
        max_tokens: int = 16000,
    ) -> None:
        self.client = client or anthropic.AsyncAnthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"claude:{model}"

    async def parse(self, *, system: str, user: str, schema: type[T]) -> T:
        response = await self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        result = response.parsed_output
        if result is None:
            raise RuntimeError(
                f"Claude returned no parseable output for schema {schema.__name__}"
            )
        return result
