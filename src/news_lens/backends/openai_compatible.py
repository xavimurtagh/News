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
against a Pydantic schema. It supports several enforcement strategies
(modes); the right one depends on the model:

- **JSON mode (default here)** — instructor adds a "respond in JSON
  matching this schema" instruction to the system prompt and parses
  the response. Most reliable on local 7B/8B models and below; works
  with every OpenAI-compatible server.
- **TOOLS mode** — uses the model's tool-calling interface. Works on
  GPT-4-class models reliably, but smaller models (Llama 3 8B, Llama
  3.2 3B) tend to emit malformed tool calls or multiple tool calls
  per response, which instructor rejects with
  "does not support multiple tool calls". Avoid for local inference.
- **JSON_SCHEMA mode** — uses servers that natively support
  response_format with a JSON schema (vLLM with the `--guided-decoding`
  flag, llama.cpp's grammar option). Most reliable when supported but
  not universal.

Pass `mode=instructor.Mode.TOOLS` at construction if you're on
GPT-4-class hosting and want the standard tool-call path.

Prompt sensitivity
------------------

The prompts in extract.py / lens.py / align.py were tuned against
Claude. Open-weight models tend to follow them well enough but quality
drops, especially on the citation-fidelity rule (return verbatim
substring) and on the "do not invent claims" rule. Smaller models
(<= 3B parameters) struggle on the longer prompts and complex
schemas — the citation guard catches and drops their bad outputs, so
the matrix is smaller but stays trustworthy.

Model recommendations (Ollama)
------------------------------

- **qwen3:8b** (default) — best quality-per-GB locally. Follows the
  nested `$defs` Pydantic schemas reliably in JSON mode.
- **qwen2.5:14b** / **qwen3:14b** — noticeably better alignment if
  you have the VRAM (~9GB).
- **llama3.1:8b** and below — NOT recommended. These models commonly
  return the JSON Schema definition (literal `$defs`, `properties`,
  `required` keys) instead of an instance of it, which makes
  extraction and alignment fail. If you must use Llama, prefer the
  70B class on hosted endpoints (Groq, OpenRouter).
"""

from __future__ import annotations

from typing import Any, TypeVar

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
        mode: Any | None = None,
    ) -> None:
        try:
            import instructor
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError(
                "OpenAICompatibleBackend requires `instructor` and `openai`. "
                'Install with: pip install -e ".[local-llm]"'
            ) from e
        # JSON mode is the most reliable on local 3B-8B models. Tool-calling
        # mode (instructor's default for OpenAI-compatible) breaks on smaller
        # models that emit malformed or multiple tool calls.
        if mode is None:
            mode = instructor.Mode.JSON
        self._client = instructor.from_openai(
            AsyncOpenAI(base_url=base_url, api_key=api_key),
            mode=mode,
        )
        self._base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.name = f"openai:{base_url}:{model}"

    async def parse(self, *, system: str, user: str, schema: type[T]) -> T:
        try:
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
        except Exception as e:
            if _is_connection_error(e):
                raise ConnectionError(
                    f"Could not reach LLM server at {self._base_url}. "
                    "Is Ollama (or your local LLM server) running? "
                    "Start Ollama with `ollama serve` in another terminal, "
                    "or pull a model with `ollama pull " + self.model + "`."
                ) from e
            raise


_CONNECTION_ERROR_NAMES = {
    "APIConnectionError",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "RemoteProtocolError",
}


def _is_connection_error(exc: BaseException) -> bool:
    """Recognize connection failures across instructor / openai / httpx layers."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return True
        if type(exc).__name__ in _CONNECTION_ERROR_NAMES:
            return True
        if "Connection error" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False
