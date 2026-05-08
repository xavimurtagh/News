"""Per-article framing analysis via a structured-output LLM.

Surfaces signals that may differ across outlets covering the same story:
headline framing, loaded vocabulary, subtle framing devices (selective
hedging, charged attribution, etc.), source diversity, and overall stance.

The model is provided as a `StructuredLLM` backend (Claude / local Llama
/ etc.) — see backends/.

Symmetry note
-------------

The prompt below names left-coded AND right-coded loaded vocabulary
explicitly so the model isn't subtly biased toward flagging one
direction. The framing-device examples are also symmetric — every
pattern is shown going both ways. If you tune the prompt, hold this
property: any change should preserve symmetry across the political
spectrum.

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
- `framing_devices` → harder; some patterns (passive voice,
  hedging-word frequency) can be detected with spaCy + heuristics,
  but charged attribution and lede burying need either a fine-tuned
  classifier or an LLM. This is the strongest argument for keeping
  an LLM in the loop for lens analysis.
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
from .models import (
    Article,
    ArticleLens,
    FramingDevice,
    FramingDeviceType,
    LensSignals,
    LoadedTerm,
)


_SYSTEM_PROMPT = """\
You are a media analyst examining how a single article framed its subject. Your job is to surface framing signals that may differ across outlets covering the same story — both the obvious word choices and the subtler sentence-level patterns that shape how a reader interprets events.

CRITICAL: Apply your analysis SYMMETRICALLY to all political viewpoints. Loaded vocabulary and framing devices exist across the political spectrum; flagging only one direction is itself a bias.

Extract:

1. `headline_framing`: How the headline and lede frame the main subject:
   - "positive": frames favorably (success, achievement, breakthrough, vindication)
   - "neutral": just-the-facts presentation, descriptive
   - "negative": frames unfavorably (controversy, failure, threat, scandal)
   - "mixed": multiple charged framings present

2. `loaded_terms`: Charged or evaluative single words and short phrases that have neutral alternatives. Capture, for each:
   - `term`: the loaded term as used in the article
   - `neutral_alternative`: a neutral alternative that preserves the meaning
   - `in_sentence`: the verbatim sentence containing the term

   Examples spanning the spectrum (NOT exhaustive — flag whatever the article uses):
   - Right-coded: "regime", "Marxist", "groomer", "globalist", "illegal aliens", "woke", "soft on crime"
   - Left-coded: "extremist", "Christian nationalist", "alt-right", "anti-trans", "fascist", "election denier", "racist"
   - Both-sided pairs (one outlet uses A, another uses B for the same fact):
     "regime"/"government", "scheme"/"plan", "crackdown"/"enforcement",
     "claim"/"say", "controversial"/"prominent", "rioters"/"protesters",
     "insurgents"/"freedom fighters", "thug"/"young man",
     "sweeping"/"broad", "lavish"/"expensive"

   Only include genuinely loaded vocabulary. Skip purely descriptive words. Aim for 0-12 terms.

3. `framing_devices`: Sentence-level patterns BEYOND single-word choices that subtly shape interpretation. The most consequential framing is often the kind a casual reader doesn't notice. Flag instances of any of these (capture the verbatim sentence in `in_sentence`):

   - "selective_hedging": One side's claims get hedge words ("alleged", "claimed", "according to") while the other side's claims are asserted as fact. Examples:
     • Right-target: "Conservatives alleged voter fraud, while critics confirmed the election was secure."
     • Left-target: "Activists claim systemic racism exists, while research has shown disparities are due to other factors."

   - "passive_voice_asymmetry": Passive voice obscures an actor on one side; active voice names them on the other. Examples:
     • "Three protesters were killed by police" (active, names actor) vs "Three police officers died" (passive, hides actor) — applied selectively.
     • Same pattern in reverse: "An officer was injured by rioters" (passive on harm to officer) vs "Police shot a protester" (active on harm by police).

   - "charged_attribution": A descriptor or qualifier added to the source that wouldn't be applied to comparable figures on the other side. Examples:
     • "Controversial commentator Tucker Carlson said..." vs "MSNBC host Rachel Maddow said..." (only one is "controversial")
     • "Far-right activist X said..." while a comparably-positioned figure on the left is just "activist Y"
     • Reverse: "Far-left activist X said..." while a comparable right-side figure gets just "activist Y"

   - "lede_burying": A material caveat or counter-fact that a reasonable reader would expect near the top is placed deep in the article (paragraph 8+) instead. The cited sentence is the buried caveat.

   - "source_asymmetry": One side's sources get full direct quotes while the other side is paraphrased or summarized into a single sentence.

   - "implied_consensus": Phrases like "it is widely understood that...", "everyone knows...", "experts agree..." without naming who the experts are or how the consensus was measured. Cite the unsourced consensus claim.

   - "scare_quotes": Words placed in quotation marks to imply they're not really what they claim to be. Examples:
     • Trump's "victory" / Biden's "recovery" / the "scientific" consensus / "moderate" Republicans / "anti-racist" training

   - "numerical_framing": Choosing the percentage or denominator that supports the angle. "Only 40% support X" vs "Up to 60% have concerns about X" describing the same poll. Cite the framed sentence.

   - "euphemism": Softened language for actions that have a more direct description. Examples:
     • "enhanced interrogation" (torture), "officer-involved shooting" (police shot someone), "kinetic action" (military strikes), "involuntary extraction" (eviction).

   - "omission_flag": A counter-fact or context that materially changes the story which a reasonable reader would expect to be present. For OMISSION_FLAG only, `in_sentence` may be empty; describe what's missing in `description`.

   For each device, capture:
   - `device_type`: one of the categories above (lowercase, with underscores)
   - `description`: one sentence explaining what the article is doing and how it shapes interpretation
   - `in_sentence`: verbatim sentence(s) from the body. Empty for omission_flag.

   Aim for 0-8 devices per article. Prefer subtle ones over obvious ones — the value here is catching what a casual reader misses.

4. `sources_quoted`: Named sources quoted or cited in the article (people by name, organizations, agencies). Just the names, in order of first appearance.

5. `stance_summary`: One sentence characterizing the article's overall framing toward the main subject. Be specific about the angle (e.g. "treats the policy as a security necessity," "skeptical of administration claims," "neutral wire-style summary," "centers economic impact over human cost").

Rules:
- Base every signal on the article's text only. Do not import outside knowledge about the outlet's reputation.
- `in_sentence` MUST be a verbatim substring of the article body — no edits, no ellipses, no paraphrasing. (Exception: empty for omission_flag.)
- A genuinely neutral wire-style article should produce empty `loaded_terms`, empty `framing_devices`, and `headline_framing: "neutral"`. Do not manufacture findings to fill quotas.
- "Charged" is not the same as "negative." Praise terms ("groundbreaking", "historic", "vindicated") are also loaded.
- Hold the symmetry: if you'd flag "regime" used for a left-leaning government as loaded, also flag "regime" used for a right-leaning one. If you'd flag "extremist" applied to a right-wing figure, also flag it applied to a left-wing one.
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

    valid_devices: list[FramingDevice] = []
    for device in signals.framing_devices:
        # OMISSION_FLAG legitimately has no in_sentence (the device is the absence).
        if device.device_type == FramingDeviceType.OMISSION_FLAG:
            valid_devices.append(device)
            continue
        if device.in_sentence and device.in_sentence in article.body:
            valid_devices.append(device)
        else:
            print(
                f"WARN: dropping framing device with non-verbatim citation in "
                f"{article.outlet_domain}: {device.device_type.value}",
                file=sys.stderr,
            )

    cleaned = LensSignals(
        headline_framing=signals.headline_framing,
        loaded_terms=valid_terms,
        framing_devices=valid_devices,
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
