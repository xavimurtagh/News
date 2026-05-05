"""CLI entry point.

Usage:
    python -m news_lens URL1 URL2 [URL3 ...]
    python -m news_lens --urls-file path/to/urls.txt
    python -m news_lens URL1 URL2 --output coverage.json

Set ANTHROPIC_API_KEY in the environment before running.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import run_pipeline
from .render import render_html


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

    matrix = run_pipeline(urls, cache_dir=args.cache_dir)
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
