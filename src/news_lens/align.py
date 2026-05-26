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

import difflib
import hashlib
import json
import sys
from typing import Mapping

from .backends.base import StructuredLLM
from .cache import Cache
from .models import (
    AlignmentResult,
    Article,
    CanonicalClaim,
    ClaimType,
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
- "omitted": The article does not mention this claim. Set `source_quote`, `attributed_to`, and `provenance` to null.

Rules:
- Two claims are the same canonical claim if they assert the same fact about the same entities, even if phrased differently. Differences in time, place, subject, or predicate make them DIFFERENT canonical claims.
- "X said Y" in one article and "Y is true" in another describe the SAME proposition but DIFFERENT statuses (attributed vs asserted). Group them as ONE canonical claim with different statuses per outlet.
- For "asserted", "attributed", or "contradicted" entries, copy `source_quote`, `attributed_to`, `provenance`, and `position` verbatim from the corresponding input claim. Do not paraphrase or recompute. For "omitted" entries, set `position` and `provenance` to null.
- `canonical_text` is a short, plain handle for the claim, used ONLY to group outlets covering the same point — it is not a neutral or verified version of the claim. Keep it brief and descriptive. The verbatim wording each outlet used is preserved separately in `source_quote`; do not try to synthesize an authoritative phrasing here.
- Do not invent claims that do not appear in any article.
- Focus on factual claims. Skip pure interpretation or background unless multiple outlets emphasize them.
- For each canonical claim, you MUST include an outlet entry for EVERY article in the input. If an article does not cover the claim, mark it "omitted".
- Aim for 5-25 canonical claims for the story.
"""


_PROMPT_HASH = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


async def _align_via_embeddings(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
    cache: Cache,
) -> AlignmentResult:
    """Run the embedding alignment with disk caching keyed on inputs + model."""
    import asyncio

    from . import align_embeddings

    payload_obj = {
        "articles": [
            {
                "article_id": a.id,
                "outlet_domain": a.outlet_domain,
                "claims": [c.model_dump(mode="json") for c in extractions[a.id].claims],
            }
            for a in articles
        ]
    }
    payload = json.dumps(payload_obj, indent=2, sort_keys=True)
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    backend_name = f"embeddings:{align_embeddings.DEFAULT_MODEL}"
    cached = cache.get("alignments", payload_hash, "embed-v1", backend_name)
    if cached is not None:
        return AlignmentResult.model_validate(cached)

    # SentenceTransformer.encode is sync; offload so we don't block the loop.
    result = await asyncio.to_thread(
        align_embeddings.align_claims_embeddings, articles, extractions
    )
    cache.set(
        "alignments",
        result.model_dump(mode="json"),
        payload_hash,
        "embed-v1",
        backend_name,
    )
    return result


async def align_claims(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
    llm: StructuredLLM,
    cache: Cache,
) -> AlignmentResult:
    # Prefer the embedding path when sentence-transformers is installed.
    # It's deterministic, doesn't hallucinate, doesn't return empty
    # outlets, and matches what the docstring at the top of this module
    # describes as the production path. The LLM path remains as a
    # fallback when the optional dependency isn't installed.
    from . import align_embeddings

    if align_embeddings.is_available():
        return await _align_via_embeddings(articles, extractions, cache)

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

    try:
        parsed = await llm.parse(
            system=_SYSTEM_PROMPT, user=payload, schema=AlignmentResult
        )
    except Exception as exc:
        # The LLM couldn't produce a schema-conforming AlignmentResult after
        # its retries (common with small open-weight models that echo the
        # JSON Schema back instead of filling it). Degrade to a per-article
        # alignment so the rest of the pipeline — and the HTML report — can
        # still surface what each outlet said. Cross-outlet consensus tiers
        # will be useless here; flag that explicitly to the operator.
        print(
            f"WARN: alignment LLM call failed ({type(exc).__name__}); "
            "falling back to per-article alignment with no cross-outlet "
            "matching. Use a stronger model (qwen3:8b or larger) for real "
            "consensus tiers.",
            file=sys.stderr,
        )
        return _fallback_alignment(articles, extractions)

    article_ids = [a.id for a in articles]
    article_to_outlet = {a.id: a.outlet_domain for a in articles}
    valid_article_ids = set(article_ids)
    valid_domains = set(article_to_outlet.values())

    filled: list[CanonicalClaim] = []
    for cc in parsed.canonical_claims:
        # Drop any outlet coverage the LLM invented — wrong article_id,
        # hallucinated domain, or mismatched article/domain pair. Weak
        # models routinely emit `outlet_domain="example.com"` or repeat
        # an article_id from a different sample. We never silently render
        # an attribution that doesn't trace to a real input article.
        clean_outlets: list[OutletCoverage] = []
        for oc in cc.outlets:
            if oc.article_id not in valid_article_ids:
                print(
                    f"WARN: dropping hallucinated article_id {oc.article_id!r} "
                    f"from canonical claim {cc.canonical_text[:60]!r}",
                    file=sys.stderr,
                )
                continue
            expected_domain = article_to_outlet[oc.article_id]
            if oc.outlet_domain != expected_domain:
                if oc.outlet_domain not in valid_domains:
                    print(
                        f"WARN: dropping hallucinated outlet_domain "
                        f"{oc.outlet_domain!r} from canonical claim "
                        f"{cc.canonical_text[:60]!r}",
                        file=sys.stderr,
                    )
                    continue
                # The domain is one of ours but doesn't match this
                # article_id — repair by trusting the article_id.
                oc = oc.model_copy(update={"outlet_domain": expected_domain})
            clean_outlets.append(oc)

        # If the LLM produced canonical_text but no outlets at all (the
        # single most common failure mode in real samples), recover by
        # fuzzy-matching the canonical_text against each article's
        # extracted claims and attaching the originating article.
        # Without this, the matrix would mark every outlet OMITTED and
        # the report becomes useless.
        if not clean_outlets:
            clean_outlets = _recover_outlets_by_similarity(
                cc.canonical_text, articles, extractions
            )
            if clean_outlets:
                print(
                    f"WARN: LLM returned no outlets for {cc.canonical_text[:60]!r}; "
                    f"recovered {len(clean_outlets)} by fuzzy claim match",
                    file=sys.stderr,
                )

        present = {oc.article_id for oc in clean_outlets}
        outlets = list(clean_outlets)
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


_RECOVERY_SIMILARITY_THRESHOLD = 0.6


def _recover_outlets_by_similarity(
    canonical_text: str,
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
) -> list[OutletCoverage]:
    """Reattach outlet coverage by fuzzy-matching against extracted claims.

    Used when the alignment LLM returns a canonical claim with an empty
    `outlets` list. Walks each article's extracted claims, scores them
    against `canonical_text` with difflib's SequenceMatcher ratio, and
    attaches the best match per article if its similarity meets the
    threshold. Status, quote, attribution, position, and provenance are
    copied verbatim from the matched extracted claim — no field is
    invented.
    """
    recovered: list[OutletCoverage] = []
    canonical_lower = canonical_text.lower()
    for article in articles:
        best_ratio = 0.0
        best_claim = None
        for claim in extractions[article.id].claims:
            ratio = difflib.SequenceMatcher(
                None, canonical_lower, claim.claim_text.lower()
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_claim = claim
        if best_claim is None or best_ratio < _RECOVERY_SIMILARITY_THRESHOLD:
            continue
        status = (
            CoverageStatus.ATTRIBUTED
            if best_claim.claim_type == ClaimType.ATTRIBUTED
            else CoverageStatus.ASSERTED
        )
        recovered.append(
            OutletCoverage(
                outlet_domain=article.outlet_domain,
                article_id=article.id,
                status=status,
                source_quote=best_claim.source_quote,
                attributed_to=best_claim.attributed_to,
                provenance=best_claim.provenance,
                position=best_claim.position,
            )
        )
    return recovered


def _fallback_alignment(
    articles: list[Article],
    extractions: Mapping[str, ExtractionResult],
) -> AlignmentResult:
    """Trivial alignment used when the LLM can't produce a valid result.

    Each extracted claim becomes its own canonical claim with one outlet
    entry (the article it came from); all other articles are marked
    omitted. This is intentionally degraded — no cross-outlet matching
    happens — but it lets the pipeline render a coverage matrix instead
    of crashing.
    """
    article_ids = [a.id for a in articles]
    article_to_outlet = {a.id: a.outlet_domain for a in articles}

    canonical: list[CanonicalClaim] = []
    for article in articles:
        for claim in extractions[article.id].claims:
            if claim.claim_type == ClaimType.ATTRIBUTED:
                status = CoverageStatus.ATTRIBUTED
            else:
                status = CoverageStatus.ASSERTED
            outlets = [
                OutletCoverage(
                    outlet_domain=article.outlet_domain,
                    article_id=article.id,
                    status=status,
                    source_quote=claim.source_quote,
                    attributed_to=claim.attributed_to,
                    provenance=claim.provenance,
                    position=claim.position,
                )
            ]
            for aid in article_ids:
                if aid == article.id:
                    continue
                outlets.append(
                    OutletCoverage(
                        outlet_domain=article_to_outlet[aid],
                        article_id=aid,
                        status=CoverageStatus.OMITTED,
                    )
                )
            canonical.append(
                CanonicalClaim(canonical_text=claim.claim_text, outlets=outlets)
            )

    return AlignmentResult(canonical_claims=canonical)
