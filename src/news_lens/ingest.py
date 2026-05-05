"""Fetch and parse news articles from URLs.

Network and HTML parsing are blocking, so the public coroutine wraps them in
asyncio.to_thread. That keeps the pipeline's per-article fetches concurrent
without forking subprocesses.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import trafilatura
from trafilatura.metadata import extract_metadata

from .models import Article


def _article_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _outlet_domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _paragraph_count(body: str) -> int:
    return max(1, sum(1 for p in body.split("\n\n") if p.strip()))


async def fetch_article(url: str) -> Article:
    """Fetch a URL and return a parsed Article. Raises ValueError on failure."""
    raw_html = await asyncio.to_thread(trafilatura.fetch_url, url)
    if raw_html is None:
        raise ValueError(f"Could not fetch URL: {url}")

    body = await asyncio.to_thread(
        trafilatura.extract,
        raw_html,
        favor_recall=True,
        include_comments=False,
        include_tables=False,
    )
    if not body:
        raise ValueError(f"Could not extract article body from: {url}")

    title: str | None = None
    byline: str | None = None
    published_at: datetime | None = None

    metadata = await asyncio.to_thread(extract_metadata, raw_html)
    if metadata is not None:
        title = metadata.title
        byline = metadata.author
        if metadata.date:
            try:
                published_at = datetime.fromisoformat(metadata.date)
            except ValueError:
                published_at = None

    return Article(
        id=_article_id(url),
        url=url,
        outlet_domain=_outlet_domain(url),
        title=title,
        byline=byline,
        published_at=published_at,
        fetched_at=datetime.now(timezone.utc),
        body=body,
        paragraph_count=_paragraph_count(body),
    )
