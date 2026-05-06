"""CLI entry point.

Usage:
    python -m news_lens URL1 URL2 [URL3 ...]
    python -m news_lens --urls-file path/to/urls.txt
    python -m news_lens URL1 URL2 --output coverage.json
    python -m news_lens URL1 --backend openai-compatible \\
        --base-url http://localhost:11434/v1 --model llama3.1:8b

Backend defaults to Claude (requires ANTHROPIC_API_KEY in env).
For self-hosted alternatives (Ollama, vLLM, Groq, OpenRouter, ...) use
--backend openai-compatible with --base-url and --model. See
news_lens/backends/__init__.py for the full migration guide.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .pipeline import run_pipeline
from .render import render_html


def _build_backend(args: argparse.Namespace):
    if args.backend == "claude":
        import anthropic

        from .backends.claude import ClaudeBackend

        return ClaudeBackend(
            client=anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            ),
            model=args.model or "claude-opus-4-7",
        )

    if args.backend == "openai-compatible":
        if not args.base_url:
            raise SystemExit(
                "error: --backend openai-compatible requires --base-url"
            )
        if not args.model:
            raise SystemExit(
                "error: --backend openai-compatible requires --model"
            )
        from .backends.openai_compatible import OpenAICompatibleBackend

        api_key = "not-needed"
        if args.api_key_env:
            api_key = os.environ.get(args.api_key_env, "")
            if not api_key:
                raise SystemExit(
                    f"error: env var {args.api_key_env} is empty or unset"
                )
        return OpenAICompatibleBackend(
            base_url=args.base_url,
            model=args.model,
            api_key=api_key,
        )

    raise SystemExit(f"error: unknown backend {args.backend!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "urls",
        nargs="*",
        help="Article URLs covering the same event.",
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        help="Path to a file with one URL per line. Lines starting with # are ignored.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache"),
        help="Directory to cache pipeline results (default: .cache).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write JSON output (default: stdout).",
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=None,
        help="Path to write a self-contained HTML coverage matrix.",
    )
    parser.add_argument(
        "--backend",
        choices=["claude", "openai-compatible"],
        default="claude",
        help='LLM backend (default: claude). Use "openai-compatible" for '
        "any OpenAI-API-compatible server (Ollama, vLLM, Groq, OpenRouter, "
        "LM Studio, ...).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL for openai-compatible backend "
        "(e.g. http://localhost:11434/v1 for Ollama).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name. For Claude defaults to claude-opus-4-7. "
        "For openai-compatible required (e.g. llama3.1:8b).",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="Env var holding the API key for openai-compatible backend "
        "(e.g. GROQ_API_KEY, OPENROUTER_API_KEY). Omit for local servers "
        "that do not require auth.",
    )
    args = parser.parse_args()

    urls = list(args.urls)
    if args.urls_file:
        urls.extend(
            line.strip()
            for line in args.urls_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if not urls:
        parser.error("Provide at least one URL (positional or via --urls-file).")
        return 2

    backend = _build_backend(args)
    matrix = run_pipeline(urls, backend=backend, cache_dir=args.cache_dir)
    output_json = matrix.model_dump_json(indent=2)

    if args.output:
        args.output.write_text(output_json)
        print(f"Wrote coverage matrix to {args.output}", file=sys.stderr)
    elif not args.html:
        print(output_json)

    if args.html:
        args.html.write_text(render_html(matrix))
        print(f"Wrote HTML report to {args.html}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
