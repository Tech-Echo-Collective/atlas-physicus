from dataclasses import dataclass
from typing import Literal

from ..attribution import FRACTIONAL_ATTRIBUTION_V1
from ..fields import PHYSICS_FIELD_ONTOLOGY_VERSION, PROVIDER_FIELD_MAPPING_VERSION
from .contracts import CANDIDATE_METRIC_IDS, get_metric_contract
from .thresholds import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    MetricValidationThresholds,
)

JointActivationStatus = Literal["withheld", "eligible-for-reviewed-activation"]
METRIC_SYSTEM_V1_VERSION = "physics-atlas-metric-system-v1"


@dataclass(frozen=True)
class MetricAlgorithmActivationEvidence:
    metric_id: str
    definition_version: str
    algorithm_version: str
    normalization_version: str
    implemented: bool
    deterministic_reproduction_passed: bool


@dataclass(frozen=True)
class MetricSystemCoverageEvidence:
    paper_time_affiliation: float | None
    canonical_institution: float | None
    citation: float | None
    field_attribution: float | None

    def __post_init__(self) -> None:
        for name, value in (
            ("paper_time_affiliation", self.paper_time_affiliation),
            ("canonical_institution", self.canonical_institution),
            ("citation", self.citation),
            ("field_attribution", self.field_attribution),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{name} coverage must be between zero and one")


@dataclass(frozen=True)
class MetricSystemActivationEvidence:
    metric_system_version: str
    algorithms: tuple[MetricAlgorithmActivationEvidence, ...]
    attribution_policy_version: str | None
    attribution_validation_passed: bool
    ontology_version: str | None
    provider_mapping_versions: tuple[tuple[str, str], ...]
    threshold_version: str
    coverage: MetricSystemCoverageEvidence
    historical_coverage_validated: bool
    citation_maturity_validated: bool
    normalization_validated: bool
    provenance_complete: bool
    deterministic_reproduction_passed: bool

    def __post_init__(self) -> None:
        metric_ids = [item.metric_id for item in self.algorithms]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("joint activation algorithm metric ids must be unique")
        providers = [provider for provider, _ in self.provider_mapping_versions]
        if len(providers) != len(set(providers)):
            raise ValueError("provider mapping evidence must use unique providers")


@dataclass(frozen=True)
class JointMetricActivationDecision:
    metric_system_version: str
    status: JointActivationStatus
    metric_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def may_activate(self) -> bool:
        return self.status == "eligible-for-reviewed-activation"


def assess_joint_metric_activation(
    evidence: MetricSystemActivationEvidence,
    thresholds: MetricValidationThresholds = METRIC_VALIDATION_THRESHOLDS_V1,
) -> JointMetricActivationDecision:
    """Fail the public system closed unless all five dimensions pass together.

    This is a system-level decision. Once it passes, an individual entity may
    still have a missing observation because its own evidence thresholds fail;
    entity availability is deliberately not an input to this global decision.
    """
    reasons: list[str] = []
    if evidence.metric_system_version != METRIC_SYSTEM_V1_VERSION:
        reasons.append("metric system version does not match Metric System v1")
    expected_ids = set(CANDIDATE_METRIC_IDS)
    algorithms = {item.metric_id: item for item in evidence.algorithms}
    if set(algorithms) != expected_ids:
        reasons.append("the activation manifest must contain exactly the five metrics")

    for metric_id in CANDIDATE_METRIC_IDS:
        algorithm = algorithms.get(metric_id)
        contract = get_metric_contract(metric_id)
        if algorithm is None or contract is None:
            continue
        if algorithm.definition_version != contract.version:
            reasons.append(
                f"{metric_id} definition version does not match the contract"
            )
        if algorithm.algorithm_version != contract.algorithm_version:
            reasons.append(f"{metric_id} algorithm version does not match the contract")
        if algorithm.normalization_version != contract.normalization_version:
            reasons.append(
                f"{metric_id} normalization version does not match the contract"
            )
        if not algorithm.implemented:
            reasons.append(f"{metric_id} algorithm is not implemented")
        if not algorithm.deterministic_reproduction_passed:
            reasons.append(f"{metric_id} deterministic reproduction has not passed")

    if evidence.attribution_policy_version != FRACTIONAL_ATTRIBUTION_V1.version:
        reasons.append("scientific attribution policy version does not match v1")
    if not evidence.attribution_validation_passed:
        reasons.append("fractional attribution validation has not passed")
    if evidence.ontology_version != PHYSICS_FIELD_ONTOLOGY_VERSION:
        reasons.append("canonical Physics ontology version does not match v1")
    mappings = dict(evidence.provider_mapping_versions)
    for provider in ("inspire", "arxiv"):
        if mappings.get(provider) != PROVIDER_FIELD_MAPPING_VERSION:
            reasons.append(f"{provider} field mapping version does not match v1")
    if evidence.threshold_version != thresholds.version:
        reasons.append("metric validation threshold version does not match v1")

    coverage_checks = (
        (
            "paper-time affiliation",
            evidence.coverage.paper_time_affiliation,
            thresholds.coverage.paper_time_affiliation,
        ),
        (
            "canonical institution",
            evidence.coverage.canonical_institution,
            thresholds.coverage.canonical_institution,
        ),
        (
            "citation",
            evidence.coverage.citation,
            thresholds.coverage.citation,
        ),
        (
            "field attribution",
            evidence.coverage.field_attribution,
            thresholds.coverage.field_attribution,
        ),
    )
    for label, value, minimum in coverage_checks:
        if value is None or value < minimum:
            reasons.append(f"{label} coverage is below {minimum:.0%}")
    if not evidence.historical_coverage_validated:
        reasons.append("six-year closed-window historical coverage is not validated")
    if not evidence.citation_maturity_validated:
        reasons.append("citation-age and common-cutoff handling are not validated")
    if not evidence.normalization_validated:
        reasons.append("metric-specific normalization validation has not passed")
    if not evidence.provenance_complete:
        reasons.append("reconstruction provenance is incomplete")
    if not evidence.deterministic_reproduction_passed:
        reasons.append("system-level deterministic reproduction has not passed")

    return JointMetricActivationDecision(
        metric_system_version=evidence.metric_system_version,
        status="withheld" if reasons else "eligible-for-reviewed-activation",
        metric_ids=tuple(CANDIDATE_METRIC_IDS),
        reasons=tuple(dict.fromkeys(reasons)),
    )
