"""Structural-omissions analysis — what's missing from the whole sample.

The per-article lens already catches outlet-level framing. The
cross-article alignment catches what some outlets carried and others
omitted. This module catches what NO outlet in the sample carried —
perspectives never quoted, source classes never interviewed, contextual
facts never provided, established public-record facts that the framing
elides. That's the propaganda model's deeper bite: manufactured consent
is most visible in the questions never asked.

The analysis is gated on having enough sample (>=3 outlets) and is
designed to fail gracefully: a small / weak LLM will be poor at this
and the report can survive an empty result. The prompt explicitly tells
the model to write a sample_caveat and emit no omissions when it can't
ground the analysis, rather than fabricating absences.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Mapping

from .backends.base import StructuredLLM
from .cache import Cache
from .models import (
    AlignmentResult,
    Article,
    ArticleLens,
    ExtractionResult,
    OmissionAnalysis,
)


_SYSTEM_PROMPT = """\
You are looking at coverage of a single story by N news outlets. Your job is to identify what is STRUCTURALLY ABSENT from the entire sample — perspectives, classes of source, contextual facts, public-record counter-facts, or angles that a careful editor would expect to inform any responsible coverage of this kind of story, but that NONE of the sampled outlets included.

You will be given:
- The outlets in the sample, with country, institutional tier (mainstream / public / independent / advocacy / state), and political lean if known.
- The aggregate list of named sources quoted across every article.
- The canonical claims that emerged across the sample.

Rules — these matter a lot:

1. BE SPECIFIC. Useless: "more diverse voices". Useful: "a frontline aid worker from inside Gaza describing distribution logistics", "a labour-economist's view on the proposed policy's effect on low-wage workers", "the 2003 declassified record showing the Tonkin Gulf second attack did not happen". Each omission should be a sentence a reader could take to a search engine.

2. BE GROUNDED. Only flag absences a careful editor would actually expect in coverage of this kind of story. Do not invent perspectives. Do not list things that are merely "alternative" if no responsible newsroom would have included them.

3. DO NOT name something that IS in the sample. If a source-class or perspective is represented in any outlet's coverage, it is NOT a structural omission.

4. CATEGORISE. Each omission must fit one of:
   - "perspective": a viewpoint with stake in the story that no outlet quoted.
   - "source_class": a class of source (e.g. "affected workers", "neighbouring-country diplomats", "indigenous community representatives") that none of the outlets interviewed.
   - "context": historical, statistical, or structural context none of the articles provided.
   - "counterfact": an established public-record fact that complicates how the story is framed across the sample.
   - "scope": an angle on the story none of the outlets examined (a downstream effect, a comparable past case, etc.).

5. AIM FOR 3–7 OMISSIONS, not more. Quality over quantity.

6. IF THE SAMPLE WON'T SUPPORT IT — too small (under 3 outlets), too narrow (all one tier), too foreign to your knowledge — set `sample_caveat` to a one-sentence honest disclosure and emit NO omissions. Better an honest empty result than a fabricated one.

7. For each omission give `description` (the specific absence) and `why_relevant` (one sentence — why this kind of story is incomplete without it).
"""


_PROMPT_HASH = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


def _build_payload(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
    alignment: AlignmentResult,
    lenses: list[ArticleLens],
) -> str:
    """Pack the sample into a compact JSON brief for the LLM."""
    from .outlets import lookup as _outlet_lookup

    outlets_meta = []
    seen = set()
    for a in articles:
        if a.outlet_domain in seen:
            continue
        seen.add(a.outlet_domain)
        info = _outlet_lookup(a.outlet_domain)
        outlets_meta.append({
            "domain": a.outlet_domain,
            "country": info.country if info else None,
            "tier": info.tier if info else None,
            "lean": info.lean if info else None,
            "owner": info.owner if info else None,
        })

    # Aggregate named sources across lenses.
    sources: dict[str, int] = {}
    for lens in lenses:
        for s in lens.signals.sources_quoted:
            key = " ".join((s or "").lower().split())
            if not key:
                continue
            sources[key] = sources.get(key, 0) + 1
    sources_list = sorted(sources.items(), key=lambda kv: -kv[1])

    payload = {
        "story_summary": (
            "The titles and outlets are listed below — infer the story "
            "subject from them and from the canonical claims."
        ),
        "outlets": outlets_meta,
        "article_titles": [a.title or "" for a in articles],
        "canonical_claims": [
            cc.canonical_text for cc in alignment.canonical_claims
        ],
        "aggregate_sources_quoted": [
            {"source": s, "n_outlets_quoting": n}
            for s, n in sources_list
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


async def analyze_omissions(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
    alignment: AlignmentResult,
    lenses: list[ArticleLens],
    llm: StructuredLLM,
    cache: Cache,
    min_outlets: int = 3,
) -> OmissionAnalysis:
    """Run the structural-omissions pass; return empty result on failure.

    The pipeline calls this once per run, AFTER alignment and lens are
    done. It is intentionally robust to LLM failure: if the call errors
    or the model can't produce a valid OmissionAnalysis, the function
    returns an empty result so the rest of the report still renders.
    """
    distinct_outlets = {a.outlet_domain for a in articles}
    if len(distinct_outlets) < min_outlets:
        return OmissionAnalysis(
            omissions=[],
            sample_caveat=(
                f"This sample has only {len(distinct_outlets)} distinct "
                f"outlet(s); structural-omissions analysis was skipped "
                f"(needs at least {min_outlets})."
            ),
        )

    payload = _build_payload(articles, extractions, alignment, lenses)
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    cached = cache.get("omissions", payload_hash, _PROMPT_HASH, llm.name)
    if cached is not None:
        return OmissionAnalysis.model_validate(cached)

    try:
        result = await llm.parse(
            system=_SYSTEM_PROMPT, user=payload, schema=OmissionAnalysis
        )
    except Exception as exc:
        print(
            f"WARN: omissions analysis failed ({type(exc).__name__}); "
            "skipping. The rest of the report renders normally.",
            file=sys.stderr,
        )
        return OmissionAnalysis(
            omissions=[],
            sample_caveat=(
                "The structural-omissions pass could not be produced for this "
                "sample — the model returned an invalid result. Re-run with "
                "a stronger model to populate this section."
            ),
        )

    cache.set(
        "omissions",
        result.model_dump(mode="json"),
        payload_hash,
        _PROMPT_HASH,
        llm.name,
    )
    return result
