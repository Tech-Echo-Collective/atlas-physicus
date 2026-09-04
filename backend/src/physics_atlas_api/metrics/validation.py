import math
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from .. import models
from ..database import Base
from .contracts import METRIC_CONTRACTS, MetricScientificContract
from .thresholds import METRIC_VALIDATION_THRESHOLDS_V1

ActivationStatus = Literal["withheld", "eligible-for-reviewed-activation"]
MetricScopeKind = Literal["research-field", "science-domain"]

REVIEWED_CLASSIFICATION_METHODS = (
    "manual-review-v1",
    "curated-review-v1",
)

REQUIRED_SANITY_CHECKS: dict[str, tuple[str, ...]] = {
    "research_activity_score": (
        "activity-order-plausibility",
        "outlier-scale-stability",
        "missing-remains-missing",
        "sparse-entities-withheld",
    ),
    "research_impact": (
        "mncs-cohort-reconstruction",
        "pp-top-decile-tie-policy",
        "citation-age-control",
        "citation-coverage-gate",
        "missing-remains-missing",
    ),
    "collaboration": (
        "collaboration-proportion-reconstruction",
        "relationship-resolution-gate",
        "consortium-outlier-review",
        "missing-remains-missing",
    ),
    "research_diversity": (
        "taxonomy-version-consistency",
        "classification-coverage-gate",
        "missing-remains-missing",
    ),
    "momentum": (
        "field-median-relative-change",
        "robust-scale-reconstruction",
        "complete-window-gate",
        "small-denominator-gate",
        "missing-remains-missing",
    ),
}


@dataclass(frozen=True)
class MetricSanityCheck:
    check_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class MetricValidationSummary:
    """Bounded evidence counts; no field in this object is a metric score."""

    dataset_version: str | None
    dataset_kind: str | None
    acquisition_scope: str | None
    terminal_year: int | None
    update_sequence: int
    source_snapshot_count: int
    source_snapshot_sources: tuple[str, ...]
    complete_source_years: tuple[int, ...]
    raw_record_count: int
    raw_paper_record_count: int
    raw_researcher_record_count: int
    canonical_paper_count: int
    canonical_researcher_count: int
    canonical_institution_count: int
    publication_years: tuple[int, ...]
    mature_paper_count: int
    paper_field_link_count: int
    classified_paper_count: int
    reviewed_classified_paper_count: int
    minimum_field_age_cohort_size: int
    authorship_count: int
    authored_paper_count: int
    affiliation_count: int
    paper_time_affiliation_count: int
    paper_time_affiliation_coverage: float | None
    collaboration_relationship_coverage: float | None
    countries_with_institutions: int
    paper_time_affiliation_attribution_certified: bool
    citation_edge_count: int
    citation_age_control_certified: bool
    common_citation_cutoff_certified: bool
    non_self_citation_rule_certified: bool
    reviewed_taxonomy_version: str | None
    identity_resolution_count: int
    matched_resolution_count: int
    unresolved_resolution_count: int
    ambiguous_resolution_count: int
    needs_review_count: int
    matched_paper_evidence_examined: int
    matched_papers_with_citation_observation: int | None
    raw_affiliation_assertion_count: int | None
    evidence_truncated: bool
    metric_observation_count: int

    @property
    def citation_observation_coverage(self) -> float | None:
        if (
            self.evidence_truncated
            or self.matched_papers_with_citation_observation is None
            or self.matched_paper_evidence_examined == 0
        ):
            return None
        return (
            self.matched_papers_with_citation_observation
            / self.matched_paper_evidence_examined
        )

    def has_complete_window(self, years: int) -> bool:
        if self.terminal_year is None or years <= 0:
            return False
        required = set(range(self.terminal_year - years + 1, self.terminal_year + 1))
        return required.issubset(self.complete_source_years)


@dataclass(frozen=True)
class MetricPartitionReadiness:
    """Reviewed evidence for one exact visualization partition.

    A corpus summary cannot establish these facts. The dataset and update keys
    bind a reviewed partition to the immutable input lineage that was actually
    checked; the booleans are outputs of the partition-level validation work,
    not assumptions derived from corpus totals.
    """

    metric_id: str
    metric_version: str
    entity_type: str
    scope_kind: MetricScopeKind
    scope_id: str
    period: str
    dataset_version: str
    acquisition_scope: str
    update_sequence: int
    input_lineage_complete: bool
    per_entity_minimums_passed: bool
    cohort_requirements_passed: bool
    missing_data_checks_passed: bool

    def __post_init__(self) -> None:
        for field_name in (
            "metric_id",
            "metric_version",
            "entity_type",
            "scope_id",
            "period",
            "dataset_version",
            "acquisition_scope",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.update_sequence < 0:
            raise ValueError("update_sequence must be nonnegative")


@dataclass(frozen=True)
class MetricActivationDecision:
    metric_id: str
    metric_version: str
    status: ActivationStatus
    reasons: tuple[str, ...]
    required_sanity_checks: tuple[str, ...]
    passed_sanity_checks: tuple[str, ...]

    @property
    def may_activate(self) -> bool:
        return self.status == "eligible-for-reviewed-activation"


@dataclass(frozen=True)
class MetricValidationReport:
    report_version: str
    summary: MetricValidationSummary
    decisions: tuple[MetricActivationDecision, ...]


def _count(session: Session, model: type[Base]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _raw_evidence_counts(
    session: Session, max_evidence_records: int
) -> tuple[int, int | None, int | None, bool]:
    """Summarize bounded raw evidence without double-counting canonical papers.

    A canonical paper has a citation observation when at least one matched raw
    provider record contains a finite, nonnegative ``citation_count``. Multiple
    provider records for the same canonical paper do not increase either the
    coverage numerator or denominator. This is only an observation-presence
    check; conflicting values and citation-cutoff comparability remain separate
    scientific gates.
    """
    statement = (
        select(
            models.IdentityResolution.canonical_entity_id,
            models.RawEntityRecord.id,
            models.RawEntityRecord.attributes_json,
        )
        .select_from(models.RawEntityRecord)
        .join(
            models.IdentityResolution,
            models.IdentityResolution.raw_entity_record_id == models.RawEntityRecord.id,
        )
        .where(
            models.RawEntityRecord.entity_type == "paper",
            models.IdentityResolution.entity_type == "paper",
            models.IdentityResolution.status == "matched",
            models.IdentityResolution.canonical_entity_id.is_not(None),
        )
        .order_by(
            models.IdentityResolution.canonical_entity_id,
            models.RawEntityRecord.id,
        )
        .limit(max_evidence_records + 1)
    )
    rows = list(session.execute(statement))
    if len(rows) > max_evidence_records:
        canonical_ids = {
            str(canonical_entity_id)
            for canonical_entity_id, _, _ in rows[:max_evidence_records]
        }
        return len(canonical_ids), None, None, True

    citation_observed_by_paper: dict[str, bool] = {}
    affiliation_assertions = 0
    seen_evidence_records: set[tuple[str, str]] = set()
    for canonical_entity_id, raw_record_id, attributes in rows:
        canonical_id = str(canonical_entity_id)
        citation_observed_by_paper.setdefault(canonical_id, False)
        evidence_key = (canonical_id, raw_record_id)
        if evidence_key in seen_evidence_records:
            continue
        seen_evidence_records.add(evidence_key)
        citation_count = attributes.get("citation_count")
        if (
            isinstance(citation_count, (int, float))
            and not isinstance(citation_count, bool)
            and math.isfinite(float(citation_count))
            and citation_count >= 0
        ):
            citation_observed_by_paper[canonical_id] = True
        authors = attributes.get("authors")
        if not isinstance(authors, list):
            continue
        for author in authors:
            if not isinstance(author, dict):
                continue
            affiliations = author.get("affiliations")
            if isinstance(affiliations, list):
                affiliation_assertions += len(affiliations)
    return (
        len(citation_observed_by_paper),
        sum(citation_observed_by_paper.values()),
        affiliation_assertions,
        False,
    )


def _paper_time_affiliation_measurement(
    session: Session,
) -> tuple[int, float | None]:
    """Measure allocated current attribution mass without certifying its review."""
    count, allocated_mass = session.execute(
        select(
            func.count(),
            func.sum(
                case(
                    (
                        (
                            models.PaperAffiliation.affiliation_resolution_status
                            == "resolved"
                        )
                        & models.PaperAffiliation.institution_id.is_not(None),
                        models.PaperAffiliation.attribution_weight,
                    ),
                    else_=0,
                )
            ),
        )
        .select_from(models.PaperAffiliation)
        .where(models.PaperAffiliation.is_current)
    ).one()
    canonical_paper_count = _count(session, models.Paper)
    if canonical_paper_count == 0:
        return int(count), None
    return int(count), float(allocated_mass or 0) / canonical_paper_count


def build_metric_validation_summary(
    session: Session,
    *,
    terminal_year: int | None = None,
    max_evidence_records: int = 10_000,
) -> MetricValidationSummary:
    """Read a bounded database evidence summary without creating observations."""
    if max_evidence_records < 1:
        raise ValueError("max_evidence_records must be positive")

    with session.no_autoflush:
        dataset = session.get(models.DatasetState, "current")
        publication_years = tuple(
            session.scalars(
                select(models.Paper.publication_year)
                .distinct()
                .order_by(models.Paper.publication_year)
            )
        )
        selected_terminal_year = terminal_year
        if selected_terminal_year is None and publication_years:
            selected_terminal_year = publication_years[-1]

        mature_cutoff = (
            selected_terminal_year - 2 if selected_terminal_year is not None else None
        )
        mature_paper_count = (
            session.scalar(
                select(func.count())
                .select_from(models.Paper)
                .where(models.Paper.publication_year <= mature_cutoff)
            )
            if mature_cutoff is not None
            else 0
        ) or 0

        field_age_cohorts = tuple(
            session.scalars(
                select(func.count(distinct(models.PaperField.paper_id)))
                .join(
                    models.Paper,
                    models.Paper.id == models.PaperField.paper_id,
                )
                .group_by(
                    models.PaperField.field_id,
                    models.Paper.publication_year,
                )
            )
        )
        minimum_field_age_cohort_size = min(field_age_cohorts, default=0)

        identity_counts = {
            status: count
            for status, count in session.execute(
                select(models.IdentityResolution.status, func.count())
                .group_by(models.IdentityResolution.status)
                .order_by(models.IdentityResolution.status)
            )
        }
        snapshot_ids = tuple(dataset.source_snapshot_ids) if dataset else ()
        source_snapshot_count = (
            session.scalar(
                select(func.count())
                .select_from(models.SourceSnapshot)
                .where(models.SourceSnapshot.id.in_(snapshot_ids))
            )
            if snapshot_ids
            else 0
        ) or 0
        snapshot_sources = (
            tuple(
                session.scalars(
                    select(models.SourceSnapshot.source)
                    .where(models.SourceSnapshot.id.in_(snapshot_ids))
                    .distinct()
                    .order_by(models.SourceSnapshot.source)
                )
            )
            if snapshot_ids
            else ()
        )
        raw_examined, citation_observed, raw_affiliations, truncated = (
            _raw_evidence_counts(session, max_evidence_records)
        )
        paper_affiliation_count, paper_time_affiliation_coverage = (
            _paper_time_affiliation_measurement(session)
        )
        provenance = dataset.provenance_json if dataset else {}

        return MetricValidationSummary(
            dataset_version=(
                str(provenance["version"])
                if provenance.get("version") is not None
                else None
            ),
            dataset_kind=dataset.dataset_kind if dataset else None,
            acquisition_scope=(
                str(provenance["acquisitionScope"])
                if provenance.get("acquisitionScope") is not None
                else None
            ),
            terminal_year=selected_terminal_year,
            update_sequence=dataset.update_sequence if dataset else 0,
            source_snapshot_count=source_snapshot_count,
            source_snapshot_sources=snapshot_sources,
            # The current persistence model does not certify complete acquisition by
            # publication year. Observed years must not be promoted to complete years.
            complete_source_years=(),
            raw_record_count=_count(session, models.RawEntityRecord),
            raw_paper_record_count=session.scalar(
                select(func.count())
                .select_from(models.RawEntityRecord)
                .where(models.RawEntityRecord.entity_type == "paper")
            )
            or 0,
            raw_researcher_record_count=session.scalar(
                select(func.count())
                .select_from(models.RawEntityRecord)
                .where(models.RawEntityRecord.entity_type == "researcher")
            )
            or 0,
            canonical_paper_count=_count(session, models.Paper),
            canonical_researcher_count=_count(session, models.Researcher),
            canonical_institution_count=_count(session, models.Institution),
            publication_years=publication_years,
            mature_paper_count=mature_paper_count,
            paper_field_link_count=_count(session, models.PaperField),
            classified_paper_count=session.scalar(
                select(func.count(distinct(models.PaperField.paper_id)))
            )
            or 0,
            reviewed_classified_paper_count=session.scalar(
                select(func.count(distinct(models.PaperField.paper_id))).where(
                    models.PaperField.classification_method.in_(
                        REVIEWED_CLASSIFICATION_METHODS
                    )
                )
            )
            or 0,
            minimum_field_age_cohort_size=minimum_field_age_cohort_size,
            authorship_count=_count(session, models.Authorship),
            authored_paper_count=session.scalar(
                select(func.count(distinct(models.Authorship.paper_id)))
            )
            or 0,
            affiliation_count=_count(session, models.Affiliation),
            paper_time_affiliation_count=paper_affiliation_count,
            paper_time_affiliation_coverage=paper_time_affiliation_coverage,
            # Collaboration-indicator coverage needs its own reviewed evidence.
            # Authored-paper presence is not a valid substitute.
            collaboration_relationship_coverage=None,
            countries_with_institutions=session.scalar(
                select(func.count(distinct(models.Institution.country_id)))
            )
            or 0,
            # Materialized allocation coverage is measured above, but review is a
            # separate scientific gate and is never inferred from row presence.
            paper_time_affiliation_attribution_certified=False,
            citation_edge_count=_count(session, models.Citation),
            # Publication month/cutoff, non-self derivation, and reviewed taxonomy
            # versions are not persisted as certifiable live inputs yet.
            citation_age_control_certified=False,
            common_citation_cutoff_certified=False,
            non_self_citation_rule_certified=False,
            reviewed_taxonomy_version=None,
            identity_resolution_count=_count(session, models.IdentityResolution),
            matched_resolution_count=identity_counts.get("matched", 0),
            unresolved_resolution_count=identity_counts.get("unresolved", 0),
            ambiguous_resolution_count=identity_counts.get("ambiguous", 0),
            needs_review_count=session.scalar(
                select(func.count())
                .select_from(models.IdentityReview)
                .where(models.IdentityReview.status == "needs_review")
            )
            or 0,
            matched_paper_evidence_examined=raw_examined,
            matched_papers_with_citation_observation=citation_observed,
            raw_affiliation_assertion_count=raw_affiliations,
            evidence_truncated=truncated,
            metric_observation_count=_count(session, models.MetricObservation),
        )


def _data_gate_reasons(
    contract: MetricScientificContract,
    summary: MetricValidationSummary,
    *,
    expected_acquisition_scope: str | None = None,
) -> list[str]:
    reasons: list[str] = []
    expected_scope = (
        contract.provenance.source_scope
        if expected_acquisition_scope is None
        else expected_acquisition_scope
    )
    if summary.dataset_version is None:
        reasons.append("input dataset version is missing")
    if summary.acquisition_scope != expected_scope:
        reasons.append(
            "acquisition scope does not match the versioned candidate contract"
        )

    thresholds = METRIC_VALIDATION_THRESHOLDS_V1
    if contract.metric_id == "research_activity_score":
        if not summary.has_complete_window(3):
            reasons.append("three complete source years are not certified")
        if (
            summary.canonical_paper_count
            < thresholds.activity.minimum_fractional_papers
        ):
            reasons.append("fewer than ten paper-equivalents are available")
        if (
            summary.canonical_researcher_count
            < thresholds.activity.minimum_distinct_researchers
        ):
            reasons.append("fewer than five identifiable researchers are available")
        if (
            summary.canonical_institution_count
            < thresholds.activity.minimum_normalization_cohort
        ):
            reasons.append("the institution normalization cohort is too small")
        if (
            summary.paper_time_affiliation_count == 0
            or summary.paper_time_affiliation_coverage is None
            or summary.paper_time_affiliation_coverage
            < thresholds.coverage.paper_time_affiliation
            or not summary.paper_time_affiliation_attribution_certified
        ):
            reasons.append("reviewed paper-time affiliation attribution is unavailable")
        if (
            summary.countries_with_institutions
            < thresholds.activity.minimum_normalization_cohort
        ):
            reasons.append("the country normalization cohort is too small")
    elif contract.metric_id == "research_impact":
        if summary.mature_paper_count < thresholds.impact.minimum_eligible_papers:
            reasons.append("fewer than ten citation-mature papers are available")
        if summary.citation_edge_count == 0:
            reasons.append("canonical non-self citation observations are unavailable")
        if not summary.citation_age_control_certified:
            reasons.append("24-month citation-age control is not certified")
        if not summary.common_citation_cutoff_certified:
            reasons.append("a common citation observation cutoff is not certified")
        if not summary.non_self_citation_rule_certified:
            reasons.append("the non-self citation rule is not certified")
        coverage = summary.citation_observation_coverage
        if coverage is None or coverage < thresholds.coverage.citation:
            reasons.append("citation-observation coverage is below 90 percent")
        if (
            summary.minimum_field_age_cohort_size
            < thresholds.impact.minimum_reference_cohort
        ):
            reasons.append("a field-age cohort is below the v1 minimum")
        if (
            summary.paper_time_affiliation_count == 0
            or summary.paper_time_affiliation_coverage is None
            or summary.paper_time_affiliation_coverage
            < thresholds.coverage.paper_time_affiliation
            or not summary.paper_time_affiliation_attribution_certified
        ):
            reasons.append("reviewed paper-time affiliation attribution is unavailable")
    elif contract.metric_id == "collaboration":
        if not summary.has_complete_window(3):
            reasons.append("three complete source years are not certified")
        relationship_coverage = summary.collaboration_relationship_coverage
        if (
            relationship_coverage is None
            or relationship_coverage
            < thresholds.connectivity.minimum_relationship_coverage
        ):
            reasons.append("resolved authorship coverage is below 90 percent")
        if (
            summary.canonical_paper_count
            < thresholds.connectivity.minimum_fractional_papers
        ):
            reasons.append("fewer than ten paper-equivalents are available")
        if (
            summary.canonical_researcher_count
            < thresholds.connectivity.minimum_identifiable_researchers
        ):
            reasons.append("fewer than five identifiable researchers are available")
        if (
            summary.paper_time_affiliation_count == 0
            or summary.paper_time_affiliation_coverage is None
            or summary.paper_time_affiliation_coverage
            < thresholds.coverage.paper_time_affiliation
            or not summary.paper_time_affiliation_attribution_certified
        ):
            reasons.append(
                "institution and country collaboration edges are unavailable"
            )
    elif contract.metric_id == "research_diversity":
        if not summary.has_complete_window(3):
            reasons.append("three complete source years are not certified")
        if (
            summary.reviewed_classified_paper_count
            < thresholds.diversity.minimum_fractional_papers
        ):
            reasons.append("fewer than fifteen papers have reviewed classifications")
        if summary.reviewed_taxonomy_version is None:
            reasons.append("a reviewed taxonomy version is unavailable")
        if summary.canonical_paper_count == 0 or (
            summary.reviewed_classified_paper_count / summary.canonical_paper_count
            < thresholds.coverage.field_attribution
        ):
            reasons.append("reviewed classification coverage is below 90 percent")
        if summary.acquisition_scope == "hep-th-v1":
            reasons.append(
                "the hep-th-conditioned corpus is not a reviewed broad-field taxonomy"
            )
        if (
            summary.paper_time_affiliation_count == 0
            or summary.paper_time_affiliation_coverage is None
            or summary.paper_time_affiliation_coverage
            < thresholds.coverage.paper_time_affiliation
            or not summary.paper_time_affiliation_attribution_certified
        ):
            reasons.append("reviewed paper-time affiliation attribution is unavailable")
    elif contract.metric_id == "momentum":
        if not summary.has_complete_window(6):
            reasons.append("six complete source years are not certified")
        if (
            summary.canonical_paper_count
            < 2 * thresholds.momentum.minimum_fractional_papers_per_window
        ):
            reasons.append("fewer than ten papers exist in each Momentum window")
        if (
            summary.paper_time_affiliation_count == 0
            or summary.paper_time_affiliation_coverage is None
            or summary.paper_time_affiliation_coverage
            < thresholds.coverage.paper_time_affiliation
            or not summary.paper_time_affiliation_attribution_certified
        ):
            reasons.append("stable paper-time affiliation attribution is unavailable")
    return reasons


def _partition_gate_reasons(
    contract: MetricScientificContract,
    summary: MetricValidationSummary,
    readiness: MetricPartitionReadiness | None,
    *,
    expected_acquisition_scope: str | None = None,
) -> list[str]:
    """Require reviewed evidence for the exact output partition and lineage."""
    if readiness is None:
        return ["exact partition and input-lineage readiness are not certified"]

    reasons: list[str] = []
    if readiness.metric_id != contract.metric_id:
        reasons.append("partition metric identifier does not match the contract")
    if readiness.metric_version != contract.version:
        reasons.append("partition metric version does not match the contract")
    if readiness.entity_type not in contract.aggregation_levels:
        reasons.append("partition entity type is not supported by the contract")
    if readiness.dataset_version != summary.dataset_version:
        reasons.append("partition input dataset version does not match the summary")
    if readiness.acquisition_scope != summary.acquisition_scope:
        reasons.append("partition acquisition scope does not match the summary")
    expected_scope = (
        contract.provenance.source_scope
        if expected_acquisition_scope is None
        else expected_acquisition_scope
    )
    if readiness.acquisition_scope != expected_scope:
        reasons.append("partition acquisition scope does not match the contract")
    if readiness.update_sequence != summary.update_sequence:
        reasons.append("partition input update sequence does not match the summary")
    if not readiness.input_lineage_complete:
        reasons.append("partition input lineage is incomplete")
    if not readiness.per_entity_minimums_passed:
        reasons.append("partition per-entity minimums have not passed")
    if not readiness.cohort_requirements_passed:
        reasons.append("partition cohort requirements have not passed")
    if not readiness.missing_data_checks_passed:
        reasons.append("partition missing-data checks have not passed")
    return reasons


def assess_metric_activation(
    contract: MetricScientificContract,
    summary: MetricValidationSummary,
    sanity_checks: tuple[MetricSanityCheck, ...] = (),
    partition_readiness: MetricPartitionReadiness | None = None,
    *,
    expected_acquisition_scope: str | None = None,
) -> MetricActivationDecision:
    """Apply the evidence and sanity gates; this never publishes a definition.

    The optional scope override is for a bounded, non-publishing validation
    corpus using the exact contract versions. Public observation and release
    checks remain bound to the registered contract and live dataset scopes.
    """
    reasons = _data_gate_reasons(
        contract,
        summary,
        expected_acquisition_scope=expected_acquisition_scope,
    )
    reasons.extend(
        _partition_gate_reasons(
            contract,
            summary,
            partition_readiness,
            expected_acquisition_scope=expected_acquisition_scope,
        )
    )
    if contract.implementation_status != "validated":
        reasons.append("scientific contract remains experimental-candidate")

    checks_by_id = {check.check_id: check for check in sanity_checks}
    required_checks = REQUIRED_SANITY_CHECKS[contract.metric_id]
    passed_checks: list[str] = []
    for check_id in required_checks:
        check = checks_by_id.get(check_id)
        if check is None:
            reasons.append(f"required sanity check has not run: {check_id}")
        elif not check.passed:
            reasons.append(f"sanity check failed: {check_id}")
        else:
            passed_checks.append(check_id)

    return MetricActivationDecision(
        metric_id=contract.metric_id,
        metric_version=contract.version,
        status="withheld" if reasons else "eligible-for-reviewed-activation",
        reasons=tuple(reasons),
        required_sanity_checks=required_checks,
        passed_sanity_checks=tuple(passed_checks),
    )


def build_metric_validation_report(
    session: Session,
    *,
    terminal_year: int | None = None,
    max_evidence_records: int = 10_000,
    sanity_checks: dict[str, tuple[MetricSanityCheck, ...]] | None = None,
) -> MetricValidationReport:
    """Build a deterministic non-publishing report for all candidate metrics."""
    summary = build_metric_validation_summary(
        session,
        terminal_year=terminal_year,
        max_evidence_records=max_evidence_records,
    )
    checks = sanity_checks or {}
    decisions = tuple(
        assess_metric_activation(contract, summary, checks.get(metric_id, ()))
        for metric_id, contract in METRIC_CONTRACTS.items()
    )
    return MetricValidationReport(
        report_version="metric-validation-report-v1",
        summary=summary,
        decisions=decisions,
    )
