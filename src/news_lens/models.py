"""Domain models for the pipeline.

Two distinct claim concepts:

- ExtractedClaim — a single claim pulled from one article, classified by how
  THAT article presented it (asserted / attributed / interpretation /
  background) with a verbatim citation.

- CanonicalClaim — a unit of cross-article comparison. The same underlying
  proposition that may appear differently across outlets. Each canonical
  claim carries a per-outlet status (asserted / attributed / contradicted /
  omitted) and a citation per outlet that has it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    ASSERTED = "asserted"
    ATTRIBUTED = "attributed"
    INTERPRETATION = "interpretation"
    BACKGROUND = "background"


class CoverageStatus(str, Enum):
    ASSERTED = "asserted"
    ATTRIBUTED = "attributed"
    CONTRADICTED = "contradicted"
    OMITTED = "omitted"


class ConsensusTier(str, Enum):
    UNIVERSAL = "universal"
    MAJORITY = "majority"
    DISPUTED = "disputed"
    SINGLE_SOURCED = "single_sourced"
    ATTRIBUTED_ONLY = "attributed_only"


class Article(BaseModel):
    id: str
    url: str
    outlet_domain: str
    title: Optional[str] = None
    byline: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: datetime
    body: str
    paragraph_count: int = 0


class ExtractedClaim(BaseModel):
    """One atomic claim extracted from a single article."""

    claim_text: str = Field(
        description="Neutral one-sentence canonical phrasing of the claim."
    )
    claim_type: ClaimType = Field(
        description="How the article presents this claim."
    )
    attributed_to: Optional[str] = Field(
        default=None,
        description="Named source for attributed claims; null otherwise.",
    )
    source_quote: str = Field(
        description=(
            "Exact verbatim span from the article body containing this claim. "
            "Must appear in the article without modification."
        )
    )
    position: int = Field(
        description="Approximate 1-indexed paragraph number where the claim first appears."
    )


class ExtractionResult(BaseModel):
    claims: List[ExtractedClaim]


class OutletCoverage(BaseModel):
    """How one outlet handled a canonical claim."""

    outlet_domain: str
    article_id: str
    status: CoverageStatus
    source_quote: Optional[str] = None
    attributed_to: Optional[str] = None
    position: Optional[int] = Field(
        default=None,
        description="1-indexed paragraph position from the source article. Null when omitted.",
    )


class CanonicalClaim(BaseModel):
    """A factual proposition compared across articles."""

    canonical_text: str = Field(
        description=(
            "Neutral phrasing of the claim, abstracted from outlet-specific framing. "
            "Strip judgmental adjectives and loaded language."
        )
    )
    outlets: List[OutletCoverage]


class AlignmentResult(BaseModel):
    canonical_claims: List[CanonicalClaim]


class TieredClaim(BaseModel):
    """A canonical claim with its computed consensus tier."""

    canonical_text: str
    tier: ConsensusTier
    outlets: List[OutletCoverage]


class HeadlineFraming(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class LoadedTerm(BaseModel):
    """A charged or evaluative term with a neutral alternative."""

    term: str = Field(description="The loaded or charged term as used in the article.")
    neutral_alternative: str = Field(
        description="A neutral alternative that conveys the same meaning without the connotation."
    )
    in_sentence: str = Field(
        description="The verbatim sentence from the article body containing the term."
    )


class FramingDeviceType(str, Enum):
    """Sentence-level framing patterns beyond simple word choice."""

    SELECTIVE_HEDGING = "selective_hedging"
    PASSIVE_VOICE_ASYMMETRY = "passive_voice_asymmetry"
    CHARGED_ATTRIBUTION = "charged_attribution"
    LEDE_BURYING = "lede_burying"
    SOURCE_ASYMMETRY = "source_asymmetry"
    IMPLIED_CONSENSUS = "implied_consensus"
    SCARE_QUOTES = "scare_quotes"
    NUMERICAL_FRAMING = "numerical_framing"
    EUPHEMISM = "euphemism"
    OMISSION_FLAG = "omission_flag"


class FramingDevice(BaseModel):
    """One sentence-level framing pattern flagged in the article.

    Subtler than loaded vocabulary: catches hedging asymmetries, charged
    descriptors at attribution, scare quotes, lede placement, and similar.
    """

    device_type: FramingDeviceType = Field(
        description="Which kind of framing pattern this is."
    )
    description: str = Field(
        description=(
            "One-sentence description of what the article is doing in this "
            "passage and how it shapes interpretation."
        )
    )
    in_sentence: str = Field(
        description=(
            "Verbatim sentence(s) from the article body that exhibit this "
            "pattern. Empty string for OMISSION_FLAG (the device is the "
            "absence of something)."
        )
    )


class LensSignals(BaseModel):
    """Framing signals produced by the lens analyzer for one article."""

    headline_framing: HeadlineFraming = Field(
        description="How the headline and lede frame the main subject."
    )
    loaded_terms: List[LoadedTerm] = Field(
        default_factory=list,
        description="Charged or evaluative terms with neutral alternatives.",
    )
    framing_devices: List[FramingDevice] = Field(
        default_factory=list,
        description=(
            "Sentence-level framing patterns beyond simple word choice — "
            "selective hedging, charged attribution, lede burying, etc."
        ),
    )
    sources_quoted: List[str] = Field(
        default_factory=list,
        description="Named sources quoted or cited in the article.",
    )
    stance_summary: str = Field(
        description="One-sentence characterization of the article's overall framing."
    )


class ArticleLens(BaseModel):
    """Lens signals tied to a specific article."""

    article_id: str
    outlet_domain: str
    signals: LensSignals


class SyndicationGroup(BaseModel):
    """A set of articles whose body text overlaps substantially.

    Wire-service syndication (AP, Reuters, AFP) means three outlets running
    the same copy aren't three independent assertions. Surface the
    relationship so consumers don't read inflated consensus.
    """

    article_ids: List[str]
    similarity: float = Field(
        description="Minimum pairwise Jaccard similarity within the group, 0..1."
    )


class CoverageMatrix(BaseModel):
    """End-to-end pipeline output: articles, tiered claims, lens, syndication."""

    articles: List[Article]
    claims: List[TieredClaim]
    lenses: List[ArticleLens] = Field(default_factory=list)
    syndication_groups: List[SyndicationGroup] = Field(default_factory=list)
