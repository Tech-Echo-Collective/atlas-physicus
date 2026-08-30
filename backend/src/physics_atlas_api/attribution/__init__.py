"""Versioned scientific-attribution contracts and pure calculations."""

from .contracts import (
    FRACTIONAL_ATTRIBUTION_V1,
    AuthorAttributionInput,
    ContributionEvidence,
    PaperTimeAffiliationAssertion,
    ScientificAttributionPolicy,
)
from .fractional import (
    AttributionShare,
    FractionalAttributionResult,
    calculate_fractional_attribution,
)

__all__ = [
    "FRACTIONAL_ATTRIBUTION_V1",
    "AttributionShare",
    "AuthorAttributionInput",
    "ContributionEvidence",
    "FractionalAttributionResult",
    "PaperTimeAffiliationAssertion",
    "ScientificAttributionPolicy",
    "calculate_fractional_attribution",
]
