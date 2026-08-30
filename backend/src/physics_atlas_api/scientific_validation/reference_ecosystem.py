"""Validate a linked scientific reference ecosystem without producing rankings.

The unit of review is the evidence chain from a paper to its canonical authors,
paper-time affiliations, institutions, field attribution, and reconstructable
normalization.  This prevents an isolated institution or researcher value from
being mistaken for validated scientific evidence.
"""

from dataclasses import dataclass
from typing import Literal

REFERENCE_ECOSYSTEM_VALIDATION_VERSION = "reference-ecosystem-validation-v1"

ResolutionStatus = Literal["resolved", "unresolved", "ambiguous"]
FieldMappingStatus = Literal["mapped", "unmapped", "ambiguous"]
IdentityWarningKind = Literal["possible-merge", "possible-split"]
ObservationStatus = Literal["available", "missing"]
IssueSeverity = Literal["fault", "warning"]
ValidationStatus = Literal["healthy", "review-required", "invalid"]


@dataclass(frozen=True)
class ProvenanceEvidence:
    dataset_version: str | None
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class PaperEvidence:
    paper_id: str
    publication_year: int | None
    expected_researcher_ids: tuple[str, ...]
    provenance: ProvenanceEvidence


@dataclass(frozen=True)
class ResearcherEvidence:
    researcher_id: str
    persistent_ids: tuple[tuple[str, str], ...]
    provenance: ProvenanceEvidence


@dataclass(frozen=True)
class AuthorshipEvidence:
    paper_id: str
    researcher_id: str
    provenance: ProvenanceEvidence


@dataclass(frozen=True)
class InstitutionEvidence:
    institution_id: str
    canonical_name: str
    persistent_ids: tuple[tuple[str, str], ...]
    provenance: ProvenanceEvidence


@dataclass(frozen=True)
class PaperTimeAffiliationEvidence:
    paper_id: str
    researcher_id: str
    institution_id: str | None
    resolution_status: ResolutionStatus
    raw_affiliation_label: str | None
    candidate_institution_ids: tuple[str, ...]
    observed_year: int | None
    fractional_weight: float | None
    provenance: ProvenanceEvidence

    def __post_init__(self) -> None:
        if self.fractional_weight is not None and not 0 <= self.fractional_weight <= 1:
            raise ValueError("fractional_weight must be between zero and one")


@dataclass(frozen=True)
class IdentityWarningEvidence:
    warning_id: str
    kind: IdentityWarningKind
    researcher_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class FieldAttributionEvidence:
    paper_id: str
    provider: str
    raw_categories: tuple[str, ...]
    field_id: str | None
    field_weight: float | None
    unmapped_field_mass: float
    mapping_status: FieldMappingStatus
    mapping_version: str | None
    ontology_version: str | None
    provenance: ProvenanceEvidence
    weighting_policy_version: str | None = None
    reconciliation_version: str | None = None

    def __post_init__(self) -> None:
        if self.field_weight is not None and not 0 <= self.field_weight <= 1:
            raise ValueError("field_weight must be between zero and one")
        if not 0 <= self.unmapped_field_mass <= 1:
            raise ValueError("unmapped_field_mass must be between zero and one")


@dataclass(frozen=True)
class HistoricalCoverageEvidence:
    required_complete_years: tuple[int, ...]
    observed_complete_years: tuple[int, ...]
    excluded_partial_years: tuple[int, ...]
    provenance: ProvenanceEvidence


@dataclass(frozen=True)
class NormalizationEvidence:
    metric_id: str
    entity_id: str
    scope_id: str
    observation_status: ObservationStatus
    raw_value: float | None
    normalized_value: float | None
    reconstructed_normalized_value: float | None
    normalization_version: str | None
    reconstruction_input_refs: tuple[str, ...]
    provenance: ProvenanceEvidence


@dataclass(frozen=True)
class SanityAnchorDefinition:
    anchor_id: str
    label: str


# These are recognizable identity/linkage cases, not benchmarks or an ordering.
REFERENCE_SANITY_ANCHORS: tuple[SanityAnchorDefinition, ...] = (
    SanityAnchorDefinition("ias", "Institute for Advanced Study"),
    SanityAnchorDefinition("princeton", "Princeton University"),
    SanityAnchorDefinition("harvard", "Harvard University"),
    SanityAnchorDefinition("caltech", "California Institute of Technology"),
    SanityAnchorDefinition("ucsb-kitp", "UC Santa Barbara / KITP"),
    SanityAnchorDefinition("stony-brook", "Stony Brook University"),
    SanityAnchorDefinition("perimeter", "Perimeter Institute"),
)


@dataclass(frozen=True)
class SanityAnchorObservation:
    anchor_id: str
    institution_id: str | None


@dataclass(frozen=True)
class ReferenceEcosystemEvidence:
    dataset_version: str
    expected_ontology_version: str
    expected_mapping_versions: tuple[tuple[str, str], ...]
    expected_normalization_versions: tuple[tuple[str, str], ...]
    papers: tuple[PaperEvidence, ...]
    researchers: tuple[ResearcherEvidence, ...]
    authorships: tuple[AuthorshipEvidence, ...]
    affiliations: tuple[PaperTimeAffiliationEvidence, ...]
    institutions: tuple[InstitutionEvidence, ...]
    identity_warnings: tuple[IdentityWarningEvidence, ...]
    field_attributions: tuple[FieldAttributionEvidence, ...]
    historical_coverage: HistoricalCoverageEvidence
    normalizations: tuple[NormalizationEvidence, ...]
    sanity_anchors: tuple[SanityAnchorObservation, ...] = ()
    expected_field_weighting_policy_version: str | None = None
    expected_field_reconciliation_version: str | None = None

    def __post_init__(self) -> None:
        if not self.dataset_version.strip():
            raise ValueError("dataset_version must be non-empty")
        if not self.expected_ontology_version.strip():
            raise ValueError("expected_ontology_version must be non-empty")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: IssueSeverity
    entity_type: str
    entity_id: str
    related_ids: tuple[str, ...]
    detail: str


@dataclass(frozen=True)
class ReferenceEcosystemSummary:
    paper_count: int
    researcher_count: int
    authorship_count: int
    affiliation_assertion_count: int
    institution_count: int
    resolved_affiliation_count: int
    unresolved_affiliation_count: int
    ambiguous_affiliation_count: int
    paper_author_link_coverage: float | None
    paper_time_affiliation_coverage: float | None
    field_attribution_coverage: float | None
    historical_year_coverage: float | None
    normalization_record_count: int
    missing_normalization_count: int


@dataclass(frozen=True)
class ReferenceEcosystemValidationReport:
    report_version: str
    dataset_version: str
    status: ValidationStatus
    summary: ReferenceEcosystemSummary
    issues: tuple[ValidationIssue, ...]
    sanity_anchors: tuple[SanityAnchorObservation, ...]

    @property
    def passes(self) -> bool:
        return self.status == "healthy"


def _coverage(numerator: int, denominator: int) -> float | None:
    """Return unknown rather than manufacturing zero for an absent denominator."""
    return numerator / denominator if denominator else None


def _issue(
    code: str,
    severity: IssueSeverity,
    entity_type: str,
    entity_id: str,
    detail: str,
    related_ids: tuple[str, ...] = (),
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        related_ids=tuple(sorted(related_ids)),
        detail=detail,
    )


def _provenance_issues(
    entity_type: str,
    entity_id: str,
    provenance: ProvenanceEvidence,
    dataset_version: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not provenance.source_refs:
        issues.append(
            _issue(
                "provenance.missing-source-reference",
                "fault",
                entity_type,
                entity_id,
                "Evidence has no source reference and cannot be reconstructed.",
            )
        )
    if provenance.dataset_version is None:
        issues.append(
            _issue(
                "provenance.missing-dataset-version",
                "fault",
                entity_type,
                entity_id,
                "Evidence has no dataset version; missing is not treated as zero.",
            )
        )
    elif provenance.dataset_version != dataset_version:
        issues.append(
            _issue(
                "provenance.dataset-version-mismatch",
                "fault",
                entity_type,
                entity_id,
                "Evidence belongs to a different dataset version.",
                (provenance.dataset_version, dataset_version),
            )
        )
    return issues


def _validate_links(evidence: ReferenceEcosystemEvidence) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    papers = {item.paper_id: item for item in evidence.papers}
    researchers = {item.researcher_id: item for item in evidence.researchers}
    institutions = {item.institution_id: item for item in evidence.institutions}
    authorship_keys = {
        (item.paper_id, item.researcher_id) for item in evidence.authorships
    }

    for paper in evidence.papers:
        for researcher_id in sorted(set(paper.expected_researcher_ids)):
            if researcher_id not in researchers:
                issues.append(
                    _issue(
                        "paper-author.missing-researcher",
                        "fault",
                        "paper",
                        paper.paper_id,
                        "A declared paper author has no canonical researcher record.",
                        (researcher_id,),
                    )
                )
            if (paper.paper_id, researcher_id) not in authorship_keys:
                issues.append(
                    _issue(
                        "paper-author.missing-link",
                        "fault",
                        "paper",
                        paper.paper_id,
                        "A declared paper author has no authorship link.",
                        (researcher_id,),
                    )
                )

    for authorship in evidence.authorships:
        key = (authorship.paper_id, authorship.researcher_id)
        if authorship.paper_id not in papers:
            issues.append(
                _issue(
                    "paper-author.unknown-paper",
                    "fault",
                    "authorship",
                    "::".join(key),
                    "Authorship references a paper outside the reviewed ecosystem.",
                    key,
                )
            )
        if authorship.researcher_id not in researchers:
            issues.append(
                _issue(
                    "paper-author.unknown-researcher",
                    "fault",
                    "authorship",
                    "::".join(key),
                    "Authorship references an unknown canonical researcher.",
                    key,
                )
            )

    affiliation_keys = {
        (item.paper_id, item.researcher_id) for item in evidence.affiliations
    }
    for paper_id, researcher_id in sorted(authorship_keys):
        if (paper_id, researcher_id) not in affiliation_keys:
            issues.append(
                _issue(
                    "paper-time-affiliation.missing",
                    "fault",
                    "authorship",
                    f"{paper_id}::{researcher_id}",
                    "Authorship has no paper-time affiliation evidence.",
                    (paper_id, researcher_id),
                )
            )

    for affiliation in evidence.affiliations:
        key = (affiliation.paper_id, affiliation.researcher_id)
        entity_id = "::".join(key)
        if key not in authorship_keys:
            issues.append(
                _issue(
                    "paper-time-affiliation.missing-authorship",
                    "fault",
                    "paper-time-affiliation",
                    entity_id,
                    "Affiliation evidence has no corresponding authorship link.",
                    key,
                )
            )
        linked_paper = papers.get(affiliation.paper_id)
        if (
            linked_paper is not None
            and linked_paper.publication_year is not None
            and affiliation.observed_year != linked_paper.publication_year
        ):
            issues.append(
                _issue(
                    "paper-time-affiliation.year-mismatch",
                    "fault",
                    "paper-time-affiliation",
                    entity_id,
                    "Affiliation year does not match the paper publication year.",
                )
            )
        if affiliation.resolution_status == "resolved":
            if affiliation.institution_id is None:
                issues.append(
                    _issue(
                        "paper-time-affiliation.resolved-without-institution",
                        "fault",
                        "paper-time-affiliation",
                        entity_id,
                        "Resolved affiliation has no canonical institution reference.",
                    )
                )
            elif affiliation.institution_id not in institutions:
                issues.append(
                    _issue(
                        "paper-time-affiliation.unknown-institution",
                        "fault",
                        "paper-time-affiliation",
                        entity_id,
                        "Resolved affiliation references an unknown institution.",
                        (affiliation.institution_id,),
                    )
                )
            if affiliation.fractional_weight is None:
                issues.append(
                    _issue(
                        "paper-time-affiliation.missing-fractional-weight",
                        "fault",
                        "paper-time-affiliation",
                        entity_id,
                        "Resolved affiliation has no fractional attribution weight.",
                    )
                )
            elif affiliation.fractional_weight == 0:
                issues.append(
                    _issue(
                        "paper-time-affiliation.zero-fractional-weight",
                        "fault",
                        "paper-time-affiliation",
                        entity_id,
                        "A resolved affiliation must have positive evidence weight.",
                    )
                )
        else:
            issues.append(
                _issue(
                    f"paper-time-affiliation.{affiliation.resolution_status}",
                    "warning",
                    "paper-time-affiliation",
                    entity_id,
                    "Affiliation remains unresolved; no ownership or zero is inferred.",
                    affiliation.candidate_institution_ids,
                )
            )
            if affiliation.fractional_weight is not None:
                issues.append(
                    _issue(
                        "paper-time-affiliation.unresolved-has-weight",
                        "fault",
                        "paper-time-affiliation",
                        entity_id,
                        "Unresolved or ambiguous affiliation evidence cannot "
                        "receive weight.",
                    )
                )
    return issues


def _validate_identity_warnings(
    evidence: ReferenceEcosystemEvidence,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    researcher_ids = {item.researcher_id for item in evidence.researchers}
    for warning in evidence.identity_warnings:
        issues.append(
            _issue(
                f"identity.{warning.kind}",
                "warning",
                "identity-warning",
                warning.warning_id,
                warning.detail,
                warning.researcher_ids,
            )
        )
        unknown = tuple(
            item for item in warning.researcher_ids if item not in researcher_ids
        )
        if unknown:
            issues.append(
                _issue(
                    "identity.warning-unknown-researcher",
                    "fault",
                    "identity-warning",
                    warning.warning_id,
                    "Identity warning references an unknown researcher.",
                    unknown,
                )
            )
        if not warning.evidence_refs:
            issues.append(
                _issue(
                    "identity.warning-missing-evidence",
                    "fault",
                    "identity-warning",
                    warning.warning_id,
                    "Merge or split warning has no reviewable evidence reference.",
                )
            )
    return issues


def _validate_fields(evidence: ReferenceEcosystemEvidence) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    papers = {item.paper_id for item in evidence.papers}
    expected_versions = dict(evidence.expected_mapping_versions)
    records_by_paper: dict[str, list[FieldAttributionEvidence]] = {}
    for item in evidence.field_attributions:
        records_by_paper.setdefault(item.paper_id, []).append(item)
        entity_id = f"{item.paper_id}::{item.provider}::{item.field_id or 'missing'}"
        if item.paper_id not in papers:
            issues.append(
                _issue(
                    "field.unknown-paper",
                    "fault",
                    "field-attribution",
                    entity_id,
                    "Field attribution references an unknown paper.",
                    (item.paper_id,),
                )
            )
        expected_mapping = expected_versions.get(item.provider)
        if expected_mapping is None or item.mapping_version != expected_mapping:
            issues.append(
                _issue(
                    "field.mapping-version-mismatch",
                    "fault",
                    "field-attribution",
                    entity_id,
                    "Provider field mapping version does not match the review "
                    "manifest.",
                )
            )
        if item.ontology_version != evidence.expected_ontology_version:
            issues.append(
                _issue(
                    "field.ontology-version-mismatch",
                    "fault",
                    "field-attribution",
                    entity_id,
                    "Field attribution uses a different ontology version.",
                )
            )
        if (
            evidence.expected_field_weighting_policy_version is None
            or item.weighting_policy_version
            != evidence.expected_field_weighting_policy_version
        ):
            issues.append(
                _issue(
                    "field.weighting-policy-version-mismatch",
                    "fault",
                    "field-attribution",
                    entity_id,
                    "Field weighting policy version does not match the review "
                    "manifest.",
                )
            )
        if (
            evidence.expected_field_reconciliation_version is None
            or item.reconciliation_version
            != evidence.expected_field_reconciliation_version
        ):
            issues.append(
                _issue(
                    "field.reconciliation-version-mismatch",
                    "fault",
                    "field-attribution",
                    entity_id,
                    "Cross-provider field reconciliation version does not match "
                    "the review manifest.",
                )
            )
        if not item.raw_categories:
            issues.append(
                _issue(
                    "field.missing-raw-category",
                    "fault",
                    "field-attribution",
                    entity_id,
                    "Raw provider categories were not preserved.",
                )
            )
        if item.mapping_status == "mapped":
            if item.field_id is None:
                issues.append(
                    _issue(
                        "field.mapped-without-field",
                        "fault",
                        "field-attribution",
                        entity_id,
                        "Mapped field evidence has no canonical field identifier.",
                    )
                )
            if item.field_weight is None:
                issues.append(
                    _issue(
                        "field.missing-weight",
                        "fault",
                        "field-attribution",
                        entity_id,
                        "Mapped field evidence has no attribution weight.",
                    )
                )
            elif item.field_weight == 0:
                issues.append(
                    _issue(
                        "field.zero-weight",
                        "fault",
                        "field-attribution",
                        entity_id,
                        "A mapped field must have positive attribution weight.",
                    )
                )
        else:
            issues.append(
                _issue(
                    f"field.{item.mapping_status}",
                    "warning",
                    "field-attribution",
                    entity_id,
                    "Field evidence remains unresolved and is not encoded as zero.",
                )
            )
            if item.field_weight is not None:
                issues.append(
                    _issue(
                        "field.unresolved-has-weight",
                        "fault",
                        "field-attribution",
                        entity_id,
                        "Unmapped or ambiguous field evidence cannot receive weight.",
                    )
                )

    for paper_id in sorted(papers):
        records = records_by_paper.get(paper_id, [])
        if not records:
            issues.append(
                _issue(
                    "field.missing-attribution",
                    "fault",
                    "paper",
                    paper_id,
                    "Paper has no field mapping evidence.",
                )
            )
            continue
        mapped_weights = [
            item.field_weight
            for item in records
            if item.mapping_status == "mapped" and item.field_weight is not None
        ]
        mapped_count = sum(item.mapping_status == "mapped" for item in records)
        mapped_field_ids = [
            item.field_id
            for item in records
            if item.mapping_status == "mapped" and item.field_id is not None
        ]
        duplicate_fields = tuple(
            sorted(
                {
                    field_id
                    for field_id in mapped_field_ids
                    if mapped_field_ids.count(field_id) > 1
                }
            )
        )
        if duplicate_fields:
            issues.append(
                _issue(
                    "field.duplicate-ledger-field",
                    "fault",
                    "field-attribution",
                    paper_id,
                    "A selected cross-provider ledger must contain one row per "
                    "canonical field.",
                    duplicate_fields,
                )
            )
        unmapped_masses = {item.unmapped_field_mass for item in records}
        if len(unmapped_masses) != 1:
            issues.append(
                _issue(
                    "field.unmapped-mass-inconsistent",
                    "fault",
                    "field-attribution",
                    paper_id,
                    "Selected paper-ledger rows disagree about explicit unmapped mass.",
                )
            )
            continue
        unmapped_mass = next(iter(unmapped_masses))
        if unmapped_mass > 0:
            issues.append(
                _issue(
                    "field.unmapped-mass",
                    "warning",
                    "field-attribution",
                    paper_id,
                    "Selected cross-provider evidence retains explicit unmapped "
                    "field mass.",
                )
            )
        if len(mapped_weights) == mapped_count:
            if abs(sum(mapped_weights) + unmapped_mass - 1.0) > 1e-9:
                issues.append(
                    _issue(
                        "field.weight-conservation-failed",
                        "fault",
                        "field-attribution",
                        paper_id,
                        "Mapped field weights plus explicit unmapped mass do not "
                        "conserve one selected cross-provider paper ledger.",
                    )
                )
    return issues


def _validate_historical_coverage(
    evidence: ReferenceEcosystemEvidence,
) -> list[ValidationIssue]:
    coverage = evidence.historical_coverage
    required = set(coverage.required_complete_years)
    observed = set(coverage.observed_complete_years)
    excluded = set(coverage.excluded_partial_years)
    missing = tuple(str(item) for item in sorted(required - observed))
    issues: list[ValidationIssue] = []
    if missing:
        issues.append(
            _issue(
                "history.incomplete-required-years",
                "fault",
                "historical-coverage",
                evidence.dataset_version,
                "Required complete publication years are absent.",
                missing,
            )
        )
    overlap = tuple(str(item) for item in sorted(required & excluded))
    if overlap:
        issues.append(
            _issue(
                "history.partial-year-used-as-complete",
                "fault",
                "historical-coverage",
                evidence.dataset_version,
                "A declared partial year is also required as a complete year.",
                overlap,
            )
        )
    return issues


def _validate_normalizations(
    evidence: ReferenceEcosystemEvidence,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    expected_versions = dict(evidence.expected_normalization_versions)
    for item in evidence.normalizations:
        entity_id = f"{item.metric_id}::{item.entity_id}::{item.scope_id}"
        if item.normalization_version != expected_versions.get(item.metric_id):
            issues.append(
                _issue(
                    "normalization.version-mismatch",
                    "fault",
                    "normalization",
                    entity_id,
                    "Normalization version does not match the review manifest.",
                )
            )
        if item.observation_status == "missing":
            if item.raw_value is not None or item.normalized_value is not None:
                issues.append(
                    _issue(
                        "normalization.missing-encoded-as-value",
                        "fault",
                        "normalization",
                        entity_id,
                        "A missing observation must remain null, never zero or "
                        "another value.",
                    )
                )
            continue
        if item.raw_value is None:
            issues.append(
                _issue(
                    "normalization.missing-raw-value",
                    "fault",
                    "normalization",
                    entity_id,
                    "Available normalized evidence has no reconstructable raw value.",
                )
            )
        if item.normalized_value is None:
            issues.append(
                _issue(
                    "normalization.missing-normalized-value",
                    "fault",
                    "normalization",
                    entity_id,
                    "Available evidence has no normalized value.",
                )
            )
        if not item.reconstruction_input_refs:
            issues.append(
                _issue(
                    "normalization.missing-reconstruction-inputs",
                    "fault",
                    "normalization",
                    entity_id,
                    "Normalization inputs were not retained for reconstruction.",
                )
            )
        if item.reconstructed_normalized_value is None:
            issues.append(
                _issue(
                    "normalization.reconstruction-unavailable",
                    "fault",
                    "normalization",
                    entity_id,
                    "Independent normalization reconstruction is unavailable.",
                )
            )
        elif (
            item.normalized_value is not None
            and abs(item.normalized_value - item.reconstructed_normalized_value) > 1e-9
        ):
            issues.append(
                _issue(
                    "normalization.reconstruction-mismatch",
                    "fault",
                    "normalization",
                    entity_id,
                    "Stored and reconstructed normalized values differ.",
                )
            )
    return issues


def _all_provenance_issues(
    evidence: ReferenceEcosystemEvidence,
) -> list[ValidationIssue]:
    checks: list[tuple[str, str, ProvenanceEvidence]] = []
    checks.extend(("paper", item.paper_id, item.provenance) for item in evidence.papers)
    checks.extend(
        ("researcher", item.researcher_id, item.provenance)
        for item in evidence.researchers
    )
    checks.extend(
        (
            "authorship",
            f"{item.paper_id}::{item.researcher_id}",
            item.provenance,
        )
        for item in evidence.authorships
    )
    checks.extend(
        ("institution", item.institution_id, item.provenance)
        for item in evidence.institutions
    )
    checks.extend(
        (
            "paper-time-affiliation",
            f"{item.paper_id}::{item.researcher_id}",
            item.provenance,
        )
        for item in evidence.affiliations
    )
    checks.extend(
        (
            "field-attribution",
            f"{item.paper_id}::{item.provider}::{item.field_id or 'missing'}",
            item.provenance,
        )
        for item in evidence.field_attributions
    )
    checks.append(
        (
            "historical-coverage",
            evidence.dataset_version,
            evidence.historical_coverage.provenance,
        )
    )
    checks.extend(
        (
            "normalization",
            f"{item.metric_id}::{item.entity_id}::{item.scope_id}",
            item.provenance,
        )
        for item in evidence.normalizations
    )
    issues: list[ValidationIssue] = []
    for entity_type, entity_id, provenance in checks:
        issues.extend(
            _provenance_issues(
                entity_type,
                entity_id,
                provenance,
                evidence.dataset_version,
            )
        )
    return issues


def _summary(evidence: ReferenceEcosystemEvidence) -> ReferenceEcosystemSummary:
    authorship_keys = {
        (item.paper_id, item.researcher_id) for item in evidence.authorships
    }
    expected_links = {
        (paper.paper_id, researcher_id)
        for paper in evidence.papers
        for researcher_id in paper.expected_researcher_ids
    }
    linked_expected = len(expected_links & authorship_keys)
    affiliation_keys = {
        (item.paper_id, item.researcher_id)
        for item in evidence.affiliations
        if item.resolution_status == "resolved" and item.institution_id is not None
    }
    mapped_papers = {
        item.paper_id
        for item in evidence.field_attributions
        if item.mapping_status == "mapped"
        and item.field_id is not None
        and item.field_weight is not None
    }
    required_years = set(evidence.historical_coverage.required_complete_years)
    observed_years = set(evidence.historical_coverage.observed_complete_years)
    return ReferenceEcosystemSummary(
        paper_count=len(evidence.papers),
        researcher_count=len(evidence.researchers),
        authorship_count=len(evidence.authorships),
        affiliation_assertion_count=len(evidence.affiliations),
        institution_count=len(evidence.institutions),
        resolved_affiliation_count=sum(
            item.resolution_status == "resolved" for item in evidence.affiliations
        ),
        unresolved_affiliation_count=sum(
            item.resolution_status == "unresolved" for item in evidence.affiliations
        ),
        ambiguous_affiliation_count=sum(
            item.resolution_status == "ambiguous" for item in evidence.affiliations
        ),
        paper_author_link_coverage=_coverage(linked_expected, len(expected_links)),
        paper_time_affiliation_coverage=_coverage(
            len(affiliation_keys & authorship_keys), len(authorship_keys)
        ),
        field_attribution_coverage=_coverage(
            len(mapped_papers & {item.paper_id for item in evidence.papers}),
            len(evidence.papers),
        ),
        historical_year_coverage=_coverage(
            len(required_years & observed_years), len(required_years)
        ),
        normalization_record_count=len(evidence.normalizations),
        missing_normalization_count=sum(
            item.observation_status == "missing" for item in evidence.normalizations
        ),
    )


def validate_reference_ecosystem(
    evidence: ReferenceEcosystemEvidence,
) -> ReferenceEcosystemValidationReport:
    """Return deterministic linkage and reconstruction findings, never a score."""
    issues = [
        *_validate_links(evidence),
        *_validate_identity_warnings(evidence),
        *_validate_fields(evidence),
        *_validate_historical_coverage(evidence),
        *_validate_normalizations(evidence),
        *_all_provenance_issues(evidence),
    ]
    issues.sort(
        key=lambda item: (
            item.code,
            item.entity_type,
            item.entity_id,
            item.related_ids,
            item.detail,
        )
    )
    if any(item.severity == "fault" for item in issues):
        status: ValidationStatus = "invalid"
    elif issues:
        status = "review-required"
    else:
        status = "healthy"
    return ReferenceEcosystemValidationReport(
        report_version=REFERENCE_ECOSYSTEM_VALIDATION_VERSION,
        dataset_version=evidence.dataset_version,
        status=status,
        summary=_summary(evidence),
        issues=tuple(issues),
        # Anchor order has no meaning; sorting makes the non-ranking behavior explicit.
        sanity_anchors=tuple(
            sorted(evidence.sanity_anchors, key=lambda item: item.anchor_id)
        ),
    )
