"""Align claims across articles into canonical claims with per-outlet status.

Two extracted claims that describe the same underlying proposition collapse
into one canonical claim — even when one article asserts it and another only
attributes it to a source. The per-outlet status preserves that difference
without losing that they refer to the same fact.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

import anthropic

from .cache import Cache
from .models import (
    AlignmentResult,
    Article,
    CanonicalClaim,
    CoverageStatus,
    ExtractionResult,
    OutletCoverage,
)


_MODEL = "claude-opus-4-7"

_SYSTEM_PROMPT = """\
You are a media analyst comparing how multiple outlets covered the same story. You will receive factual claims extracted from each article. Your job is to identify canonical claims across articles and document how each outlet handled each one.

For each canonical claim, classify EVERY article's handling as one of:
- "asserted": The article states this as a fact in its own voice (input claim_type was "asserted").
- "attributed": The article reports it as a claim by a named source (input claim_type was "attributed"). Set `attributed_to` to the source.
- "contradicted": The article states something that directly contradicts this claim.
- "omitted": The article does not mention this claim. Set `source_quote` and `attributed_to` to null.

Rules:
- Two claims are the same canonical claim if they assert the same fact about the same entities, even if phrased differently. Differences in time, place, subject, or predicate make them DIFFERENT canonical claims.
- "X said Y" in one article and "Y is true" in another describe the SAME proposition but DIFFERENT statuses (attributed vs asserted). Group them as ONE canonical claim with different statuses per outlet.
- For "asserted", "attributed", or "contradicted" entries, copy `source_quote`, `attributed_to`, and `position` verbatim from the corresponding input claim. Do not paraphrase or recompute. For "omitted" entries, set `position` to null.
- `canonical_text` should be a neutral phrasing that abstracts away outlet-specific framing. Avoid loaded language. Strip judgmental adjectives.
- Do not invent claims that do not appear in any article.
- Focus on factual claims. Skip pure interpretation or background unless multiple outlets emphasize them.
- For each canonical claim, you MUST include an outlet entry for EVERY article in the input. If an article does not cover the claim, mark it "omitted".
- Aim for 5-25 canonical claims for the story.
"""


async def align_claims(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
    client: anthropic.AsyncAnthropic,
    cache: Cache,
) -> AlignmentResult:
    payload_obj = {
        "articles": [
            {
                "article_id": a.id,
                "outlet_domain": a.outlet_domain,
                "title": a.title or "",
                "url": a.url,
                "claims": [c.model_dump(mode="json") for c in extractions[a.id].claims],
            }
            for a in articles
        ]
    }
    payload = json.dumps(payload_obj, indent=2)

    prompt_hash = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    cached = cache.get("alignments", payload_hash, prompt_hash)
    if cached is not None:
        return AlignmentResult.model_validate(cached)

    response = await client.messages.parse(
        model=_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": payload}],
        output_format=AlignmentResult,
    )

    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError("Alignment returned no parseable output")

    article_ids = [a.id for a in articles]
    article_to_outlet = {a.id: a.outlet_domain for a in articles}

    filled: list[CanonicalClaim] = []
    for cc in parsed.canonical_claims:
        present = {oc.article_id for oc in cc.outlets}
        outlets = list(cc.outlets)
        for aid in article_ids:
            if aid not in present:
                outlets.append(
                    OutletCoverage(
                        outlet_domain=article_to_outlet[aid],
                        article_id=aid,
                        status=CoverageStatus.OMITTED,
                    )
                )
        filled.append(CanonicalClaim(canonical_text=cc.canonical_text, outlets=outlets))

    result = AlignmentResult(canonical_claims=filled)
    cache.set("alignments", result.model_dump(mode="json"), payload_hash, prompt_hash)
    return result
