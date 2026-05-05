"""Guard against accidental sync regressions of the LLM/fetch coroutines.

Concurrency in the pipeline depends on these staying awaitable so they can
run inside `asyncio.gather`. If one is rewritten as a sync function the
gather degrades to serial execution silently.
"""

from __future__ import annotations

import inspect

from news_lens.align import align_claims
from news_lens.extract import extract_claims
from news_lens.ingest import fetch_article
from news_lens.lens import analyze_lens
from news_lens.pipeline import _analyze_article, _run_async, run_pipeline


def test_pipeline_helpers_are_coroutines():
    assert inspect.iscoroutinefunction(extract_claims)
    assert inspect.iscoroutinefunction(analyze_lens)
    assert inspect.iscoroutinefunction(align_claims)
    assert inspect.iscoroutinefunction(fetch_article)
    assert inspect.iscoroutinefunction(_analyze_article)
    assert inspect.iscoroutinefunction(_run_async)


def test_run_pipeline_remains_sync_entrypoint():
    """The public CLI surface must stay sync so callers don't have to manage a loop."""
    assert not inspect.iscoroutinefunction(run_pipeline)
