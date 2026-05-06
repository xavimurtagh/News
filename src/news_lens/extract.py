"""Extract atomic claims from a single article via a structured-output LLM.

The LLM is provided as a `StructuredLLM` backend (see backends/), so this
module is agnostic to whether the call goes to Claude, a local Llama, or
anything else with a Pydantic-validated structured-output interface.

Each claim must cite a verbatim span from the article body. The post-call
filter drops any claim whose `source_quote` is not a substring of the
body — this guards against the model paraphrasing the citation, which
would silently break the "every fact links back to a sentence" invariant
the product depends on. The guard matters even more on weaker models
where citation drift is more frequent.
"""

from __future__ import annotations

import hashlib
import sys

from .backends.base import StructuredLLM
from .cache import Cache
from .models import Article, ExtractedClaim, ExtractionResult


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


_PROMPT_HASH = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


async def extract_claims(
    article: Article,
    llm: StructuredLLM,
    cache: Cache,
) -> ExtractionResult:
    cached = cache.get("extractions", article.id, _PROMPT_HASH, llm.name)
    if cached is not None:
        return ExtractionResult.model_validate(cached)

    user_text = (
        f"Outlet: {article.outlet_domain}\n"
        f"Title: {article.title or '(no title)'}\n"
        f"URL: {article.url}\n\n"
        f"Article body:\n---\n{article.body}\n---"
    )

    parsed = await llm.parse(
        system=_SYSTEM_PROMPT, user=user_text, schema=ExtractionResult
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
    cache.set(
        "extractions", result.model_dump(mode="json"), article.id, _PROMPT_HASH, llm.name
    )
    return result
