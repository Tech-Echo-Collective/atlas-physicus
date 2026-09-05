import math
from dataclasses import dataclass
from datetime import datetime

from ..fields import (
    FIELD_WEIGHTING_POLICY_VERSION,
    PHYSICS_FIELD_ONTOLOGY_V1,
    PHYSICS_FIELD_ONTOLOGY_VERSION,
    PROVIDER_FIELD_MAPPING_VERSION,
)
from .contracts import CertificationState

FIELD_CERTIFICATION_RULE_VERSION = "reviewed-field-ledger-certification-v1"
FIELD_CONSERVATION_TOLERANCE = 1e-9


@dataclass(frozen=True)
class FieldWeight:
    field_id: str
    weight: float

    def __post_init__(self) -> None:
        if not self.field_id.strip():
            raise ValueError("field id must be non-empty")
        if not math.isfinite(self.weight) or self.weight <= 0 or self.weight > 1:
            raise ValueError("field weight must be finite and within (0,1]")


@dataclass(frozen=True)
class FieldLedgerEvidence:
    paper_id: str
    assignments: tuple[FieldWeight, ...]
    unmapped_mass: float
    review_state: str
    ontology_version: str
    mapping_policy_version: str
    weighting_policy_version: str
    source_evidence_ids: tuple[str, ...]
    source_manifest_digest: str
    provider_disagreement: bool = False
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_confidence: float | None = None

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.paper_id,
                self.review_state,
                self.ontology_version,
                self.mapping_policy_version,
                self.weighting_policy_version,
            )
        ):
            raise ValueError("field ledger identifiers must be non-empty")
        if not math.isfinite(self.unmapped_mass) or not 0 <= self.unmapped_mass <= 1:
            raise ValueError("unmapped field mass must be finite and within [0,1]")
        field_ids = [item.field_id for item in self.assignments]
        if len(set(field_ids)) != len(field_ids):
            raise ValueError("a field ledger may contain each canonical field once")
        if not self.source_evidence_ids or len(set(self.source_evidence_ids)) != len(
            self.source_evidence_ids
        ):
            raise ValueError("field source evidence ids must be non-empty and unique")
        if len(self.source_manifest_digest) != 64:
            raise ValueError("field source manifest digest must be SHA-256")
        try:
            int(self.source_manifest_digest, 16)
        except ValueError as error:
            raise ValueError(
                "field source manifest digest must be hexadecimal"
            ) from error
        if (self.reviewed_by is None) != (self.reviewed_at is None):
            raise ValueError("field reviewer and review timestamp must be paired")
        if self.reviewed_at is not None and (
            self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None
        ):
            raise ValueError("field review timestamp must include a timezone")
        if self.review_confidence is not None and (
            not math.isfinite(self.review_confidence)
            or not 0 <= self.review_confidence <= 1
        ):
            raise ValueError("field review confidence must be within [0,1]")

    @property
    def conservation_total(self) -> float:
        return math.fsum(item.weight for item in self.assignments) + self.unmapped_mass


@dataclass(frozen=True)
class FieldCertificationResult:
    evidence: FieldLedgerEvidence
    paper_id: str
    state: CertificationState
    assignments: tuple[FieldWeight, ...]
    unmapped_mass: float
    conservation_total: float
    source_evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    rule_version: str = FIELD_CERTIFICATION_RULE_VERSION


def certify_field_ledger(ledger: FieldLedgerEvidence) -> FieldCertificationResult:
    """Certify a reviewed ledger without interpreting mapping as human review."""

    reasons: list[str] = []
    state: CertificationState = "certified"
    if (
        ledger.ontology_version != PHYSICS_FIELD_ONTOLOGY_VERSION
        or ledger.mapping_policy_version != PROVIDER_FIELD_MAPPING_VERSION
        or ledger.weighting_policy_version != FIELD_WEIGHTING_POLICY_VERSION
    ):
        state = "conflicted"
        reasons.append("field ledger uses an unapproved ontology or policy version")
    elif any(
        not PHYSICS_FIELD_ONTOLOGY_V1.contains(item.field_id)
        or PHYSICS_FIELD_ONTOLOGY_V1.get(item.field_id).node_kind != "field"
        for item in ledger.assignments
    ):
        state = "conflicted"
        reasons.append("field ledger contains a field outside the approved ontology")
    elif not math.isclose(
        ledger.conservation_total,
        1.0,
        rel_tol=0.0,
        abs_tol=FIELD_CONSERVATION_TOLERANCE,
    ):
        state = "conflicted"
        reasons.append("mapped and explicit unmapped field mass do not total one")
    elif ledger.review_state == "reviewed-approved" and (
        ledger.reviewed_by is None or ledger.reviewed_at is None
    ):
        state = "needs_review"
        reasons.append("field review lacks reviewer identity or review timestamp")
    elif ledger.provider_disagreement and ledger.review_state != "reviewed-approved":
        state = "needs_review"
        reasons.append("cross-provider field disagreement has not been reviewed")
    elif ledger.review_state != "reviewed-approved":
        state = "needs_review"
        reasons.append(
            "provider mapping exists but the selected field ledger is unreviewed"
        )
    elif not ledger.assignments:
        state = "insufficient_evidence"
        reasons.append("the reviewed ledger contains no mapped canonical field mass")

    return FieldCertificationResult(
        evidence=ledger,
        paper_id=ledger.paper_id,
        state=state,
        assignments=ledger.assignments,
        unmapped_mass=ledger.unmapped_mass,
        conservation_total=ledger.conservation_total,
        source_evidence_ids=ledger.source_evidence_ids,
        reasons=tuple(reasons),
    )
