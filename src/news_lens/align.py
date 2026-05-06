"""Align claims across articles into canonical claims with per-outlet status.

Two extracted claims that describe the same underlying proposition collapse
into one canonical claim — even when one article asserts it and another
only attributes it to a source. The per-outlet status preserves that
difference without losing that they refer to the same fact.

The model is provided as a `StructuredLLM` backend (Claude / local Llama
/ etc.) — see backends/.

Migration path away from an LLM
-------------------------------

Cross-article alignment is a textbook semantic-equivalence problem and
should not be an LLM call in a production self-hosted setup. The classical
two-stage pipeline gives equal-or-better quality, runs in milliseconds per
pair, and is much easier to tune and validate:

1. **Candidate generation** — embed every extracted claim with
   `sentence-transformers/all-mpnet-base-v2` (or `paraphrase-multilingual-mpnet-base-v2`
   for non-English coverage). Compute pairwise cosine similarity between
   claims from different articles. Keep pairs above a threshold (~0.7) as
   candidate equivalences.

2. **Verification** — run a DeBERTa-v3 NLI cross-encoder
   (`cross-encoder/nli-deberta-v3-large` or similar) on each candidate
   pair to classify the relationship: entailment, contradiction, neutral.
   Bidirectional entailment → same canonical claim. One-direction → one
   is stronger; pick the more general phrasing. Contradiction → DISPUTED.

3. **Clustering** — connect transitive entailment edges with union-find.
   Each connected component is a canonical claim. The status per outlet
   maps from the input claim's claim_type (asserted vs attributed).

A `ClassicalAlignmentBackend` would expose `align_claims(articles,
extractions) -> AlignmentResult` matching this module's signature. The
cache namespacing already includes the backend name so a classical
backend's outputs stay separate from any LLM-cached results, which makes
A/B comparisons easy.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

from .backends.base import StructuredLLM
from .cache import Cache
from .models import (
    AlignmentResult,
    Article,
    CanonicalClaim,
    CoverageStatus,
    ExtractionResult,
    OutletCoverage,
)


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


_PROMPT_HASH = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


async def align_claims(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
    llm: StructuredLLM,
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

    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    cached = cache.get("alignments", payload_hash, _PROMPT_HASH, llm.name)
    if cached is not None:
        return AlignmentResult.model_validate(cached)

    parsed = await llm.parse(
        system=_SYSTEM_PROMPT, user=payload, schema=AlignmentResult
    )

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
    cache.set("alignments", result.model_dump(mode="json"), payload_hash, _PROMPT_HASH, llm.name)
    return result
