import math
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Literal

from ..fields import (
    FIELD_WEIGHTING_POLICY_VERSION,
    PHYSICS_FIELD_ONTOLOGY_V1,
    PHYSICS_FIELD_ONTOLOGY_VERSION,
    PROVIDER_FIELD_MAPPING_VERSION,
)
from .automation import (
    AUTOMATIC_FIELD_RULE_VERSION,
    AutomaticCertification,
    AutomaticFieldEvidence,
)
from .contracts import (
    CertificationError,
    CertificationState,
    EvidenceCertificationDecision,
    EvidenceKind,
    canonical_digest,
)

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


def _automatic_ledger_view(evidence: AutomaticFieldEvidence) -> FieldLedgerEvidence:
    from ..fields.mapping import CrossProviderFieldLedger

    assessment = AutomaticCertification(evidence)
    value = assessment.value
    if not isinstance(value, CrossProviderFieldLedger):
        raise CertificationError("automatic field assessment requires field evidence")
    provider_fields: dict[str, set[str]] = {}
    for category in value.category_mappings:
        provider_fields.setdefault(category.provider, set()).update(
            category.atlas_field_ids
        )
    return FieldLedgerEvidence(
        paper_id=evidence.context.paper_id,
        assignments=tuple(
            FieldWeight(item.field_id, item.weight) for item in value.assignments
        ),
        unmapped_mass=value.unmapped_field_mass,
        review_state="machine-assessed",
        ontology_version=value.ontology_version,
        mapping_policy_version=value.mapping_version,
        weighting_policy_version=value.weighting_policy_version,
        source_evidence_ids=tuple(
            sorted(
                f"{item.provider}:{item.source_record_id}"
                for item in evidence.references
            )
        ),
        source_manifest_digest=assessment.input_digest,
        provider_disagreement=len(
            {tuple(sorted(items)) for items in provider_fields.values()}
        )
        > 1,
    )


@dataclass(frozen=True, kw_only=True)
class AutomaticFieldLedgerEvidence(FieldLedgerEvidence):
    """Opt-in derived ledger; the legacy reviewed type and its digest stay intact."""

    automatic_evidence: AutomaticFieldEvidence

    def __post_init__(self) -> None:
        FieldLedgerEvidence.__post_init__(self)
        expected = _automatic_ledger_view(self.automatic_evidence)
        if any(
            getattr(self, item.name) != getattr(expected, item.name)
            for item in fields(FieldLedgerEvidence)
        ):
            raise CertificationError(
                "automatic field ledger differs from exact provider evidence"
            )


def automatic_field_ledger(
    evidence: AutomaticFieldEvidence,
) -> AutomaticFieldLedgerEvidence:
    value = _automatic_ledger_view(evidence)
    return AutomaticFieldLedgerEvidence(
        paper_id=value.paper_id,
        assignments=value.assignments,
        unmapped_mass=value.unmapped_mass,
        review_state=value.review_state,
        ontology_version=value.ontology_version,
        mapping_policy_version=value.mapping_policy_version,
        weighting_policy_version=value.weighting_policy_version,
        source_evidence_ids=value.source_evidence_ids,
        source_manifest_digest=value.source_manifest_digest,
        provider_disagreement=value.provider_disagreement,
        automatic_evidence=evidence,
    )


def certify_field_ledger(ledger: FieldLedgerEvidence) -> FieldCertificationResult:
    """Certify a reviewed ledger without interpreting mapping as human review."""

    if isinstance(ledger, AutomaticFieldLedgerEvidence):
        ledger.__post_init__()
        assessment = AutomaticCertification(ledger.automatic_evidence)
        return FieldCertificationResult(
            evidence=ledger,
            paper_id=ledger.paper_id,
            state=assessment.decision.state,
            assignments=ledger.assignments,
            unmapped_mass=ledger.unmapped_mass,
            conservation_total=ledger.conservation_total,
            source_evidence_ids=ledger.source_evidence_ids,
            reasons=assessment.decision.reasons,
            rule_version=AUTOMATIC_FIELD_RULE_VERSION,
        )
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


@dataclass(frozen=True)
class AutomaticFieldBinding:
    """Exact consumer projection, distinct from the raw provider ledger."""

    purpose: Literal["source-year-ledger", "coverage", "metric-paper"]
    field_id: str | None = None
    entity_attribution_weight: float | None = None
    include_category_weights: bool = False


def _automatic_field_value(
    ledger: AutomaticFieldLedgerEvidence,
    binding: AutomaticFieldBinding,
) -> object:
    if binding.purpose in {"source-year-ledger", "coverage"}:
        if (
            binding.field_id is not None
            or binding.entity_attribution_weight is not None
            or binding.include_category_weights
        ):
            raise CertificationError(
                "source-ledger binding cannot carry metric field overrides"
            )
        return {
            "paper_id": ledger.paper_id,
            "field_weights": tuple(
                sorted((item.field_id, item.weight) for item in ledger.assignments)
            ),
            "unmapped_field_mass": ledger.unmapped_mass,
            "field_weight_total": ledger.conservation_total,
            "field_weighting_policy_version": ledger.weighting_policy_version,
        }
    if binding.purpose != "metric-paper":
        raise CertificationError("unsupported automatic field binding purpose")
    weights = {item.field_id: item.weight for item in ledger.assignments}
    share = binding.entity_attribution_weight
    field_id = binding.field_id
    if (
        field_id is None
        or field_id not in weights
        or share is None
        or not math.isfinite(share)
        or not 0 <= share <= 1
    ):
        raise CertificationError(
            "automatic metric field binding lacks an exact supported share"
        )
    return {
        "paper_id": ledger.paper_id,
        "field_id": field_id,
        "attribution_weight": share * weights[field_id],
        "category_weights": tuple(sorted(weights.items()))
        if binding.include_category_weights
        else (),
    }


@dataclass(frozen=True, kw_only=True)
class AutomaticFieldDecision(EvidenceCertificationDecision):
    """Known automatic rule with reconstructable evidence and consumed-value binding."""

    automatic_field_evidence: AutomaticFieldEvidence
    field_binding: AutomaticFieldBinding

    def __post_init__(self) -> None:
        EvidenceCertificationDecision.__post_init__(self)
        ledger = automatic_field_ledger(self.automatic_field_evidence)
        assessment = AutomaticCertification(self.automatic_field_evidence)
        expected_type = (
            "coverage-unit" if self.field_binding.purpose == "coverage" else "paper"
        )
        allowed_kinds: set[EvidenceKind] = {
            "field-classification",
            "field-weight-conservation",
        }
        if self.field_binding.purpose == "source-year-ledger":
            allowed_kinds = {"field-weight-conservation"}
        elif self.field_binding.purpose == "coverage":
            allowed_kinds = {"field-classification"}
        context = self.automatic_field_evidence.context
        if (
            self.subject_type != expected_type
            or self.subject_id != context.paper_id
            or self.evidence_kind not in allowed_kinds
            or self.rule_version != AUTOMATIC_FIELD_RULE_VERSION
            or self.dataset_version != context.dataset_version
            or self.acquisition_scope != context.acquisition_scope
            or self.state != assessment.decision.state
            or self.reasons != assessment.decision.reasons
            or self.evidence != assessment.decision.evidence
            or self.reviewed_by is not None
            or self.reviewed_at is not None
            or self.supersedes_decision_id is not None
            or self.certified_value_digest
            != canonical_digest(_automatic_field_value(ledger, self.field_binding))
        ):
            raise CertificationError(
                "automatic field decision does not reconstruct its consumed evidence"
            )


def automatic_field_decision(
    evidence: AutomaticFieldEvidence,
    *,
    binding: AutomaticFieldBinding,
    evidence_kind: EvidenceKind,
) -> AutomaticFieldDecision:
    ledger = automatic_field_ledger(evidence)
    assessment = AutomaticCertification(evidence)
    return AutomaticFieldDecision(
        subject_type="coverage-unit" if binding.purpose == "coverage" else "paper",
        subject_id=evidence.context.paper_id,
        evidence_kind=evidence_kind,
        state=assessment.decision.state,
        rule_version=AUTOMATIC_FIELD_RULE_VERSION,
        dataset_version=evidence.context.dataset_version,
        acquisition_scope=evidence.context.acquisition_scope,
        evidence=assessment.decision.evidence,
        certified_value_digest=canonical_digest(
            _automatic_field_value(ledger, binding)
        ),
        reasons=assessment.decision.reasons,
        automatic_field_evidence=evidence,
        field_binding=binding,
    )
