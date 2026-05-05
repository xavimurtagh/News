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


class CoverageMatrix(BaseModel):
    """End-to-end pipeline output: articles plus tiered canonical claims."""

    articles: List[Article]
    claims: List[TieredClaim]
