"""News Lens — multi-source fact abstraction with bias-lens analysis.

The pipeline takes a set of article URLs covering the same event and produces
a coverage matrix: which outlets asserted, attributed, contradicted, or
omitted each canonical claim, with citations back to the source sentences.
"""

from .models import (
    Article,
    CanonicalClaim,
    ClaimType,
    ConsensusTier,
    CoverageMatrix,
    CoverageStatus,
    ExtractedClaim,
    OutletCoverage,
    TieredClaim,
)

__all__ = [
    "Article",
    "CanonicalClaim",
    "ClaimType",
    "ConsensusTier",
    "CoverageMatrix",
    "CoverageStatus",
    "ExtractedClaim",
    "OutletCoverage",
    "TieredClaim",
]
