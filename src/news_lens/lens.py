"""Per-article framing analysis via a structured-output LLM.

Surfaces signals that may differ across outlets covering the same story:
headline framing, loaded vocabulary, source diversity, stance.

The model is provided as a `StructuredLLM` backend (Claude / local
Llama / etc.) — see backends/.

Migration path away from an LLM
-------------------------------

LLMs are overkill for this task. A specialised pipeline gives equal or
better quality at a fraction of the cost and latency:

- `headline_framing` → fine-tune DistilRoBERTa on news headline
  sentiment (positive / neutral / negative). The
  `mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis`
  model is a starting point; better to fine-tune on a political-news
  set since financial-news framing differs.
- `loaded_terms` → maintain a paired-term lexicon
  (regime↔government, scheme↔plan, sweeping↔broad, …) and dictionary-
  match. Augment with a sentiment classifier scoring noun/adjective
  candidates against a Reuters wire baseline. The current LLM
  sometimes invents pairings; a curated lexicon is auditable and
  consistent.
- `sources_quoted` → spaCy NER (PERSON / ORG) with a dependency-parse
  filter for entities adjacent to reporting verbs (said, told,
  according-to). spaCy's `en_core_web_trf` is accurate enough for
  most news prose.
- `stance_summary` → a short LLM call OR an extractive 1-sentence
  summary (the article's lede sentence is a decent proxy).

A `ClassicalLensBackend` would expose `analyze_lens(article) ->
ArticleLens` with the same shape this module returns. Wire it in as a
sibling of the StructuredLLM-based path; the cache key already
namespaces by backend name.
"""

from __future__ import annotations

import hashlib
import sys

from .backends.base import StructuredLLM
from .cache import Cache
from .models import Article, ArticleLens, LensSignals, LoadedTerm


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


_PROMPT_HASH = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


async def analyze_lens(
    article: Article,
    llm: StructuredLLM,
    cache: Cache,
) -> ArticleLens:
    cached = cache.get("lenses", article.id, _PROMPT_HASH, llm.name)
    if cached is not None:
        return ArticleLens.model_validate(cached)

    user_text = (
        f"Outlet: {article.outlet_domain}\n"
        f"Headline: {article.title or '(no title)'}\n\n"
        f"Article body:\n---\n{article.body}\n---"
    )

    signals = await llm.parse(
        system=_SYSTEM_PROMPT, user=user_text, schema=LensSignals
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
    cache.set("lenses", lens.model_dump(mode="json"), article.id, _PROMPT_HASH, llm.name)
    return lens
