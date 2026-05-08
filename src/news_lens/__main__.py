"""CLI entry point.

Examples
--------

Auto-discover sources covering a topic, then analyze them (no manual URLs):
    python -m news_lens --search "gorton denton byelection green party" \\
        --max-sources 5 --ollama --html out.html

Combine search + explicit URLs (search adds, doesn't replace):
    python -m news_lens https://example.com/article \\
        --search "topic" --max-sources 3 --ollama

Claude (default; requires ANTHROPIC_API_KEY):
    python -m news_lens URL1 URL2 URL3 --html out.html

Local Llama via Ollama (zero subscriptions, runs on your machine):
    1. Install: `bash scripts/setup_local.sh`  (or see scripts/setup_local.sh)
    2. Run:     python -m news_lens URL1 URL2 URL3 --ollama --html out.html

The `--ollama` flag is shorthand for:
    --backend openai-compatible --base-url http://localhost:11434/v1
The default model is llama3.2:3b (~2GB RAM, runs anywhere).

For larger machines / better quality, override:
    python -m news_lens URL1 URL2 URL3 --ollama --model llama3.1:8b   # ~5GB RAM
    python -m news_lens URL1 URL2 URL3 --ollama --model qwen2.5:14b   # ~9GB RAM

Hosted-but-not-Claude (e.g. Groq's free tier):
    python -m news_lens URL1 URL2 URL3 \\
        --backend openai-compatible \\
        --base-url https://api.groq.com/openai/v1 \\
        --model llama-3.1-70b-versatile \\
        --api-key-env GROQ_API_KEY

Migration strategy and longer-term self-hosting paths are documented in
news_lens/backends/__init__.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import asyncio

from .discover import report_selection, search, select_diverse
from .pipeline import run_pipeline
from .render import render_html


_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_OLLAMA_DEFAULT_MODEL = "llama3.2:3b"


def _validate_url(raw: str) -> str:
    """Strip whitespace and verify the argument looks like a URL.

    Catches the common paste-with-line-continuation paper-cut where backslashes
    survive shell parsing on Windows cmd/PowerShell.
    """
    url = raw.strip()
    if not url:
        raise SystemExit("error: empty URL passed as argument")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise SystemExit(
            f"error: not a valid URL: {raw!r}\n"
            "If you used backslash for line continuation in your shell and "
            "the backslash got passed as an argument, your shell didn't "
            "interpret it. On Windows cmd use ^ at end-of-line, on PowerShell "
            "use ` (backtick), or pass URLs on a single line / via "
            "--urls-file path/to/urls.txt."
        )
    return url


def _build_backend(args: argparse.Namespace):
    # --ollama is a shortcut for openai-compatible against a local Ollama.
    if args.ollama:
        args.backend = "openai-compatible"
        if not args.base_url:
            args.base_url = _OLLAMA_DEFAULT_BASE_URL
        if not args.model:
            args.model = _OLLAMA_DEFAULT_MODEL

    if args.backend == "claude":
        import anthropic

        from .backends.claude import ClaudeBackend

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit(
                "error: ANTHROPIC_API_KEY is not set. Either export it or "
                "use --ollama for a local LLM (see scripts/setup_local.sh)."
            )
        return ClaudeBackend(
            client=anthropic.AsyncAnthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            ),
            model=args.model or "claude-opus-4-7",
        )

    if args.backend == "openai-compatible":
        if not args.base_url:
            raise SystemExit(
                "error: --backend openai-compatible requires --base-url "
                "(or use --ollama for local Ollama at localhost:11434)"
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
        "--ollama",
        action="store_true",
        help="Shortcut for --backend openai-compatible --base-url "
        f"{_OLLAMA_DEFAULT_BASE_URL} with default model "
        f"{_OLLAMA_DEFAULT_MODEL}. Override the model with --model.",
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
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        help='Auto-search GDELT for articles on this topic. e.g. '
        '--search "gorton denton byelection". Combines with explicit URLs.',
    )
    parser.add_argument(
        "--max-sources",
        type=int,
        default=5,
        help="Max sources to keep from --search results (default: 5). One "
        "article per outlet, prioritizing outlets in the registry.",
    )
    parser.add_argument(
        "--require-known-outlets",
        action="store_true",
        help="With --search, only include outlets in the registry "
        "(news_lens/outlets.py). Otherwise unknown outlets fill in if "
        "fewer than --max-sources known outlets matched.",
    )
    args = parser.parse_args()

    urls = [_validate_url(u) for u in args.urls]
    if args.urls_file:
        urls.extend(
            _validate_url(line)
            for line in args.urls_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if args.search:
        print(f"Searching GDELT for: {args.search!r}", file=sys.stderr)
        results = asyncio.run(search(args.search, max_results=30))
        outlets_found = {r.outlet_domain for r in results}
        print(
            f"  found {len(results)} articles across {len(outlets_found)} outlet(s)",
            file=sys.stderr,
        )
        selected = select_diverse(
            results,
            n=args.max_sources,
            require_known=args.require_known_outlets,
        )
        print(f"  selected {len(selected)} for analysis:", file=sys.stderr)
        report_selection(selected)
        urls.extend(r.url for r in selected)

    if not urls:
        parser.error(
            "Provide at least one URL (positional, --urls-file, or --search)."
        )
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
