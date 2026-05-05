"""Per-article framing analysis using Claude.

Surfaces signals that may differ across outlets covering the same story:
headline framing, loaded vocabulary, source diversity, stance. The point is
to make framing visible alongside the facts — not to label any outlet good
or bad. Every loaded term carries a verbatim citation so a reader can check
the call.
"""

from __future__ import annotations

import hashlib
import sys

import anthropic

from .cache import Cache
from .models import Article, ArticleLens, LensSignals, LoadedTerm


_MODEL = "claude-opus-4-7"

_SYSTEM_PROMPT = """\
You are a media analyst examining how a single article framed its subject. Your goal is to surface framing signals that may differ across outlets covering the same story — not to label the article good or bad.

For the article, extract:

- `headline_framing`: How the headline and lede frame the main subject:
  - "positive": frames favorably (success, achievement, breakthrough)
  - "neutral": just-the-facts presentation, descriptive
  - "negative": frames unfavorably (controversy, failure, threat)
  - "mixed": multiple charged framings present

- `loaded_terms`: Charged or evaluative terms used in the article that have neutral alternatives. Examples:
    "regime" (neutral: "government"), "scheme" (neutral: "plan"),
    "crackdown" (neutral: "enforcement"), "lavish" (neutral: "expensive"),
    "sweeping" (neutral: "broad"), "claim" (vs neutral: "say"),
    "insurgents" / "freedom fighters" / "rebels" / "terrorists" (vs neutral: "armed group").
  For each, capture:
    - `term`: the loaded term as used in the article
    - `neutral_alternative`: a neutral alternative that preserves the meaning without the connotation
    - `in_sentence`: the verbatim sentence containing the term, copied exactly from the article body
  Only include terms that are clearly evaluative or carry connotation — skip purely descriptive vocabulary. Aim for 0-10 terms.

- `sources_quoted`: Named sources quoted or cited in the article (people by name, organizations, agencies). Just the names — no need to include what they said. Capture all distinct named sources, in order of first appearance.

- `stance_summary`: One sentence characterizing the article's overall framing toward the main subject. Be specific about the angle (e.g. "treats the policy as a security necessity," "skeptical of administration claims," "neutral wire-style summary," "centers economic impact over human cost").

Rules:
- Base every signal on the article's text only. Do not import outside knowledge about the outlet or its reputation.
- Loaded-term `in_sentence` MUST be a verbatim substring of the article body — no edits, no ellipses, no paraphrasing.
- If the article is genuinely neutral, return an empty `loaded_terms` list and `headline_framing: "neutral"`. Do not manufacture findings to fill quotas.
- "Charged" is not the same as "negative." Praise terms like "groundbreaking," "historic," "lavish" are also loaded.
"""


async def analyze_lens(
    article: Article,
    client: anthropic.AsyncAnthropic,
    cache: Cache,
) -> ArticleLens:
    prompt_hash = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]
    cached = cache.get("lenses", article.id, prompt_hash)
    if cached is not None:
        return ArticleLens.model_validate(cached)

    user_text = (
        f"Outlet: {article.outlet_domain}\n"
        f"Headline: {article.title or '(no title)'}\n\n"
        f"Article body:\n---\n{article.body}\n---"
    )

    response = await client.messages.parse(
        model=_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_text}],
        output_format=LensSignals,
    )

    signals = response.parsed_output
    if signals is None:
        raise RuntimeError(
            f"Lens analysis returned no parseable output for {article.url}"
        )

    valid_terms: list[LoadedTerm] = []
    for term in signals.loaded_terms:
        if term.in_sentence and term.in_sentence in article.body:
            valid_terms.append(term)
        else:
            print(
                f"WARN: dropping loaded term with non-verbatim citation in "
                f"{article.outlet_domain}: {term.term!r}",
                file=sys.stderr,
            )

    cleaned = LensSignals(
        headline_framing=signals.headline_framing,
        loaded_terms=valid_terms,
        sources_quoted=signals.sources_quoted,
        stance_summary=signals.stance_summary,
    )

    lens = ArticleLens(
        article_id=article.id,
        outlet_domain=article.outlet_domain,
        signals=cleaned,
    )
    cache.set("lenses", lens.model_dump(mode="json"), article.id, prompt_hash)
    return lens
