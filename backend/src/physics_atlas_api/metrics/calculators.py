import hashlib
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Literal

from .contracts import get_metric_contract
from .normalization import (
    log_midrank_percentiles,
    normalized_shannon_evenness,
    robust_centered_change_cohort,
    robust_log_winsorized_cohort,
    robust_mncs_cohort,
)
from .thresholds import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    MetricValidationThresholds,
)

MetricEntityType = Literal["researcher", "institution", "country"]
MetricMetadataValue = str | int | float | bool | None


@dataclass(frozen=True)
class MetricCoverageEvidence:
    """Coverage ratios for one exact entity/field/window partition."""

    paper_time_affiliation: float | None
    canonical_institution: float | None
    citation: float | None
    field_attribution: float | None
    collaboration_relationship: float | None = None

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} coverage must be between zero and one")


@dataclass(frozen=True)
class AttributedPaperEvidence:
    """One canonical paper's materialized share for an entity/field partition.

    ``attribution_weight`` already combines the conserved paper-time entity
    share and the versioned field share. Unresolved mass must not be
    redistributed into this value.
    """

    paper_id: str
    publication_date: date
    document_type: str
    attribution_weight: float
    researcher_ids: tuple[str, ...]
    citation_count: float | None = None
    citation_observed_at: date | None = None
    collaborative: bool | None = None
    cross_institution: bool | None = None
    international: bool | None = None
    partner_entity_ids: tuple[str, ...] = ()
    category_weights: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.paper_id.strip() or not self.document_type.strip():
            raise ValueError("paper id and document type must be non-empty")
        if not math.isfinite(self.attribution_weight) or not (
            0 <= self.attribution_weight <= 1
        ):
            raise ValueError("paper attribution weight must be finite and within [0,1]")
        if self.citation_count is not None and (
            not math.isfinite(self.citation_count) or self.citation_count < 0
        ):
            raise ValueError("citation count must be finite and nonnegative")
        categories = dict(self.category_weights)
        if len(categories) != len(self.category_weights):
            raise ValueError("paper category ids must be unique")
        if categories:
            if any(
                not math.isfinite(value) or value < 0 for value in categories.values()
            ):
                raise ValueError(
                    "paper category weights must be finite and nonnegative"
                )
            if not math.isclose(
                math.fsum(categories.values()), 1.0, rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError("classified paper category weights must total one")


@dataclass(frozen=True)
class MetricPartitionInput:
    entity_type: MetricEntityType
    entity_id: str
    field_id: str
    terminal_year: int
    as_of_date: date
    dataset_version: str
    acquisition_scope: str
    attribution_policy_version: str
    ontology_version: str
    mapping_policy_version: str
    citation_policy_version: str
    coverage: MetricCoverageEvidence
    complete_source_years: tuple[int, ...]
    papers: tuple[AttributedPaperEvidence, ...]
    eligible_category_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value in (
            self.entity_id,
            self.field_id,
            self.dataset_version,
            self.acquisition_scope,
            self.attribution_policy_version,
            self.ontology_version,
            self.mapping_policy_version,
            self.citation_policy_version,
        ):
            if not value.strip():
                raise ValueError("metric partition identifiers must be non-empty")
        paper_ids = [paper.paper_id for paper in self.papers]
        if len(set(paper_ids)) != len(paper_ids):
            raise ValueError("an entity/field partition may contain each paper once")
        if len(set(self.eligible_category_ids)) != len(self.eligible_category_ids):
            raise ValueError("eligible category ids must be unique")


@dataclass(frozen=True)
class CitationReferenceCohort:
    field_id: str
    publication_year: int
    document_type: str
    observed_at: date
    citations: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not self.field_id.strip() or not self.document_type.strip():
            raise ValueError("citation cohort identifiers must be non-empty")
        citation_map = dict(self.citations)
        if len(citation_map) != len(self.citations):
            raise ValueError("citation cohort paper ids must be unique")
        if any(
            not math.isfinite(value) or value < 0 for value in citation_map.values()
        ):
            raise ValueError("citation cohort values must be finite and nonnegative")

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.field_id, self.publication_year, self.document_type)


@dataclass(frozen=True)
class MetricCalculationResult:
    metric_id: str
    metric_definition_version: str
    algorithm_version: str
    normalization_version: str
    entity_type: MetricEntityType
    entity_id: str
    field_id: str
    period: str
    raw_value: float | None
    raw_unit: str
    normalized_value: float | None
    components: Mapping[str, MetricMetadataValue]
    normalization_parameters: Mapping[str, MetricMetadataValue]
    input_count: int
    input_manifest_digest: str
    threshold_version: str
    dataset_version: str
    acquisition_scope: str
    attribution_policy_version: str
    ontology_version: str
    mapping_policy_version: str
    citation_policy_version: str
    missing_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def raw_eligible(self) -> bool:
        return self.raw_value is not None and not self.missing_reasons

    @property
    def eligible_for_observation(self) -> bool:
        return self.raw_eligible and self.normalized_value is not None


def _contract_versions(metric_id: str) -> tuple[str, str, str, str]:
    contract = get_metric_contract(metric_id)
    if contract is None:
        raise ValueError(f"unknown metric contract: {metric_id}")
    return (
        contract.version,
        contract.algorithm_version,
        contract.normalization_version,
        contract.raw_unit,
    )


def _manifest_digest(partition: MetricPartitionInput, metric_id: str) -> str:
    payload = {
        "metric_id": metric_id,
        "entity_type": partition.entity_type,
        "entity_id": partition.entity_id,
        "field_id": partition.field_id,
        "terminal_year": partition.terminal_year,
        "as_of_date": partition.as_of_date.isoformat(),
        "dataset_version": partition.dataset_version,
        "acquisition_scope": partition.acquisition_scope,
        "attribution_policy_version": partition.attribution_policy_version,
        "ontology_version": partition.ontology_version,
        "mapping_policy_version": partition.mapping_policy_version,
        "citation_policy_version": partition.citation_policy_version,
        "coverage": asdict(partition.coverage),
        "complete_source_years": partition.complete_source_years,
        "eligible_category_ids": partition.eligible_category_ids,
        "papers": [
            {
                **asdict(paper),
                "publication_date": paper.publication_date.isoformat(),
                "citation_observed_at": (
                    paper.citation_observed_at.isoformat()
                    if paper.citation_observed_at
                    else None
                ),
            }
            for paper in sorted(partition.papers, key=lambda item: item.paper_id)
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coverage_components(
    coverage: MetricCoverageEvidence,
) -> dict[str, MetricMetadataValue]:
    return {
        "paper_time_affiliation_coverage": coverage.paper_time_affiliation,
        "canonical_institution_coverage": coverage.canonical_institution,
        "citation_coverage": coverage.citation,
        "field_attribution_coverage": coverage.field_attribution,
        "collaboration_relationship_coverage": coverage.collaboration_relationship,
    }


def _base_coverage_reasons(
    partition: MetricPartitionInput,
    thresholds: MetricValidationThresholds,
    *,
    require_geographic_attribution: bool,
) -> list[str]:
    reasons: list[str] = []
    if (
        partition.coverage.field_attribution is None
        or partition.coverage.field_attribution < thresholds.coverage.field_attribution
    ):
        reasons.append("field attribution coverage is below the v1 threshold")
    if require_geographic_attribution:
        if (
            partition.coverage.paper_time_affiliation is None
            or partition.coverage.paper_time_affiliation
            < thresholds.coverage.paper_time_affiliation
        ):
            reasons.append("paper-time affiliation coverage is below the v1 threshold")
        if (
            partition.coverage.canonical_institution is None
            or partition.coverage.canonical_institution
            < thresholds.coverage.canonical_institution
        ):
            reasons.append("canonical institution coverage is below the v1 threshold")
    return reasons


def _years(partition: MetricPartitionInput, count: int) -> set[int]:
    return set(range(partition.terminal_year - count + 1, partition.terminal_year + 1))


def _window_papers(
    partition: MetricPartitionInput, count: int
) -> tuple[AttributedPaperEvidence, ...]:
    years = _years(partition, count)
    return tuple(
        paper for paper in partition.papers if paper.publication_date.year in years
    )


def _complete_window_reason(partition: MetricPartitionInput, count: int) -> str | None:
    if not _years(partition, count).issubset(partition.complete_source_years):
        return f"{count} complete source years are not certified"
    return None


def _result(
    partition: MetricPartitionInput,
    metric_id: str,
    *,
    raw_value: float | None,
    normalized_value: float | None,
    components: Mapping[str, MetricMetadataValue],
    parameters: Mapping[str, MetricMetadataValue],
    input_count: int,
    thresholds: MetricValidationThresholds,
    missing_reasons: Sequence[str] = (),
) -> MetricCalculationResult:
    definition_version, algorithm_version, normalization_version, raw_unit = (
        _contract_versions(metric_id)
    )
    return MetricCalculationResult(
        metric_id=metric_id,
        metric_definition_version=definition_version,
        algorithm_version=algorithm_version,
        normalization_version=normalization_version,
        entity_type=partition.entity_type,
        entity_id=partition.entity_id,
        field_id=partition.field_id,
        period=str(partition.terminal_year),
        raw_value=raw_value,
        raw_unit=raw_unit,
        normalized_value=normalized_value,
        components={**_coverage_components(partition.coverage), **components},
        normalization_parameters=parameters,
        input_count=input_count,
        input_manifest_digest=_manifest_digest(partition, metric_id),
        threshold_version=thresholds.version,
        dataset_version=partition.dataset_version,
        acquisition_scope=partition.acquisition_scope,
        attribution_policy_version=partition.attribution_policy_version,
        ontology_version=partition.ontology_version,
        mapping_policy_version=partition.mapping_policy_version,
        citation_policy_version=partition.citation_policy_version,
        missing_reasons=tuple(dict.fromkeys(missing_reasons)),
    )


def calculate_activity_raw(
    partition: MetricPartitionInput,
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> MetricCalculationResult:
    papers = _window_papers(partition, 3)
    fractional_papers = math.fsum(paper.attribution_weight for paper in papers)
    researchers = {item for paper in papers for item in paper.researcher_ids}
    reasons = _base_coverage_reasons(
        partition,
        thresholds,
        require_geographic_attribution=partition.entity_type
        in {"institution", "country"},
    )
    if reason := _complete_window_reason(partition, 3):
        reasons.append(reason)
    if fractional_papers < thresholds.activity.minimum_fractional_papers:
        reasons.append("fractional paper output is below the Activity v1 minimum")
    if len(researchers) < thresholds.activity.minimum_distinct_researchers:
        reasons.append("distinct researcher count is below the Activity v1 minimum")
    return _result(
        partition,
        "research_activity_score",
        raw_value=None if reasons else fractional_papers,
        normalized_value=None,
        components={
            "fractional_papers": fractional_papers,
            "distinct_papers": len(papers),
            "distinct_researchers": len(researchers),
            "window_start_year": partition.terminal_year - 2,
            "window_end_year": partition.terminal_year,
        },
        parameters={},
        input_count=len(papers),
        thresholds=thresholds,
        missing_reasons=reasons,
    )


def _normalization_cohorts(
    results: Sequence[MetricCalculationResult], metric_id: str
) -> dict[tuple[str, ...], list[tuple[int, MetricCalculationResult]]]:
    cohorts: dict[tuple[str, ...], list[tuple[int, MetricCalculationResult]]] = (
        defaultdict(list)
    )
    for index, result in enumerate(results):
        if result.metric_id != metric_id:
            raise ValueError(f"normalization input must use metric {metric_id}")
        key = (
            result.entity_type,
            result.field_id,
            result.period,
            result.metric_definition_version,
            result.algorithm_version,
            result.dataset_version,
            result.acquisition_scope,
            result.attribution_policy_version,
            result.ontology_version,
            result.mapping_policy_version,
            result.citation_policy_version,
            result.threshold_version,
        )
        cohorts[key].append((index, result))
    for cohort in cohorts.values():
        entity_ids = [result.entity_id for _, result in cohort]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("a normalization cohort may contain each entity once")
    return cohorts


def normalize_activity_results(
    results: Sequence[MetricCalculationResult],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> tuple[MetricCalculationResult, ...]:
    output = list(results)
    for cohort in _normalization_cohorts(results, "research_activity_score").values():
        raw = {
            result.entity_id: result.raw_value
            for _, result in cohort
            if result.raw_value is not None and not result.missing_reasons
        }
        normalized = robust_log_winsorized_cohort(
            raw, minimum_cohort=thresholds.activity.minimum_normalization_cohort
        )
        for index, result in cohort:
            output[index] = replace(
                result,
                normalized_value=normalized.scores.get(result.entity_id),
                normalization_parameters={
                    **normalized.parameters,
                    "field_id": result.field_id,
                    "terminal_year": int(result.period),
                    "threshold_version": thresholds.version,
                },
                missing_reasons=(
                    result.missing_reasons
                    if result.raw_value is None or normalized.eligible
                    else (
                        *result.missing_reasons,
                        normalized.reason or "normalization failed",
                    )
                ),
            )
    return tuple(output)


def _months_elapsed(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - (1 if end.day < start.day else 0)


def calculate_impact_raw(
    partition: MetricPartitionInput,
    citation_cohorts: Sequence[CitationReferenceCohort],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> MetricCalculationResult:
    papers = _window_papers(partition, 3)
    reasons = _base_coverage_reasons(
        partition,
        thresholds,
        require_geographic_attribution=partition.entity_type
        in {"institution", "country"},
    )
    if reason := _complete_window_reason(partition, 3):
        reasons.append(reason)
    cohort_by_key = {cohort.key: cohort for cohort in citation_cohorts}
    if len(cohort_by_key) != len(citation_cohorts):
        raise ValueError("citation reference cohort keys must be unique")

    total_weight = math.fsum(paper.attribution_weight for paper in papers)
    observed_weight = math.fsum(
        paper.attribution_weight for paper in papers if paper.citation_count is not None
    )
    calculated_coverage = observed_weight / total_weight if total_weight > 0 else None
    effective_coverage_values = [
        value
        for value in (calculated_coverage, partition.coverage.citation)
        if value is not None
    ]
    effective_coverage = min(effective_coverage_values, default=None)
    if effective_coverage is None or effective_coverage < thresholds.coverage.citation:
        reasons.append("citation coverage is below the Impact v1 threshold")

    weighted_ncs: list[tuple[float, float]] = []
    weighted_top_decile: list[tuple[float, float]] = []
    ineligible_maturity = 0
    unavailable_cohort = 0
    for paper in papers:
        if paper.citation_count is None or paper.citation_observed_at is None:
            continue
        if paper.citation_observed_at != partition.as_of_date:
            unavailable_cohort += 1
            continue
        if (
            _months_elapsed(paper.publication_date, partition.as_of_date)
            < thresholds.impact.citation_maturity_months
        ):
            ineligible_maturity += 1
            continue
        cohort = cohort_by_key.get(
            (partition.field_id, paper.publication_date.year, paper.document_type)
        )
        if (
            cohort is None
            or cohort.observed_at != partition.as_of_date
            or len(cohort.citations) < thresholds.impact.minimum_reference_cohort
        ):
            unavailable_cohort += 1
            continue
        citation_values = dict(cohort.citations)
        if paper.paper_id not in citation_values:
            unavailable_cohort += 1
            continue
        expected_citations = statistics.fmean(citation_values.values())
        if expected_citations <= 0:
            unavailable_cohort += 1
            continue
        ncs = paper.citation_count / expected_citations
        percentiles = log_midrank_percentiles(
            citation_values,
            minimum_cohort=thresholds.impact.minimum_reference_cohort,
        )
        weighted_ncs.append((paper.attribution_weight, ncs))
        weighted_top_decile.append(
            (
                paper.attribution_weight,
                1.0 if percentiles.scores[paper.paper_id] >= 90.0 else 0.0,
            )
        )

    eligible_count = len(weighted_ncs)
    eligible_weight = math.fsum(weight for weight, _ in weighted_ncs)
    if eligible_count < thresholds.impact.minimum_eligible_papers:
        reasons.append("eligible paper count is below the Impact v1 minimum")
    if eligible_weight <= 0:
        reasons.append("eligible fractional citation evidence is absent")
    mncs = (
        math.fsum(weight * value for weight, value in weighted_ncs) / eligible_weight
        if eligible_weight > 0
        else None
    )
    pp_top_10 = (
        math.fsum(weight * value for weight, value in weighted_top_decile)
        / eligible_weight
        if eligible_weight > 0
        else None
    )
    return _result(
        partition,
        "research_impact",
        raw_value=None if reasons else mncs,
        normalized_value=None,
        components={
            "mncs": mncs,
            "pp_top_10_share": pp_top_10,
            "pp_top_10_tie_policy": "log1p-midrank-percentile-at-least-90",
            "eligible_papers": eligible_count,
            "eligible_fractional_paper_mass": eligible_weight,
            "citation_coverage": effective_coverage,
            "citation_maturity_months": thresholds.impact.citation_maturity_months,
            "citation_cutoff": partition.as_of_date.isoformat(),
            "maturity_ineligible_papers": ineligible_maturity,
            "unavailable_reference_cohorts": unavailable_cohort,
        },
        parameters={},
        input_count=eligible_count,
        thresholds=thresholds,
        missing_reasons=reasons,
    )


def normalize_impact_results(
    results: Sequence[MetricCalculationResult],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> tuple[MetricCalculationResult, ...]:
    output = list(results)
    for cohort in _normalization_cohorts(results, "research_impact").values():
        raw = {
            result.entity_id: result.raw_value
            for _, result in cohort
            if result.raw_value is not None and not result.missing_reasons
        }
        normalized = robust_mncs_cohort(
            raw, minimum_cohort=thresholds.impact.minimum_normalization_cohort
        )
        for index, result in cohort:
            output[index] = replace(
                result,
                normalized_value=normalized.scores.get(result.entity_id),
                normalization_parameters={
                    **normalized.parameters,
                    "field_id": result.field_id,
                    "terminal_year": int(result.period),
                    "threshold_version": thresholds.version,
                },
                missing_reasons=(
                    result.missing_reasons
                    if result.raw_value is None or normalized.eligible
                    else (
                        *result.missing_reasons,
                        normalized.reason or "normalization failed",
                    )
                ),
            )
    return tuple(output)


def _weighted_boolean_share(
    papers: Sequence[AttributedPaperEvidence], attribute: str
) -> tuple[float | None, float]:
    known = [paper for paper in papers if getattr(paper, attribute) is not None]
    known_weight = math.fsum(paper.attribution_weight for paper in known)
    if known_weight <= 0:
        return None, 0.0
    positive = math.fsum(
        paper.attribution_weight for paper in known if getattr(paper, attribute) is True
    )
    return positive / known_weight, known_weight


def calculate_connectivity(
    partition: MetricPartitionInput,
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> MetricCalculationResult:
    papers = _window_papers(partition, 3)
    fractional_papers = math.fsum(paper.attribution_weight for paper in papers)
    researchers = {item for paper in papers for item in paper.researcher_ids}
    reasons = _base_coverage_reasons(
        partition,
        thresholds,
        require_geographic_attribution=partition.entity_type
        in {"institution", "country"},
    )
    if reason := _complete_window_reason(partition, 3):
        reasons.append(reason)
    if fractional_papers < thresholds.connectivity.minimum_fractional_papers:
        reasons.append("fractional paper output is below the Connectivity v1 minimum")
    if len(researchers) < thresholds.connectivity.minimum_identifiable_researchers:
        reasons.append("researcher count is below the Connectivity v1 minimum")

    shares = {
        name: _weighted_boolean_share(papers, name)
        for name in ("collaborative", "cross_institution", "international")
    }
    primary_component = {
        "researcher": "collaborative",
        "institution": "cross_institution",
        "country": "international",
    }[partition.entity_type]
    primary_share, known_weight = shares[primary_component]
    relationship_coverage = (
        known_weight / fractional_papers if fractional_papers > 0 else None
    )
    supplied_relationship_coverage = partition.coverage.collaboration_relationship
    effective_relationship_values = [
        value
        for value in (relationship_coverage, supplied_relationship_coverage)
        if value is not None
    ]
    effective_relationship_coverage = min(effective_relationship_values, default=None)
    if (
        effective_relationship_coverage is None
        or effective_relationship_coverage
        < thresholds.connectivity.minimum_relationship_coverage
    ):
        reasons.append("relationship coverage is below the Connectivity v1 minimum")
    if primary_share is None:
        reasons.append("the entity-specific collaboration indicator is missing")

    partner_ids = {item for paper in papers for item in paper.partner_entity_ids}
    return _result(
        partition,
        "collaboration",
        raw_value=None if reasons else primary_share,
        normalized_value=(
            None if reasons or primary_share is None else 100 * primary_share
        ),
        components={
            "primary_indicator": primary_component,
            "collaborative_publication_share": shares["collaborative"][0],
            "cross_institution_publication_share": shares["cross_institution"][0],
            "international_publication_share": shares["international"][0],
            "fractional_papers": fractional_papers,
            "distinct_researchers": len(researchers),
            "unique_supported_partners": len(partner_ids),
            "relationship_coverage": effective_relationship_coverage,
            "network_centrality_used": False,
        },
        parameters={
            "method": "entity-specific-bounded-collaboration-proportion",
            "output_min": 0.0,
            "output_max": 100.0,
            "threshold_version": thresholds.version,
        },
        input_count=len(papers),
        thresholds=thresholds,
        missing_reasons=reasons,
    )


def calculate_diversity(
    partition: MetricPartitionInput,
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> MetricCalculationResult:
    papers = _window_papers(partition, 3)
    total_weight = math.fsum(paper.attribution_weight for paper in papers)
    category_totals = {
        category_id: 0.0 for category_id in partition.eligible_category_ids
    }
    classified_weight = 0.0
    for paper in papers:
        categories = dict(paper.category_weights)
        unsupported = set(categories) - set(category_totals)
        if unsupported:
            raise ValueError(
                "paper categories are outside the versioned eligible category universe"
            )
        if not categories:
            continue
        classified_weight += paper.attribution_weight
        for category_id, category_share in categories.items():
            category_totals[category_id] += paper.attribution_weight * category_share

    calculated_coverage = classified_weight / total_weight if total_weight > 0 else None
    effective_coverage_values = [
        value
        for value in (calculated_coverage, partition.coverage.field_attribution)
        if value is not None
    ]
    effective_coverage = min(effective_coverage_values, default=None)
    reasons = _base_coverage_reasons(
        partition,
        thresholds,
        require_geographic_attribution=partition.entity_type
        in {"institution", "country"},
    )
    if reason := _complete_window_reason(partition, 3):
        reasons.append(reason)
    if total_weight < thresholds.diversity.minimum_fractional_papers:
        reasons.append("fractional paper output is below the Diversity v1 minimum")
    if len(category_totals) < 2:
        reasons.append("fewer than two eligible canonical categories are available")
    if (
        effective_coverage is None
        or effective_coverage < thresholds.coverage.field_attribution
    ):
        reasons.append("field attribution coverage is below the Diversity v1 threshold")
    entropy = normalized_shannon_evenness(category_totals)
    if not entropy.eligible:
        reasons.append(entropy.reason or "diversity calculation is unavailable")
    variety = sum(1 for value in category_totals.values() if value > 0)
    return _result(
        partition,
        "research_diversity",
        raw_value=None if reasons else entropy.raw_value,
        normalized_value=None if reasons else entropy.score,
        components={
            "fractional_papers": total_weight,
            "classified_fractional_papers": classified_weight,
            "field_attribution_coverage": effective_coverage,
            "variety": variety,
            "balance": entropy.raw_value,
            "disparity": None,
            "eligible_category_count": len(category_totals),
        },
        parameters={
            **entropy.parameters,
            "ontology_version": partition.ontology_version,
            "eligible_category_ids": ",".join(partition.eligible_category_ids),
            "threshold_version": thresholds.version,
        },
        input_count=len(papers),
        thresholds=thresholds,
        missing_reasons=reasons,
    )


def calculate_momentum_raw(
    partition: MetricPartitionInput,
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> MetricCalculationResult:
    required_years = thresholds.momentum.required_complete_years
    reasons = _base_coverage_reasons(
        partition,
        thresholds,
        require_geographic_attribution=partition.entity_type
        in {"institution", "country"},
    )
    if partition.terminal_year >= partition.as_of_date.year:
        reasons.append("the incomplete current calendar year is excluded from Momentum")
    if reason := _complete_window_reason(partition, required_years):
        reasons.append(reason)
    window_papers = _window_papers(partition, required_years)
    annual = {
        year: math.fsum(
            paper.attribution_weight
            for paper in window_papers
            if paper.publication_date.year == year
        )
        for year in sorted(_years(partition, required_years))
    }
    baseline_end = partition.terminal_year - 3
    baseline = math.fsum(
        value for year, value in annual.items() if year <= baseline_end
    )
    recent = math.fsum(value for year, value in annual.items() if year > baseline_end)
    minimum = thresholds.momentum.minimum_fractional_papers_per_window
    if baseline < minimum:
        reasons.append("baseline window is below the Momentum v1 minimum")
    if recent < minimum:
        reasons.append("recent window is below the Momentum v1 minimum")
    log_change = math.log(recent / baseline) if baseline > 0 and recent > 0 else None
    annual_values = [annual[year] for year in sorted(annual)]
    annual_log_changes = [
        math.log1p(current) - math.log1p(previous)
        for previous, current in zip(annual_values, annual_values[1:], strict=False)
    ]
    volatility = (
        statistics.median(
            abs(value - statistics.median(annual_log_changes))
            for value in annual_log_changes
        )
        if annual_log_changes
        else None
    )
    persistence = (
        sum(1 for value in annual_values if value > 0) / required_years
        if required_years
        else None
    )
    return _result(
        partition,
        "momentum",
        raw_value=None if reasons else log_change,
        normalized_value=None,
        components={
            "baseline_fractional_papers": baseline,
            "recent_fractional_papers": recent,
            "relative_log_activity_change": log_change,
            "persistence_fraction_of_years": persistence,
            "annual_log_change_volatility_mad": volatility,
            "window_coverage": (
                len(
                    set(partition.complete_source_years)
                    & _years(partition, required_years)
                )
                / required_years
            ),
            "baseline_start_year": partition.terminal_year - 5,
            "baseline_end_year": baseline_end,
            "recent_start_year": partition.terminal_year - 2,
            "recent_end_year": partition.terminal_year,
        },
        parameters={},
        input_count=len(window_papers),
        thresholds=thresholds,
        missing_reasons=reasons,
    )


def normalize_momentum_results(
    results: Sequence[MetricCalculationResult],
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> tuple[MetricCalculationResult, ...]:
    output = list(results)
    for cohort in _normalization_cohorts(results, "momentum").values():
        raw = {
            result.entity_id: result.raw_value
            for _, result in cohort
            if result.raw_value is not None and not result.missing_reasons
        }
        normalized = robust_centered_change_cohort(
            raw,
            minimum_cohort=thresholds.momentum.minimum_normalization_cohort,
            z_clip=thresholds.momentum.robust_z_clip,
        )
        for index, result in cohort:
            output[index] = replace(
                result,
                normalized_value=normalized.scores.get(result.entity_id),
                components={
                    **result.components,
                    "field_cohort_median_log_change": normalized.parameters.get(
                        "fitted_median"
                    ),
                    "field_relative_log_change": (
                        result.raw_value - float(normalized.parameters["fitted_median"])
                        if result.raw_value is not None
                        and "fitted_median" in normalized.parameters
                        else None
                    ),
                },
                normalization_parameters={
                    **normalized.parameters,
                    "field_id": result.field_id,
                    "terminal_year": int(result.period),
                    "threshold_version": thresholds.version,
                },
                missing_reasons=(
                    result.missing_reasons
                    if result.raw_value is None or normalized.eligible
                    else (
                        *result.missing_reasons,
                        normalized.reason or "normalization failed",
                    )
                ),
            )
    return tuple(output)
