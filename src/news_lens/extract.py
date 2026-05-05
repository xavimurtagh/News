"""Extract atomic claims from a single article using Claude.

Each claim must cite a verbatim span from the article body. The post-call
filter drops any claim whose `source_quote` is not a substring of the body —
this guards against the model paraphrasing the citation, which would silently
break the "every fact links back to a sentence" invariant the product
depends on.
"""

from __future__ import annotations

import hashlib
import sys

import anthropic

from .cache import Cache
from .models import Article, ExtractedClaim, ExtractionResult


_MODEL = "claude-opus-4-7"

_SYSTEM_PROMPT = """\
You are a careful news analyst extracting atomic factual claims from news articles. Your job is to identify discrete claims, classify each by how the article presents it, and link each claim back to the exact sentence(s) in the source.

For each claim, classify the type:
- "asserted": The article states this as a fact in its own voice (no attribution).
- "attributed": The article reports what a named source said, claimed, or alleged. Capture who said it in `attributed_to`.
- "interpretation": Analysis, characterization, opinion, or inference by the article (often unverifiable as fact).
- "background": Historical context or general knowledge presented without recent sourcing.

For each claim, capture:
- `claim_text`: A neutral, one-sentence canonical phrasing of the claim. Use simple, direct language. Strip out adjectives that imply judgment.
- `claim_type`: One of the four categories above.
- `attributed_to`: For "attributed" claims, the named source (a person, organization, or agency). Otherwise null.
- `source_quote`: A contiguous span from the article body that contains this claim. MUST appear verbatim in the article — no edits, no ellipses, no paraphrasing. This is the citation back to the source.
- `position`: Approximate 1-indexed paragraph number where the claim first appears.

Rules:
- Only extract claims that are clearly stated in the article. Do not infer, generalize, or add information.
- `source_quote` must be an exact verbatim substring of the article body. If you cannot find such a span, do not include the claim.
- Break compound sentences into separate atomic claims when each part is independently checkable.
- Skip headlines, captions, navigation, and metadata. Focus on body prose.
- Skip pure rhetorical or opinion statements unless they make a specific checkable factual claim.
- Aim for 5-25 claims per article — capture the most newsworthy and substantive claims.
"""


async def extract_claims(
    article: Article,
    client: anthropic.AsyncAnthropic,
    cache: Cache,
) -> ExtractionResult:
    prompt_hash = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
    cached = cache.get("extractions", article.id, prompt_hash)
    if cached is not None:
        return ExtractionResult.model_validate(cached)

    user_text = (
        f"Outlet: {article.outlet_domain}\n"
        f"Title: {article.title or '(no title)'}\n"
        f"URL: {article.url}\n\n"
        f"Article body:\n---\n{article.body}\n---"
    )

    response = await client.messages.parse(
        model=_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_text}],
        output_format=ExtractionResult,
    )

    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(
            f"Claim extraction returned no parseable output for {article.url}"
        )

    valid: list[ExtractedClaim] = []
    for claim in parsed.claims:
        if claim.source_quote and claim.source_quote in article.body:
            valid.append(claim)
        else:
            print(
                f"WARN: dropping claim with non-verbatim citation in {article.outlet_domain}: "
                f"{claim.claim_text!r}",
                file=sys.stderr,
            )

    result = ExtractionResult(claims=valid)
    cache.set("extractions", result.model_dump(mode="json"), article.id, prompt_hash)
    return result
