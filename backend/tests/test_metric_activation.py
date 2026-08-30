from dataclasses import replace

from physics_atlas_api.fields import (
    CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
    FIELD_WEIGHTING_POLICY_VERSION,
)
from physics_atlas_api.metrics import (
    CANDIDATE_METRIC_IDS,
    METRIC_CONTRACTS,
    JointMetricActivationDecision,
    MetricAlgorithmActivationEvidence,
    MetricSystemActivationEvidence,
    MetricSystemCoverageEvidence,
    assess_joint_metric_activation,
)


def algorithm_evidence(metric_id: str) -> MetricAlgorithmActivationEvidence:
    contract = METRIC_CONTRACTS[metric_id]
    return MetricAlgorithmActivationEvidence(
        metric_id=metric_id,
        definition_version=contract.version,
        algorithm_version=contract.algorithm_version,
        normalization_version=contract.normalization_version,
        implemented=True,
        deterministic_reproduction_passed=True,
    )


def complete_evidence() -> MetricSystemActivationEvidence:
    return MetricSystemActivationEvidence(
        metric_system_version="physics-atlas-metric-system-v1",
        algorithms=tuple(algorithm_evidence(item) for item in CANDIDATE_METRIC_IDS),
        attribution_policy_version="fractional-attribution-v1",
        attribution_validation_passed=True,
        ontology_version="physics-field-ontology-v1",
        provider_mapping_versions=(
            ("inspire", "provider-field-mapping-v1"),
            ("arxiv", "provider-field-mapping-v1"),
        ),
        threshold_version="metric-validation-thresholds-v1",
        coverage=MetricSystemCoverageEvidence(
            paper_time_affiliation=0.90,
            canonical_institution=0.95,
            citation=0.90,
            field_attribution=0.90,
        ),
        historical_coverage_validated=True,
        citation_maturity_validated=True,
        normalization_validated=True,
        provenance_complete=True,
        deterministic_reproduction_passed=True,
        field_weighting_policy_version=FIELD_WEIGHTING_POLICY_VERSION,
        field_reconciliation_version=CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
        field_weight_conservation_passed=True,
    )


def test_joint_gate_requires_exactly_all_five_metric_algorithms() -> None:
    evidence = complete_evidence()
    eligible = assess_joint_metric_activation(evidence)
    assert eligible == JointMetricActivationDecision(
        metric_system_version="physics-atlas-metric-system-v1",
        status="eligible-for-reviewed-activation",
        metric_ids=CANDIDATE_METRIC_IDS,
        reasons=(),
    )
    assert eligible.may_activate is True

    partial = assess_joint_metric_activation(
        replace(evidence, algorithms=evidence.algorithms[:-1])
    )
    assert partial.status == "withheld"
    assert "exactly the five metrics" in " ".join(partial.reasons)


def test_joint_gate_enforces_versions_and_every_validation_dimension() -> None:
    evidence = complete_evidence()
    stale_algorithm = replace(
        evidence.algorithms[0], algorithm_version="stale-algorithm"
    )
    failed = assess_joint_metric_activation(
        replace(
            evidence,
            algorithms=(stale_algorithm, *evidence.algorithms[1:]),
            attribution_validation_passed=False,
            provider_mapping_versions=(("inspire", "mapping-v1"),),
            coverage=replace(evidence.coverage, citation=0.8999),
            historical_coverage_validated=False,
            citation_maturity_validated=False,
            normalization_validated=False,
            provenance_complete=False,
            deterministic_reproduction_passed=False,
            field_weighting_policy_version="stale-field-weighting",
            field_reconciliation_version="stale-reconciliation",
            field_weight_conservation_passed=False,
        )
    )
    reasons = " ".join(failed.reasons)
    assert failed.status == "withheld"
    assert "algorithm version" in reasons
    assert "fractional attribution validation" in reasons
    assert "arxiv field mapping" in reasons
    assert "citation coverage" in reasons
    assert "historical coverage" in reasons
    assert "citation-age" in reasons
    assert "normalization validation" in reasons
    assert "provenance is incomplete" in reasons
    assert "system-level deterministic reproduction" in reasons
    assert "field weighting policy version" in reasons
    assert "cross-provider field reconciliation version" in reasons
    assert "field-weight conservation" in reasons


def test_joint_gate_fails_closed_for_a_legacy_manifest_without_field_proof() -> None:
    evidence = complete_evidence()

    decision = assess_joint_metric_activation(
        replace(
            evidence,
            field_weighting_policy_version=None,
            field_reconciliation_version=None,
            field_weight_conservation_passed=False,
        )
    )

    assert decision.status == "withheld"
    assert decision.may_activate is False


def test_entity_level_missing_observation_does_not_disable_eligible_system() -> None:
    decision = assess_joint_metric_activation(complete_evidence())
    entity_observations: dict[str, float | None] = {
        "institution-princeton": 61.0,
        "institution-small": None,
    }

    assert decision.may_activate is True
    assert entity_observations["institution-small"] is None
    assert entity_observations["institution-princeton"] == 61.0


def test_current_candidate_contracts_and_unvalidated_evidence_remain_withheld() -> None:
    assert all(
        contract.implementation_status == "experimental-candidate"
        for contract in METRIC_CONTRACTS.values()
    )
    evidence = replace(
        complete_evidence(),
        attribution_validation_passed=False,
        historical_coverage_validated=False,
        citation_maturity_validated=False,
        normalization_validated=False,
        provenance_complete=False,
        deterministic_reproduction_passed=False,
        coverage=MetricSystemCoverageEvidence(
            paper_time_affiliation=None,
            canonical_institution=None,
            citation=None,
            field_attribution=None,
        ),
    )
    decision = assess_joint_metric_activation(evidence)
    assert decision.status == "withheld"
    assert decision.may_activate is False
