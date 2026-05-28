r"""CLI entry point.

Examples (each command fits on one line so it pastes cleanly in any shell)
-------------------------------------------------------------------------

Auto-discover sources covering a topic, then analyze them:
    python -m news_lens --search "gorton denton byelection" --max-sources 5 --ollama --html out.html

Spectrum-balanced search (one outlet per left/center-left/center/center-right/right):
    python -m news_lens --search "trump tariffs" --balance-spectrum --max-sources 5 --ollama --model qwen3:8b --html tariffs.html

Tier-balanced search (round-robin across mainstream/public/independent/advocacy/state):
    python -m news_lens --search "trump tariffs" --balance-tier --max-sources 5 --ollama --model qwen3:8b --html tariffs.html

Combine search + explicit URLs:
    python -m news_lens https://example.com/article --search "topic" --max-sources 3 --ollama

Historical case study (curated URLs from archive.org or live web):
    python -m news_lens --urls-file examples/vietnam_gulf_of_tonkin.urls --ollama --html gulf.html
GDELT's archive starts February 2015; older events need the --urls-file
path. See examples/README.md for the workflow.

Claude (default; requires ANTHROPIC_API_KEY):
    python -m news_lens URL1 URL2 URL3 --html out.html

Local Llama via Ollama (zero subscriptions, runs on your machine):
    bash scripts/setup_local.sh
    pip install -e ".[local-llm,embeddings]"
    python -m news_lens URL1 URL2 URL3 --ollama --html out.html

The `[embeddings]` extra installs sentence-transformers. It is
strongly recommended: the alignment step uses it (deterministic,
won't hallucinate outlets) and the search step uses it to cluster
results by topic so a query like "morales arrest" doesn't mix
Bolivia, Texas, and Toledo stories.

The `--ollama` flag is shorthand for `--backend openai-compatible
--base-url http://localhost:11434/v1`. Default model is qwen3:8b
(~5GB RAM) — Qwen models are far more reliable than Llama on the
nested JSON schemas this pipeline requires. Fall back to a smaller
model with `--model qwen3:4b` (~3GB) for low-RAM machines, or scale
up to `--model qwen2.5:14b` (~9GB) for the best local quality.
Llama 3.x at 8B and below tends to echo the JSON schema back instead
of filling it, breaking extraction and alignment.

Hosted-but-not-Claude (e.g. Groq's free tier):
    python -m news_lens URL1 URL2 URL3 --backend openai-compatible --base-url https://api.groq.com/openai/v1 --model llama-3.1-70b-versatile --api-key-env GROQ_API_KEY

Multi-line note: backslash line continuation works in bash/zsh on Linux/macOS.
On Windows cmd use `^` at end of line; on Windows PowerShell use backtick.
If your shell passes lone `\` as arguments, this CLI strips them with a
warning so the command still works, but the cleanest fix is to paste the
command on one line.

Migration strategy and longer-term self-hosting paths are documented in
news_lens/backends/__init__.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import asyncio

from .cache import Cache
from .discover import cluster_by_event, report_selection, search, select_diverse
from .pipeline import run_pipeline
from .render import render_html


_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_OLLAMA_DEFAULT_MODEL = "qwen3:8b"


def _embeddings_installed() -> bool:
    from .align_embeddings import is_available

    return is_available()


def _strip_line_continuations(argv: list[str]) -> tuple[list[str], int]:
    """Drop lone backslash args from argv (Windows cmd/PowerShell paper-cut).

    A lone backslash in argv means the user typed `\\` for line continuation
    in a shell that doesn't recognize it (Windows cmd uses ^, PowerShell uses
    backtick). We strip those and tell the user, so the command still works.
    Returns (cleaned_argv, n_stripped).
    """
    cleaned: list[str] = []
    stripped = 0
    for arg in argv:
        if arg.strip() in ("\\", "\\\\"):
            stripped += 1
            continue
        cleaned.append(arg)
    return cleaned, stripped


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
            max_concurrency=args.max_concurrency,
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
        "For openai-compatible required (e.g. qwen3:8b).",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="Env var holding the API key for openai-compatible backend "
        "(e.g. GROQ_API_KEY, OPENROUTER_API_KEY). Omit for local servers "
        "that do not require auth.",
    )
    parser.add_argument(
        "--no-omissions",
        action="store_true",
        help="Skip the structural-omissions LLM pass. By default, after "
        "alignment, the pipeline runs one extra LLM call asking the model "
        "to name perspectives, source classes, and contextual facts that "
        "are absent from EVERY article in the sample — Manufacturing "
        "Consent's deeper question. Disable when you want to save the "
        "extra call or when the local model is too weak for the task.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2,
        help="Max simultaneous LLM requests for the openai-compatible "
        "backend (default: 2). A local Ollama server holds one model and "
        "serializes work anyway; too many in-flight requests inflate "
        "memory and can crash it mid-run. Lower to 1 on a low-RAM machine; "
        "raise it for a hosted endpoint that scales.",
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
        "--days",
        type=int,
        default=14,
        help="With --search, only return articles published in the last N "
        "days (default: 14). Without a window GDELT matches across years "
        "and a short query like 'morales arrest' returns unrelated stories "
        "from different events. Pass 0 to disable the window.",
    )
    parser.add_argument(
        "--no-cluster",
        action="store_true",
        help="Disable topical clustering of search results. By default, "
        "when news-lens[embeddings] is installed, search results are "
        "clustered by title similarity and only the largest cluster is "
        "kept — this stops keyword collisions (different events sharing a "
        "surname) from polluting the analysis.",
    )
    parser.add_argument(
        "--require-coherence",
        action="store_true",
        help="With --search, error out if the largest event cluster covers "
        "less than 50%% of the search results. Use when you want the run "
        "to fail loud rather than analyze a topically-mixed sample.",
    )
    parser.add_argument(
        "--require-known-outlets",
        action="store_true",
        help="With --search, only include outlets in the registry "
        "(news_lens/outlets.py). Otherwise unknown outlets fill in if "
        "fewer than --max-sources known outlets matched.",
    )
    balance_group = parser.add_mutually_exclusive_group()
    balance_group.add_argument(
        "--balance-spectrum",
        action="store_true",
        help="With --search, round-robin source selection across the "
        "left → center-left → center → center-right → right buckets "
        "before filling repeats. Aims for cross-spectrum coverage of "
        "the topic. Outlet leans come from the registry; outlets without "
        "a lean are picked last.",
    )
    balance_group.add_argument(
        "--balance-tier",
        action="store_true",
        help="With --search, round-robin source selection across the "
        "institutional-tier buckets (mainstream / public / independent / "
        "advocacy / state) before filling repeats. Targets the axis a "
        "left-vs-right balance misses: a spectrum-balanced sample can "
        "still be entirely commercial-mainstream. Mutually exclusive "
        "with --balance-spectrum.",
    )
    raw_argv = sys.argv[1:]
    cleaned_argv, n_stripped = _strip_line_continuations(raw_argv)
    if n_stripped:
        print(
            f"WARN: stripped {n_stripped} lone backslash arg(s) — your shell "
            "didn't interpret them as line continuation. On Windows cmd use "
            "^ at end-of-line, on PowerShell use ` (backtick), or paste the "
            "command on a single line.",
            file=sys.stderr,
        )
    args = parser.parse_args(cleaned_argv)

    urls = [_validate_url(u) for u in args.urls]
    if args.urls_file:
        urls.extend(
            _validate_url(line)
            for line in args.urls_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if args.search:
        days = args.days if args.days > 0 else None
        window_label = f"last {args.days}d" if days else "all time"
        print(
            f"Searching GDELT for: {args.search!r} ({window_label})",
            file=sys.stderr,
        )
        search_cache = Cache(args.cache_dir)
        results = asyncio.run(
            search(args.search, max_results=30, days=days, cache=search_cache)
        )
        outlets_found = {r.outlet_domain for r in results}
        print(
            f"  found {len(results)} articles across {len(outlets_found)} outlet(s)",
            file=sys.stderr,
        )

        if not args.no_cluster and results:
            clusters = cluster_by_event(results)
            if len(clusters) > 1:
                primary = clusters[0]
                fraction = len(primary) / len(results)
                print(
                    f"  GDELT results span {len(clusters)} event cluster(s); "
                    f"keeping the largest ({len(primary)} of {len(results)} "
                    f"articles, {fraction:.0%}). Other clusters were dropped "
                    "because they look like different stories that share "
                    "keywords.",
                    file=sys.stderr,
                )
                if args.require_coherence and fraction < 0.5:
                    raise SystemExit(
                        f"error: the largest event cluster is only "
                        f"{fraction:.0%} of the search results "
                        "(--require-coherence threshold is 50%). The query "
                        "is too broad or too generic — try adding a "
                        "distinguishing entity, location, or date hint."
                    )
                results = primary
            elif len(clusters) == 1 and results and not _embeddings_installed():
                print(
                    "  (install news-lens[embeddings] for topical clustering "
                    "of search results; without it broad queries can mix "
                    "unrelated events.)",
                    file=sys.stderr,
                )

        selected = select_diverse(
            results,
            n=args.max_sources,
            require_known=args.require_known_outlets,
            balance_spectrum=args.balance_spectrum,
            balance_tier=args.balance_tier,
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
    matrix = run_pipeline(
        urls,
        backend=backend,
        cache_dir=args.cache_dir,
        omissions_enabled=not args.no_omissions,
    )
    output_json = matrix.model_dump_json(indent=2)

    if args.output:
        args.output.write_text(output_json, encoding="utf-8")
        print(f"Wrote coverage matrix to {args.output}", file=sys.stderr)
    elif not args.html:
        print(output_json)

    if args.html:
        args.html.write_text(render_html(matrix), encoding="utf-8")
        print(f"Wrote HTML report to {args.html}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
