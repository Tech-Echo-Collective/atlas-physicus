"""Fail-closed, versioned storage readiness gate for future corpus loads."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from ..metrics.activation import (
    JointMetricActivationDecision,
    MetricSystemActivationEvidence,
    assess_joint_metric_activation,
)
from .contracts import ArtifactRef, ArtifactStore

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
STORAGE_EVIDENCE_DOCUMENT_VERSION = "storage-budget-evidence-document-v1"
STORAGE_PROJECTION_METHOD_V1 = "final-schema-linear-lower-bound-v1"
_STORAGE_GATE_VERIFICATION_TOKEN = object()
_SCIENTIFIC_GATE_VERIFICATION_TOKEN = object()


def _canonical_json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported canonical storage evidence value: {type(value)!r}")


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_payload(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=_canonical_json_default,
    ).encode("utf-8")


def _validate_evidence_pointer(
    label: str,
    digest: str | None,
    reference: str | None,
) -> None:
    if digest is None and reference is None:
        return
    if digest is None or reference is None:
        raise ValueError(f"{label} digest and reference must be provided together")
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{label} digest must be a lowercase SHA-256 value")
    if not reference.strip():
        raise ValueError(f"{label} reference must be non-empty")


def _validate_nonnegative_optional(name: str, value: int | None) -> None:
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise ValueError(f"{name} must be a nonnegative integer or None")


def _ceil_ratio(value: int, numerator: int, denominator: int) -> int:
    return (value * numerator + denominator - 1) // denominator


@dataclass(frozen=True)
class StorageBudgetPolicy:
    """Capacity policy; basis points avoid floating-point boundary drift."""

    version: str
    minimum_representative_papers: int
    contingency_basis_points: int
    steady_state_limit_basis_points: int
    peak_limit_basis_points: int

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("storage budget policy version must be non-empty")
        if self.minimum_representative_papers <= 0:
            raise ValueError("minimum representative paper count must be positive")
        if not 0 <= self.contingency_basis_points <= 10_000:
            raise ValueError("contingency must be between zero and 100%")
        if not 0 < self.steady_state_limit_basis_points < 10_000:
            raise ValueError("steady-state limit must be between zero and 100%")
        if not (
            self.steady_state_limit_basis_points < self.peak_limit_basis_points < 10_000
        ):
            raise ValueError("peak limit must be above steady state and below 100%")


STORAGE_BUDGET_POLICY_V1 = StorageBudgetPolicy(
    version="storage-budget-gate-v1",
    minimum_representative_papers=10_000,
    contingency_basis_points=2_500,
    steady_state_limit_basis_points=6_000,
    peak_limit_basis_points=8_000,
)


@dataclass(frozen=True)
class StorageBudgetEvidence:
    """Measured and projected evidence for one proposed full-load boundary."""

    capacity_bytes: int | None
    current_used_bytes: int | None
    measured_sample_papers: int | None
    measured_sample_bytes: int | None
    measured_fixed_bytes: int | None
    measurement_environment_id: str | None
    measured_at: datetime | None
    target_papers: int | None
    target_population_id: str | None
    target_population_policy_version: str | None
    target_population_cutoff: datetime | None
    target_population_paper_ids_digest: str | None
    projection_method_version: str | None
    projected_steady_state_bytes: int | None
    projected_peak_bytes: int | None
    representative_final_schema: bool
    database_statistics_refreshed: bool
    peak_working_set_included: bool
    certification_storage_included: bool
    citation_storage_included: bool
    cold_payloads_externalized: bool
    artifact_integrity_verified: bool
    backup_restore_verified: bool
    backup_id: str | None = None
    backup_digest: str | None = None
    restore_target_id: str | None = None
    restore_environment_id: str | None = None
    restore_checks_digest: str | None = None
    restore_completed_at: datetime | None = None
    restore_reviewer_id: str | None = None
    measured_audit_digest: str | None = None
    measured_audit_reference: str | None = None
    projection_evidence_digest: str | None = None
    projection_evidence_reference: str | None = None
    backup_restore_evidence_digest: str | None = None
    backup_restore_evidence_reference: str | None = None
    target_population_evidence_digest: str | None = None
    target_population_evidence_reference: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "capacity_bytes",
            "current_used_bytes",
            "measured_sample_papers",
            "measured_sample_bytes",
            "measured_fixed_bytes",
            "target_papers",
            "projected_steady_state_bytes",
            "projected_peak_bytes",
        ):
            _validate_nonnegative_optional(name, getattr(self, name))
        if (
            self.measured_fixed_bytes is not None
            and self.measured_sample_bytes is not None
            and self.measured_fixed_bytes > self.measured_sample_bytes
        ):
            raise ValueError("measured fixed bytes cannot exceed measured sample bytes")
        for name in (
            "measurement_environment_id",
            "target_population_id",
            "target_population_policy_version",
            "projection_method_version",
            "backup_id",
            "restore_target_id",
            "restore_environment_id",
            "restore_reviewer_id",
        ):
            value = getattr(self, name)
            if value is not None and not value.strip():
                raise ValueError(f"{name} must be non-empty when provided")
        for name in (
            "target_population_paper_ids_digest",
            "backup_digest",
            "restore_checks_digest",
        ):
            value = getattr(self, name)
            if value is not None and _SHA256_PATTERN.fullmatch(value) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256 value")
        for name in (
            "measured_at",
            "target_population_cutoff",
            "restore_completed_at",
        ):
            value = getattr(self, name)
            if value is not None and (
                value.tzinfo is None or value.utcoffset() is None
            ):
                raise ValueError(f"{name} must include a timezone")
        for name in (
            "representative_final_schema",
            "database_statistics_refreshed",
            "peak_working_set_included",
            "certification_storage_included",
            "citation_storage_included",
            "cold_payloads_externalized",
            "artifact_integrity_verified",
            "backup_restore_verified",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean evidence")
        _validate_evidence_pointer(
            "measured audit", self.measured_audit_digest, self.measured_audit_reference
        )
        _validate_evidence_pointer(
            "projection evidence",
            self.projection_evidence_digest,
            self.projection_evidence_reference,
        )
        _validate_evidence_pointer(
            "backup/restore evidence",
            self.backup_restore_evidence_digest,
            self.backup_restore_evidence_reference,
        )
        _validate_evidence_pointer(
            "target population evidence",
            self.target_population_evidence_digest,
            self.target_population_evidence_reference,
        )


def measured_storage_audit_payload(evidence: StorageBudgetEvidence) -> bytes:
    """Canonical content expected in the measured-audit artifact."""

    return _canonical_payload(
        {
            "document_version": STORAGE_EVIDENCE_DOCUMENT_VERSION,
            "kind": "measured-storage-audit",
            "policy_version": STORAGE_BUDGET_POLICY_V1.version,
            "capacity_bytes": evidence.capacity_bytes,
            "current_used_bytes": evidence.current_used_bytes,
            "measured_sample_papers": evidence.measured_sample_papers,
            "measured_sample_bytes": evidence.measured_sample_bytes,
            "measured_fixed_bytes": evidence.measured_fixed_bytes,
            "measurement_environment_id": evidence.measurement_environment_id,
            "measured_at": (
                evidence.measured_at.isoformat() if evidence.measured_at else None
            ),
            "representative_final_schema": evidence.representative_final_schema,
            "database_statistics_refreshed": (evidence.database_statistics_refreshed),
        }
    )


def storage_projection_payload(evidence: StorageBudgetEvidence) -> bytes:
    """Canonical content expected in the full-load projection artifact."""

    return _canonical_payload(
        {
            "document_version": STORAGE_EVIDENCE_DOCUMENT_VERSION,
            "kind": "storage-projection",
            "policy_version": STORAGE_BUDGET_POLICY_V1.version,
            "target_papers": evidence.target_papers,
            "target_population_id": evidence.target_population_id,
            "target_population_policy_version": (
                evidence.target_population_policy_version
            ),
            "target_population_cutoff": (
                evidence.target_population_cutoff.isoformat()
                if evidence.target_population_cutoff
                else None
            ),
            "target_population_paper_ids_digest": (
                evidence.target_population_paper_ids_digest
            ),
            "projection_method_version": evidence.projection_method_version,
            "measured_sample_papers": evidence.measured_sample_papers,
            "measured_sample_bytes": evidence.measured_sample_bytes,
            "measured_fixed_bytes": evidence.measured_fixed_bytes,
            "projected_steady_state_bytes": (evidence.projected_steady_state_bytes),
            "projected_peak_bytes": evidence.projected_peak_bytes,
            "peak_working_set_included": evidence.peak_working_set_included,
            "certification_storage_included": (evidence.certification_storage_included),
            "citation_storage_included": evidence.citation_storage_included,
            "cold_payloads_externalized": evidence.cold_payloads_externalized,
            "artifact_integrity_verified": evidence.artifact_integrity_verified,
        }
    )


def backup_restore_evidence_payload(evidence: StorageBudgetEvidence) -> bytes:
    """Canonical content expected in an isolated backup/restore evidence artifact."""

    return _canonical_payload(
        {
            "document_version": STORAGE_EVIDENCE_DOCUMENT_VERSION,
            "kind": "backup-restore-evidence",
            "policy_version": STORAGE_BUDGET_POLICY_V1.version,
            "backup_restore_verified": evidence.backup_restore_verified,
            "backup_id": evidence.backup_id,
            "backup_digest": evidence.backup_digest,
            "restore_target_id": evidence.restore_target_id,
            "restore_environment_id": evidence.restore_environment_id,
            "restore_checks_digest": evidence.restore_checks_digest,
            "restore_completed_at": (
                evidence.restore_completed_at.isoformat()
                if evidence.restore_completed_at
                else None
            ),
            "restore_reviewer_id": evidence.restore_reviewer_id,
        }
    )


def target_population_evidence_payload(evidence: StorageBudgetEvidence) -> bytes:
    """Canonical manifest for the exact population a projection authorizes."""

    return _canonical_payload(
        {
            "document_version": STORAGE_EVIDENCE_DOCUMENT_VERSION,
            "kind": "target-population-evidence",
            "policy_version": STORAGE_BUDGET_POLICY_V1.version,
            "target_population_id": evidence.target_population_id,
            "target_population_policy_version": (
                evidence.target_population_policy_version
            ),
            "target_population_cutoff": (
                evidence.target_population_cutoff.isoformat()
                if evidence.target_population_cutoff
                else None
            ),
            "canonical_paper_count": evidence.target_papers,
            "canonical_paper_ids_digest": (evidence.target_population_paper_ids_digest),
        }
    )


def storage_budget_evidence_digest(
    evidence: StorageBudgetEvidence,
    policy: StorageBudgetPolicy = STORAGE_BUDGET_POLICY_V1,
) -> str:
    """Bind a storage decision to its complete evidence and policy inputs."""

    return _canonical_digest({"evidence": asdict(evidence), "policy": asdict(policy)})


@dataclass(frozen=True)
class StorageBudgetDecision:
    policy_version: str
    status: Literal["pass", "withheld"]
    steady_state_limit_bytes: int | None
    peak_limit_bytes: int | None
    conservative_steady_state_bytes: int | None
    conservative_peak_bytes: int | None
    input_evidence_digest: str
    measured_audit_digest: str | None
    measured_audit_reference: str | None
    projection_evidence_digest: str | None
    projection_evidence_reference: str | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("storage decision policy version must be non-empty")
        if _SHA256_PATTERN.fullmatch(self.input_evidence_digest) is None:
            raise ValueError("storage decision input digest must be SHA-256")
        _validate_evidence_pointer(
            "measured audit", self.measured_audit_digest, self.measured_audit_reference
        )
        _validate_evidence_pointer(
            "projection evidence",
            self.projection_evidence_digest,
            self.projection_evidence_reference,
        )
        if self.status == "pass" and self.reasons:
            raise ValueError("passing storage decisions cannot retain failure reasons")
        if self.status == "withheld" and not self.reasons:
            raise ValueError("withheld storage decisions require explicit reasons")
        if self.status == "pass" and (
            self.measured_audit_digest is None
            or self.projection_evidence_digest is None
        ):
            raise ValueError("passing storage decisions require bound evidence")

    @property
    def may_start_full_load(self) -> bool:
        return self.status == "pass"

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(asdict(self))


def scientific_gate_evidence_digest(evidence: MetricSystemActivationEvidence) -> str:
    """Return the digest expected by a storage authorization boundary."""

    return _canonical_digest(asdict(evidence))


@dataclass(frozen=True)
class ScientificGateReview:
    reviewer_id: str
    reviewed_at: datetime
    evidence_digest: str
    decision_digest: str
    approved_for_full_load: bool

    def __post_init__(self) -> None:
        if not self.reviewer_id.strip():
            raise ValueError("scientific gate reviewer id must be non-empty")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("scientific gate review timestamp must include a timezone")
        if _SHA256_PATTERN.fullmatch(self.evidence_digest) is None:
            raise ValueError("scientific review evidence digest must be SHA-256")
        if _SHA256_PATTERN.fullmatch(self.decision_digest) is None:
            raise ValueError("scientific review decision digest must be SHA-256")
        if not isinstance(self.approved_for_full_load, bool):
            raise ValueError("scientific review approval must be boolean")


def scientific_gate_evidence_payload(
    evidence: MetricSystemActivationEvidence,
    decision: JointMetricActivationDecision,
    review: ScientificGateReview,
) -> bytes:
    """Canonical reviewed Joint Metric Gate artifact content."""

    return _canonical_payload(
        {
            "document_version": "reviewed-joint-metric-gate-evidence-v1",
            "kind": "scientific-gate-review",
            "evidence": asdict(evidence),
            "decision": asdict(decision),
            "review": {
                **asdict(review),
                "reviewed_at": review.reviewed_at.isoformat(),
            },
        }
    )


@dataclass(frozen=True, init=False)
class ScientificGateEvidence:
    """Joint Metric Gate evidence loaded from a reviewed immutable artifact."""

    evidence: MetricSystemActivationEvidence
    decision: JointMetricActivationDecision
    evidence_digest: str
    evidence_reference: str
    review: ScientificGateReview
    evidence_artifact: ArtifactRef

    def __init__(
        self,
        *,
        evidence: MetricSystemActivationEvidence,
        decision: JointMetricActivationDecision,
        evidence_digest: str,
        evidence_reference: str,
        review: ScientificGateReview,
        evidence_artifact: ArtifactRef,
        _verification_token: object | None = None,
    ) -> None:
        if _verification_token is not _SCIENTIFIC_GATE_VERIFICATION_TOKEN:
            raise ValueError(
                "scientific gate evidence must be built by "
                "verify_scientific_gate_evidence"
            )
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "evidence_digest", evidence_digest)
        object.__setattr__(self, "evidence_reference", evidence_reference)
        object.__setattr__(self, "review", review)
        object.__setattr__(self, "evidence_artifact", evidence_artifact)
        self.__post_init__()

    def __post_init__(self) -> None:
        if _SHA256_PATTERN.fullmatch(self.evidence_digest) is None:
            raise ValueError("scientific gate evidence digest must be SHA-256")
        if not self.evidence_reference.strip():
            raise ValueError("scientific gate evidence reference must be non-empty")
        if scientific_gate_evidence_digest(self.evidence) != self.evidence_digest:
            raise ValueError("scientific gate evidence digest does not match")
        if assess_joint_metric_activation(self.evidence) != self.decision:
            raise ValueError("scientific gate decision does not match its evidence")
        if self.evidence_artifact.uri != self.evidence_reference:
            raise ValueError("scientific gate artifact does not match its pointer")
        if self.review.evidence_digest != scientific_gate_evidence_digest(
            self.evidence
        ) or self.review.decision_digest != _canonical_digest(asdict(self.decision)):
            raise ValueError("scientific gate review does not bind its evidence")

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(asdict(self.decision))


def verify_scientific_gate_evidence(
    evidence: MetricSystemActivationEvidence,
    *,
    artifact_store: ArtifactStore,
    evidence_artifact: ArtifactRef,
    review: ScientificGateReview,
) -> ScientificGateEvidence:
    """Verify a reviewed, content-addressed Joint Metric Gate artifact."""

    decision = assess_joint_metric_activation(evidence)
    if review.evidence_digest != scientific_gate_evidence_digest(evidence):
        raise ValueError("scientific gate review evidence digest does not match")
    if review.decision_digest != _canonical_digest(asdict(decision)):
        raise ValueError("scientific gate review decision digest does not match")
    expected = scientific_gate_evidence_payload(evidence, decision, review)
    if _read_verified_artifact(artifact_store, evidence_artifact) != expected:
        raise ValueError("scientific gate artifact content does not match review")
    return ScientificGateEvidence(
        evidence=evidence,
        decision=decision,
        evidence_digest=scientific_gate_evidence_digest(evidence),
        evidence_reference=evidence_artifact.uri,
        review=review,
        evidence_artifact=evidence_artifact,
        _verification_token=_SCIENTIFIC_GATE_VERIFICATION_TOKEN,
    )


@dataclass(frozen=True, init=False)
class StorageGateEvidence:
    """Storage decision created only after all referenced artifacts verify."""

    evidence: StorageBudgetEvidence
    decision: StorageBudgetDecision
    evidence_digest: str
    evidence_reference: str
    measured_audit_artifact: ArtifactRef
    projection_evidence_artifact: ArtifactRef
    backup_restore_evidence_artifact: ArtifactRef
    target_population_evidence_artifact: ArtifactRef

    def __init__(
        self,
        *,
        evidence: StorageBudgetEvidence,
        decision: StorageBudgetDecision,
        evidence_digest: str,
        evidence_reference: str,
        measured_audit_artifact: ArtifactRef,
        projection_evidence_artifact: ArtifactRef,
        backup_restore_evidence_artifact: ArtifactRef,
        target_population_evidence_artifact: ArtifactRef,
        _verification_token: object | None = None,
    ) -> None:
        if _verification_token is not _STORAGE_GATE_VERIFICATION_TOKEN:
            raise ValueError(
                "storage gate evidence must be built by verify_storage_gate_evidence"
            )
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "evidence_digest", evidence_digest)
        object.__setattr__(self, "evidence_reference", evidence_reference)
        object.__setattr__(self, "measured_audit_artifact", measured_audit_artifact)
        object.__setattr__(
            self, "projection_evidence_artifact", projection_evidence_artifact
        )
        object.__setattr__(
            self,
            "backup_restore_evidence_artifact",
            backup_restore_evidence_artifact,
        )
        object.__setattr__(
            self,
            "target_population_evidence_artifact",
            target_population_evidence_artifact,
        )
        self.__post_init__()

    def __post_init__(self) -> None:
        if _SHA256_PATTERN.fullmatch(self.evidence_digest) is None:
            raise ValueError("storage gate evidence digest must be SHA-256")
        if not self.evidence_reference.strip():
            raise ValueError("storage gate evidence reference must be non-empty")
        if storage_budget_evidence_digest(self.evidence) != self.evidence_digest:
            raise ValueError("storage gate evidence digest does not match")
        if assess_storage_budget(self.evidence) != self.decision:
            raise ValueError("storage gate decision does not match its evidence")
        pointers = (
            (
                self.measured_audit_artifact,
                self.evidence.measured_audit_digest,
                self.evidence.measured_audit_reference,
            ),
            (
                self.projection_evidence_artifact,
                self.evidence.projection_evidence_digest,
                self.evidence.projection_evidence_reference,
            ),
            (
                self.backup_restore_evidence_artifact,
                self.evidence.backup_restore_evidence_digest,
                self.evidence.backup_restore_evidence_reference,
            ),
            (
                self.target_population_evidence_artifact,
                self.evidence.target_population_evidence_digest,
                self.evidence.target_population_evidence_reference,
            ),
        )
        if any(
            artifact.sha256 != digest or artifact.uri != reference
            for artifact, digest, reference in pointers
        ):
            raise ValueError("storage gate artifacts do not match evidence pointers")

    @property
    def decision_digest(self) -> str:
        return self.decision.decision_digest


def _read_verified_artifact(
    store: ArtifactStore,
    reference: ArtifactRef,
) -> bytes:
    if not store.verify(reference):
        raise ValueError(
            f"storage evidence artifact failed verification: {reference.uri}"
        )
    stat = store.stat(reference)
    if stat.reference != reference or stat.stored_size_bytes != reference.size_bytes:
        raise ValueError("storage evidence artifact stat does not match its reference")
    with store.open(reference) as stream:
        payload = stream.read()
    if (
        len(payload) != reference.size_bytes
        or hashlib.sha256(payload).hexdigest() != reference.sha256
    ):
        raise ValueError("storage evidence artifact bytes failed verification")
    return payload


def verify_storage_gate_evidence(
    evidence: StorageBudgetEvidence,
    *,
    artifact_store: ArtifactStore,
    measured_audit_artifact: ArtifactRef,
    projection_evidence_artifact: ArtifactRef,
    backup_restore_evidence_artifact: ArtifactRef,
    target_population_evidence_artifact: ArtifactRef,
    evidence_reference: str,
) -> StorageGateEvidence:
    """Verify typed content-addressed evidence before authorization."""

    expected = (
        (
            measured_audit_artifact,
            evidence.measured_audit_digest,
            evidence.measured_audit_reference,
            measured_storage_audit_payload(evidence),
        ),
        (
            projection_evidence_artifact,
            evidence.projection_evidence_digest,
            evidence.projection_evidence_reference,
            storage_projection_payload(evidence),
        ),
        (
            backup_restore_evidence_artifact,
            evidence.backup_restore_evidence_digest,
            evidence.backup_restore_evidence_reference,
            backup_restore_evidence_payload(evidence),
        ),
        (
            target_population_evidence_artifact,
            evidence.target_population_evidence_digest,
            evidence.target_population_evidence_reference,
            target_population_evidence_payload(evidence),
        ),
    )
    for artifact, digest, reference, expected_payload in expected:
        if artifact.sha256 != digest or artifact.uri != reference:
            raise ValueError("storage artifact reference does not match gate evidence")
        if _read_verified_artifact(artifact_store, artifact) != expected_payload:
            raise ValueError(
                "storage artifact content does not match typed gate evidence"
            )
    decision = assess_storage_budget(evidence)
    return StorageGateEvidence(
        evidence=evidence,
        decision=decision,
        evidence_digest=storage_budget_evidence_digest(evidence),
        evidence_reference=evidence_reference,
        measured_audit_artifact=measured_audit_artifact,
        projection_evidence_artifact=projection_evidence_artifact,
        backup_restore_evidence_artifact=backup_restore_evidence_artifact,
        target_population_evidence_artifact=target_population_evidence_artifact,
        _verification_token=_STORAGE_GATE_VERIFICATION_TOKEN,
    )


@dataclass(frozen=True)
class FullPhysicsLoadDecision:
    """Independent conjunction of scientific and storage readiness gates."""

    status: Literal["authorized", "withheld"]
    joint_metric_gate_passed: bool
    storage_budget_gate_passed: bool
    storage_policy_version: str
    scientific_gate_evidence_digest: str
    scientific_gate_artifact_digest: str
    scientific_gate_decision_digest: str
    storage_gate_evidence_digest: str
    storage_budget_decision_digest: str
    reasons: tuple[str, ...]

    @property
    def may_start_full_load(self) -> bool:
        return self.status == "authorized"

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(asdict(self))


def estimate_linear_storage(
    *,
    measured_bytes: int,
    measured_papers: int,
    target_papers: int,
    fixed_bytes: int = 0,
) -> int:
    """Conservative integer linear estimate with an explicit fixed component."""

    for name, value in (
        ("measured_bytes", measured_bytes),
        ("measured_papers", measured_papers),
        ("target_papers", target_papers),
        ("fixed_bytes", fixed_bytes),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if measured_papers == 0:
        raise ValueError("measured_papers must be positive")
    if fixed_bytes > measured_bytes:
        raise ValueError("fixed_bytes cannot exceed measured_bytes")
    variable_bytes = measured_bytes - fixed_bytes
    return fixed_bytes + _ceil_ratio(variable_bytes, target_papers, measured_papers)


def assess_storage_budget(
    evidence: StorageBudgetEvidence,
    policy: StorageBudgetPolicy = STORAGE_BUDGET_POLICY_V1,
) -> StorageBudgetDecision:
    """Require representative, complete storage evidence and ample headroom."""

    reasons: list[str] = []
    capacity = evidence.capacity_bytes
    steady_limit = (
        capacity * policy.steady_state_limit_basis_points // 10_000
        if capacity is not None and capacity > 0
        else None
    )
    peak_limit = (
        capacity * policy.peak_limit_basis_points // 10_000
        if capacity is not None and capacity > 0
        else None
    )
    contingency_numerator = 10_000 + policy.contingency_basis_points
    conservative_steady = (
        _ceil_ratio(
            evidence.projected_steady_state_bytes, contingency_numerator, 10_000
        )
        if evidence.projected_steady_state_bytes is not None
        else None
    )
    conservative_peak = (
        _ceil_ratio(evidence.projected_peak_bytes, contingency_numerator, 10_000)
        if evidence.projected_peak_bytes is not None
        else None
    )

    if capacity is None or capacity <= 0:
        reasons.append("physical volume capacity is missing")
    if evidence.current_used_bytes is None:
        reasons.append("current physical volume use is missing")
    elif capacity is not None and evidence.current_used_bytes > capacity:
        reasons.append("current physical volume use exceeds reported capacity")
    if (
        evidence.measured_sample_papers is None
        or evidence.measured_sample_papers < policy.minimum_representative_papers
    ):
        reasons.append(
            "final-schema storage measurement covers fewer than "
            f"{policy.minimum_representative_papers} representative papers"
        )
    if evidence.measured_sample_bytes is None or evidence.measured_sample_bytes <= 0:
        reasons.append("measured final-schema sample byte footprint is missing")
    if evidence.measured_fixed_bytes is None:
        reasons.append("measured fixed storage component is missing")
    if evidence.measurement_environment_id is None or evidence.measured_at is None:
        reasons.append("measurement environment or timestamp is missing")
    if evidence.target_papers is None or evidence.target_papers <= 0:
        reasons.append("target canonical paper count is missing")
    elif (
        evidence.measured_sample_papers is not None
        and evidence.target_papers < evidence.measured_sample_papers
    ):
        reasons.append("target paper count is smaller than the representative sample")
    if (
        evidence.target_population_id is None
        or evidence.target_population_policy_version is None
        or evidence.target_population_cutoff is None
        or evidence.target_population_paper_ids_digest is None
    ):
        reasons.append("exact target population identity is missing")
    if evidence.projection_method_version != STORAGE_PROJECTION_METHOD_V1:
        reasons.append("storage projection method is missing or not the v1 method")
    if not evidence.representative_final_schema:
        reasons.append("measurement does not represent the final proposed schema")
    if not evidence.database_statistics_refreshed:
        reasons.append("final-schema database statistics have not been refreshed")
    if not evidence.peak_working_set_included:
        reasons.append("peak WAL and migration/index working storage are absent")
    if not evidence.certification_storage_included:
        reasons.append("certification storage is absent from the projection")
    if not evidence.citation_storage_included:
        reasons.append("citation storage is absent from the projection")
    if not evidence.cold_payloads_externalized:
        reasons.append("cold provider payloads are still projected in PostgreSQL")
    if not evidence.artifact_integrity_verified:
        reasons.append("external artifact checksum and retrieval are unverified")
    if not evidence.backup_restore_verified:
        reasons.append("backup and isolated restore evidence is missing")
    backup_fields = (
        evidence.backup_id,
        evidence.backup_digest,
        evidence.restore_target_id,
        evidence.restore_environment_id,
        evidence.restore_checks_digest,
        evidence.restore_completed_at,
        evidence.restore_reviewer_id,
    )
    if any(value is None for value in backup_fields):
        reasons.append("typed backup and isolated restore attestation is incomplete")
    if (
        evidence.measurement_environment_id is not None
        and evidence.restore_environment_id == evidence.measurement_environment_id
    ):
        reasons.append("restore verification did not use an isolated environment")
    if (
        evidence.measured_at is not None
        and evidence.restore_completed_at is not None
        and evidence.restore_completed_at < evidence.measured_at
    ):
        reasons.append("restore verification predates the measured final-schema sample")
    if (
        evidence.backup_restore_evidence_digest is None
        or evidence.backup_restore_evidence_reference is None
    ):
        reasons.append("checksum-bound backup/restore evidence is missing")
    if (
        evidence.measured_audit_digest is None
        or evidence.measured_audit_reference is None
    ):
        reasons.append("checksum-bound measured storage audit evidence is missing")
    if (
        evidence.projection_evidence_digest is None
        or evidence.projection_evidence_reference is None
    ):
        reasons.append("checksum-bound storage projection evidence is missing")
    if (
        evidence.target_population_evidence_digest is None
        or evidence.target_population_evidence_reference is None
    ):
        reasons.append("checksum-bound target population evidence is missing")
    if (
        evidence.measured_sample_bytes is not None
        and evidence.measured_sample_bytes > 0
        and evidence.measured_fixed_bytes is not None
        and evidence.measured_sample_papers is not None
        and evidence.measured_sample_papers > 0
        and evidence.target_papers is not None
        and evidence.target_papers >= evidence.measured_sample_papers
        and evidence.projected_steady_state_bytes is not None
    ):
        deterministic_floor = estimate_linear_storage(
            measured_bytes=evidence.measured_sample_bytes,
            measured_papers=evidence.measured_sample_papers,
            target_papers=evidence.target_papers,
            fixed_bytes=evidence.measured_fixed_bytes,
        )
        if evidence.projected_steady_state_bytes < deterministic_floor:
            reasons.append(
                "projected steady state is below the deterministic v1 estimate"
            )
    if conservative_steady is None:
        reasons.append("projected steady-state storage is missing")
    elif steady_limit is not None and conservative_steady > steady_limit:
        reasons.append("conservative steady-state projection exceeds 60% capacity")
    if conservative_peak is None:
        reasons.append("projected peak storage is missing")
    elif peak_limit is not None and conservative_peak > peak_limit:
        reasons.append("conservative peak projection exceeds 80% capacity")
    if (
        evidence.projected_steady_state_bytes is not None
        and evidence.projected_peak_bytes is not None
        and evidence.projected_peak_bytes < evidence.projected_steady_state_bytes
    ):
        reasons.append("projected peak storage is below projected steady state")
    if (
        evidence.current_used_bytes is not None
        and evidence.projected_steady_state_bytes is not None
        and evidence.projected_steady_state_bytes < evidence.current_used_bytes
    ):
        reasons.append("projected steady state is below current physical use")

    return StorageBudgetDecision(
        policy_version=policy.version,
        status="withheld" if reasons else "pass",
        steady_state_limit_bytes=steady_limit,
        peak_limit_bytes=peak_limit,
        conservative_steady_state_bytes=conservative_steady,
        conservative_peak_bytes=conservative_peak,
        input_evidence_digest=storage_budget_evidence_digest(evidence, policy),
        measured_audit_digest=evidence.measured_audit_digest,
        measured_audit_reference=evidence.measured_audit_reference,
        projection_evidence_digest=evidence.projection_evidence_digest,
        projection_evidence_reference=evidence.projection_evidence_reference,
        reasons=tuple(reasons),
    )


def assess_full_physics_load(
    *,
    scientific_gate: ScientificGateEvidence,
    storage_gate: StorageGateEvidence,
) -> FullPhysicsLoadDecision:
    """Authorize a load only when both independent gates genuinely pass."""

    if not isinstance(scientific_gate, ScientificGateEvidence):
        raise ValueError(
            "full-load assessment requires verified scientific gate evidence"
        )
    if not isinstance(storage_gate, StorageGateEvidence):
        raise ValueError("full-load assessment requires verified storage gate evidence")
    reasons: list[str] = []
    storage_budget = storage_gate.decision
    scientific_passed = (
        scientific_gate.decision.may_activate
        and scientific_gate.review.approved_for_full_load
    )
    if not scientific_passed:
        reasons.append("Scientific Evidence / Joint Metric Gate has not passed")
    if not storage_budget.may_start_full_load:
        reasons.append("Storage Budget Gate has not passed")
    if storage_budget.policy_version != STORAGE_BUDGET_POLICY_V1.version:
        reasons.append("Storage Budget Gate policy is not the current v1 policy")
    return FullPhysicsLoadDecision(
        status="withheld" if reasons else "authorized",
        joint_metric_gate_passed=scientific_passed,
        storage_budget_gate_passed=storage_budget.may_start_full_load,
        storage_policy_version=storage_budget.policy_version,
        scientific_gate_evidence_digest=scientific_gate.evidence_digest,
        scientific_gate_artifact_digest=scientific_gate.evidence_artifact.sha256,
        scientific_gate_decision_digest=scientific_gate.decision_digest,
        storage_gate_evidence_digest=storage_gate.evidence_digest,
        storage_budget_decision_digest=storage_budget.decision_digest,
        reasons=tuple(reasons),
    )
