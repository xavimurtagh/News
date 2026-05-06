"""StructuredLLM for any OpenAI-API-compatible server.

Works with vLLM, Ollama, LM Studio, OpenRouter, Groq, LiteLLM, and the
llama.cpp HTTP server. Requires `pip install instructor openai`
(install via `pip install -e ".[local-llm]"` from the project root).

Examples
--------

Ollama running locally:
    backend = OpenAICompatibleBackend(
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
    )

vLLM (after `vllm serve meta-llama/Llama-3.1-8B-Instruct`):
    backend = OpenAICompatibleBackend(
        base_url="http://localhost:8000/v1",
        model="meta-llama/Llama-3.1-8B-Instruct",
    )

Groq (very fast, hosted):
    backend = OpenAICompatibleBackend(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
        model="llama-3.1-70b-versatile",
    )

OpenRouter (any model behind one API):
    backend = OpenAICompatibleBackend(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        model="meta-llama/llama-3.1-70b-instruct",
    )

How structured output is enforced
---------------------------------

Most local LLMs don't natively support Anthropic-style typed outputs.
The `instructor` library wraps the OpenAI client to validate responses
against a Pydantic schema — it converts the schema to JSON Schema, asks
the model to fill it via tool calls or JSON mode, and validates +
retries on parse errors. Quality varies by model: Llama 3.1 8B+ and
Qwen 2.5 7B+ produce reliable structured output; smaller models
struggle and may need JSON-mode (instructor.Mode.JSON) or grammar
constraints.

Prompt sensitivity
------------------

The prompts in extract.py / lens.py / align.py were tuned against
Claude. Open-weight models tend to follow them well enough but quality
drops, especially on the citation-fidelity rule (return verbatim
substring) and on the "do not invent claims" rule. If you see
hallucinated citations after a backend swap, consider:

- Adding 1-2 in-context examples (few-shot) to the system prompt
- Lowering temperature to 0
- Using JSON mode (instructor.Mode.JSON_SCHEMA) for stricter validation
- Fine-tuning the model on Claude-generated outputs (see
  backends/__init__.py for the bootstrapping recipe).
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class OpenAICompatibleBackend:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        max_tokens: int = 8000,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> None:
        try:
            import instructor
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError(
                "OpenAICompatibleBackend requires `instructor` and `openai`. "
                'Install with: pip install -e ".[local-llm]"'
            ) from e
        self._client = instructor.from_openai(
            AsyncOpenAI(base_url=base_url, api_key=api_key)
        )
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.name = f"openai:{base_url}:{model}"

    async def parse(self, *, system: str, user: str, schema: type[T]) -> T:
        return await self._client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            max_retries=self.max_retries,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_model=schema,
        )
