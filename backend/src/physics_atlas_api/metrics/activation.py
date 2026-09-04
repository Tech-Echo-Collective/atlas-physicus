from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from ..attribution import FRACTIONAL_ATTRIBUTION_V1
from ..fields import (
    CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
    FIELD_WEIGHTING_POLICY_VERSION,
    PHYSICS_FIELD_ONTOLOGY_VERSION,
    PROVIDER_FIELD_MAPPING_VERSION,
)
from .contracts import CANDIDATE_METRIC_IDS, get_metric_contract
from .thresholds import (
    METRIC_VALIDATION_THRESHOLDS_V1,
    MetricValidationThresholds,
)

JointActivationStatus = Literal["withheld", "eligible-for-reviewed-activation"]
AcquisitionBoundaryKind = Literal["field-conditioned", "broad-physics"]
METRIC_SYSTEM_V1_VERSION = "physics-atlas-metric-system-v1"
DIVERSITY_BREADTH_REVIEW_VERSION = "diversity-breadth-review-v1"
HEP_TH_CONDITIONED_SCOPE = "hep-th-v1"
COND_MAT_CONDITIONED_SCOPE = "cond-mat-validation-v1"
KNOWN_FIELD_CONDITIONED_SCOPES = frozenset(
    (HEP_TH_CONDITIONED_SCOPE, COND_MAT_CONDITIONED_SCOPE)
)


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
    field_weighting_policy_version: str | None = None
    field_reconciliation_version: str | None = None
    field_weight_conservation_passed: bool = False
    acquisition_scope: str | None = None
    acquisition_boundary_kind: AcquisitionBoundaryKind | None = None
    data_source_version: str | None = None
    diversity_breadth_review_version: str | None = None
    diversity_breadth_review_passed: bool = False

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


def field_validation_manifest_is_current(
    validation_evidence: Mapping[str, object],
) -> bool:
    """Fail closed unless a persisted release records the selected-ledger proof.

    These keys live in the existing JSON validation manifest so tightening the
    scientific gate does not require a schema migration. Older reviewed
    manifests remain readable, but cannot publish observations until they are
    re-reviewed against the conserved cross-provider ledger.
    """

    return (
        validation_evidence.get("fieldWeightingPolicyVersion")
        == FIELD_WEIGHTING_POLICY_VERSION
        and validation_evidence.get("fieldReconciliationVersion")
        == CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION
        and validation_evidence.get("fieldWeightConservationPassed") is True
    )


def reviewed_activation_manifest_is_current(
    validation_evidence: Mapping[str, object],
    *,
    expected_acquisition_scope: str | None = None,
    expected_data_source_version: str | None = None,
) -> bool:
    """Bind a persisted joint review to its dataset and broad-field evidence.

    The bounded ``hep-th-v1`` corpus is intentionally conditioned on one field
    and cannot validate Research Diversity. Older manifests remain readable,
    but a bare ``jointGatePassed`` flag cannot publish or preserve live metric
    state without the current field and breadth-review proofs.
    """

    acquisition_scope = validation_evidence.get("acquisitionScope")
    data_source_version = validation_evidence.get("dataSourceVersion")
    return (
        validation_evidence.get("jointGatePassed") is True
        and field_validation_manifest_is_current(validation_evidence)
        and isinstance(acquisition_scope, str)
        and bool(acquisition_scope.strip())
        and acquisition_scope not in KNOWN_FIELD_CONDITIONED_SCOPES
        and validation_evidence.get("acquisitionBoundaryKind") == "broad-physics"
        and (
            expected_acquisition_scope is None
            or acquisition_scope == expected_acquisition_scope
        )
        and isinstance(data_source_version, str)
        and bool(data_source_version.strip())
        and (
            expected_data_source_version is None
            or data_source_version == expected_data_source_version
        )
        and validation_evidence.get("diversityBreadthReviewVersion")
        == DIVERSITY_BREADTH_REVIEW_VERSION
        and validation_evidence.get("diversityBreadthReviewPassed") is True
    )


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
    if evidence.field_weighting_policy_version != FIELD_WEIGHTING_POLICY_VERSION:
        reasons.append("field weighting policy version does not match the contract")
    if (
        evidence.field_reconciliation_version
        != CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION
    ):
        reasons.append("cross-provider field reconciliation version does not match")
    if not evidence.field_weight_conservation_passed:
        reasons.append("per-paper field-weight conservation has not passed")
    if not evidence.acquisition_scope or not evidence.acquisition_scope.strip():
        reasons.append("acquisition scope is missing")
    elif evidence.acquisition_scope in KNOWN_FIELD_CONDITIONED_SCOPES:
        reasons.append(
            f"{evidence.acquisition_scope} cannot validate the broad-field "
            "Research Diversity boundary"
        )
    if evidence.acquisition_boundary_kind != "broad-physics":
        reasons.append(
            "the acquisition boundary is not certified as broad Physics evidence"
        )
    if not evidence.data_source_version or not evidence.data_source_version.strip():
        reasons.append("data source version is missing")
    if evidence.diversity_breadth_review_version != DIVERSITY_BREADTH_REVIEW_VERSION:
        reasons.append("Diversity breadth-review version does not match the contract")
    if not evidence.diversity_breadth_review_passed:
        reasons.append("broad-field Research Diversity review has not passed")
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
