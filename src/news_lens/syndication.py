"""Detect wire-syndicated articles.

Three outlets running AP wire copy aren't three independent confirmations
of a fact. This module groups articles whose body text overlaps enough
that they should be treated as a single voice for tier purposes.

The metric is sentence-level Jaccard: count sentences that appear verbatim
in both articles, divide by total distinct sentences across both. A
threshold of 0.5 catches near-verbatim wire copies while keeping most
independently-reported coverage in separate groups. Minor edits (e.g.
swapping a single word in a sentence) won't match — the metric is verbatim
substring equality, by design. That keeps false positives down at the
cost of recall on heavily-edited rewrites.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .models import Article, SyndicationGroup


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
_MIN_SENTENCE_LEN = 30


def _sentences(body: str) -> set[str]:
    """Return the set of "long enough" sentences from an article body.

    Short sentences are dropped to avoid spurious matches on common
    fragments like "Yes." or "He said."
    """
    sents = _SENTENCE_SPLIT.split(body)
    return {s.strip() for s in sents if len(s.strip()) >= _MIN_SENTENCE_LEN}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detect_syndication(
    articles: list[Article], threshold: float = 0.5
) -> list[SyndicationGroup]:
    """Cluster articles by body overlap. Returns non-singleton groups only."""
    sentences_by_id = {a.id: _sentences(a.body) for a in articles}

    parent = {a.id: a.id for a in articles}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    pair_similarity: dict[tuple[str, str], float] = {}
    for i, a in enumerate(articles):
        for b in articles[i + 1 :]:
            sim = _jaccard(sentences_by_id[a.id], sentences_by_id[b.id])
            pair_similarity[(a.id, b.id)] = sim
            if sim >= threshold:
                union(a.id, b.id)

    groups: dict[str, list[str]] = defaultdict(list)
    for aid in sentences_by_id:
        groups[find(aid)].append(aid)

    result: list[SyndicationGroup] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members_sorted = sorted(members)
        # Group similarity = the minimum pairwise inside the group
        # (proxy for how tightly clustered the bodies are).
        min_sim = 1.0
        for i, m1 in enumerate(members_sorted):
            for m2 in members_sorted[i + 1 :]:
                key = (m1, m2) if (m1, m2) in pair_similarity else (m2, m1)
                min_sim = min(min_sim, pair_similarity.get(key, 0.0))
        result.append(SyndicationGroup(article_ids=members_sorted, similarity=min_sim))

    result.sort(key=lambda g: g.article_ids)
    return result
