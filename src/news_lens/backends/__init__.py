"""LLM backend abstractions for the structured-output tasks.

Three tasks in this pipeline ride on an LLM today: claim extraction,
lens analysis, and cross-article alignment. Each one is "given a system
prompt and user content, return a Pydantic-validated structured output."
That shape is what the StructuredLLM protocol abstracts over.

Bundled backends
----------------

- ClaudeBackend: Anthropic's Claude (claude-opus-4-7 by default) with
  adaptive thinking and high effort. The pipeline was developed against
  this; treat it as the baseline when evaluating other backends.

- OpenAICompatibleBackend: any OpenAI-API-compatible server. Works with
  Ollama, vLLM, LM Studio, OpenRouter, Groq, LiteLLM, and the
  llama.cpp HTTP server. Add `pip install -e ".[local-llm]"` to get
  the dependencies (instructor + openai), then point at a base_url.
  This is the recommended migration target if you're moving off Claude
  but want to keep the LLM-shaped architecture.

Choosing a target model
-----------------------

For self-hosting:
- **Llama 3.1 8B Instruct** is the recommended starting point. Runs on
  a 16GB GPU; quality is meaningfully below Claude on long-context
  reasoning but workable for claim extraction with the existing prompts.
- **Llama 3.1 70B** if you have a 48GB+ GPU. Closes most of the quality
  gap with Claude.
- **Qwen 2.5 7B / 14B Instruct** is a strong alternative with good
  structured-output behavior.

For a hosted-but-not-Claude path:
- **Groq** (very fast Llama inference) and **OpenRouter** (any model)
  both expose OpenAI-compatible APIs and slot right into
  OpenAICompatibleBackend.

Specialized models for alignment and lens
-----------------------------------------

LLMs are overkill for cross-article alignment and lens analysis. A
self-hosted production setup should replace them with task-specific
models that are smaller, faster, and easier to evaluate:

- Cross-article alignment → sentence-transformers (all-mpnet-base-v2)
  for candidate generation by cosine similarity, plus a DeBERTa-v3 NLI
  cross-encoder for entailment / contradiction verification. See the
  module docstring in align.py for the planned shape.

- Lens analysis → spaCy NER for sources_quoted, a paired-term lexicon
  for loaded vocabulary, and a fine-tuned news-sentiment classifier
  (DistilRoBERTa-base on financial-news / political-news sentiment
  data) for headline_framing. See lens.py.

These are described in the respective modules; the backends here cover
the general LLM swap. Specialised non-LLM backends are a follow-on.

Bootstrapping a fine-tune
-------------------------

While you still have Claude API access, every pipeline run caches its
outputs (extractions, lenses, alignments). Those cached JSON files are
ready-made silver labels. To move to a fine-tuned local model:

1. Run the Claude backend over a representative corpus (~500-2000
   articles) and accumulate the cache.
2. Convert cache entries to (prompt, completion) pairs.
3. Fine-tune Llama 3.1 8B or Qwen 2.5 7B with LoRA — a few hours on
   one A100 or comparable.
4. Serve the fine-tuned model via vLLM and point
   OpenAICompatibleBackend at it. The `cache` namespacing already
   incorporates the backend name, so your Claude-cached outputs and
   your fine-tuned outputs live side by side for comparison.
"""

from .base import StructuredLLM
from .claude import ClaudeBackend
from .openai_compatible import OpenAICompatibleBackend

__all__ = ["StructuredLLM", "ClaudeBackend", "OpenAICompatibleBackend"]
