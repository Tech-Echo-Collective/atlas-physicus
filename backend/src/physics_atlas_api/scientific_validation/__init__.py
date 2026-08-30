"""Pure scientific-evidence validation helpers.

These validators inspect linked evidence and never calculate public metric scores.
"""

from .reference_ecosystem import (
    REFERENCE_ECOSYSTEM_VALIDATION_VERSION,
    REFERENCE_SANITY_ANCHORS,
    AuthorshipEvidence,
    FieldAttributionEvidence,
    HistoricalCoverageEvidence,
    IdentityWarningEvidence,
    InstitutionEvidence,
    NormalizationEvidence,
    PaperEvidence,
    PaperTimeAffiliationEvidence,
    ProvenanceEvidence,
    ReferenceEcosystemEvidence,
    ReferenceEcosystemSummary,
    ReferenceEcosystemValidationReport,
    ResearcherEvidence,
    SanityAnchorDefinition,
    SanityAnchorObservation,
    ValidationIssue,
    validate_reference_ecosystem,
)

__all__ = [
    "REFERENCE_ECOSYSTEM_VALIDATION_VERSION",
    "REFERENCE_SANITY_ANCHORS",
    "AuthorshipEvidence",
    "FieldAttributionEvidence",
    "HistoricalCoverageEvidence",
    "IdentityWarningEvidence",
    "InstitutionEvidence",
    "NormalizationEvidence",
    "PaperEvidence",
    "PaperTimeAffiliationEvidence",
    "ProvenanceEvidence",
    "ReferenceEcosystemEvidence",
    "ReferenceEcosystemSummary",
    "ReferenceEcosystemValidationReport",
    "ResearcherEvidence",
    "SanityAnchorDefinition",
    "SanityAnchorObservation",
    "ValidationIssue",
    "validate_reference_ecosystem",
]
