"""Opt-in, record-level machine assessment of explicit provider evidence.

These rules do not impersonate human review or replace Metric System v1. They
reconstruct a result from compact, typed source facts; a caller cannot supply a
successful assessment flag. Verified acquisition/parser code must establish the
facts and source references upstream. A checksum binds content, not authenticity.

The existing reviewed contracts and their historical digests are unchanged.
These results alone do not certify complete years, populations, or activation.
"""

import calendar
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from ..connectors.base import normalize_external_id
from ..fields.mapping import (
    CrossProviderFieldLedger,
    ProviderCategoryEvidence,
    ProviderFieldProjection,
    reconcile_cross_provider_field_evidence,
)
from ..fields.ontology import PHYSICS_FIELD_ONTOLOGY_V1
from .contracts import (
    CertificationError,
    CertificationState,
    EvidenceCertificationDecision,
    EvidenceKind,
    EvidenceReference,
    canonical_digest,
)

AUTOMATIC_FIELD_RULE_VERSION = "exact-provider-field-assessment-v1"
AUTOMATIC_DATE_RULE_VERSION = "declared-date-basis-assessment-v1"
AUTOMATIC_RESEARCHER_RULE_VERSION = "paper-native-identifier-assessment-v1"

# A date's meaning comes from this explicit provider field, never its ordering
# relative to unrelated timestamps. Additional sources require a versioned rule.
_DATE_ORIGINS = {
    "arxiv-initial-submission": ("arxiv", "published"),
    "inspire-preprint-date": ("inspire", "preprint_date"),
    "journal-online-publication": ("crossref", "published-online"),
    "journal-print-publication": ("crossref", "published-print"),
}
_IDENTIFIER_FIELDS = {
    "orcid": frozenset({"authors[].ORCID", "authors[].orcid", "authors[].ids"}),
    "inspire-author": frozenset({"authors[].record", "authors[].recid"}),
}


@dataclass(frozen=True)
class AutomaticEvidenceContext:
    paper_id: str
    dataset_version: str
    acquisition_scope: str

    def __post_init__(self) -> None:
        if any(not value.strip() for value in self.__dict__.values()):
            raise ValueError("automatic assessment context must be non-empty")


@dataclass(frozen=True)
class AutomaticFieldEvidence:
    context: AutomaticEvidenceContext
    projections: tuple[ProviderFieldProjection, ...]
    references: tuple[EvidenceReference, ...]


@dataclass(frozen=True)
class ProviderDateFact:
    reference: EvidenceReference
    basis: str
    source_field: str
    value: str


@dataclass(frozen=True)
class AutomaticDateEvidence:
    context: AutomaticEvidenceContext
    declared_basis: str
    facts: tuple[ProviderDateFact, ...]


@dataclass(frozen=True)
class ResolvedDateBasis:
    basis: str
    exact_date: date | None
    precision: str | None
    earliest_possible: date | None
    latest_possible: date | None


@dataclass(frozen=True)
class ResearcherIdentifierFact:
    reference: EvidenceReference
    source_field: str
    scheme: str
    value: str


@dataclass(frozen=True)
class AutomaticResearcherEvidence:
    context: AutomaticEvidenceContext
    appearance_id: str
    facts: tuple[ResearcherIdentifierFact, ...]


@dataclass(frozen=True)
class ResolvedResearcherIdentifiers:
    """Co-asserted identifiers, not permission for name-based/global merging."""

    identifiers: tuple[tuple[str, str], ...]


type AutomaticEvidence = (
    AutomaticFieldEvidence | AutomaticDateEvidence | AutomaticResearcherEvidence
)
type AutomaticValue = (
    CrossProviderFieldLedger | ResolvedDateBasis | ResolvedResearcherIdentifiers
)


@dataclass(frozen=True)
class _Evaluation:
    state: CertificationState
    reasons: tuple[str, ...]
    value: AutomaticValue
    kind: EvidenceKind
    rule_version: str
    subject_type: str
    subject_id: str
    references: tuple[EvidenceReference, ...]


def _references(items: tuple[EvidenceReference, ...]) -> tuple[EvidenceReference, ...]:
    if any(not isinstance(item, EvidenceReference) for item in items):
        raise CertificationError("automatic evidence requires typed source references")
    if any(not item.source_snapshot_id for item in items):
        raise CertificationError(
            "automatic evidence requires a source snapshot identity"
        )
    return tuple(sorted(set(items), key=canonical_digest))


def _field_evaluation(evidence: AutomaticFieldEvidence) -> _Evaluation:
    references = _references(evidence.references)
    if not isinstance(evidence.projections, tuple) or any(
        not isinstance(item, ProviderFieldProjection) for item in evidence.projections
    ):
        raise CertificationError("automatic fields require typed provider projections")
    if any(
        item.provider not in {"inspire", "arxiv", "crossref"}
        or not isinstance(item.categories, tuple)
        or any(
            not isinstance(category, ProviderCategoryEvidence)
            or category.role not in {"primary", "secondary", "unspecified"}
            for category in item.categories
        )
        for item in evidence.projections
    ):
        raise CertificationError(
            "automatic field source or category contract is invalid"
        )
    projection_keys = [
        (item.provider, item.source_record_id, item.source_snapshot_id)
        for item in evidence.projections
    ]
    reference_keys = {
        (item.provider, item.source_record_id, item.source_snapshot_id)
        for item in references
    }
    if (
        len(set(projection_keys)) != len(projection_keys)
        or set(projection_keys) != reference_keys
        or any(not item.source_snapshot_id for item in references)
        or len(reference_keys) != len(references)
    ):
        raise CertificationError(
            "field projections do not bind exact source occurrences"
        )
    # The selected ledger cannot silently merge two revisions of one record.
    record_keys = [(provider, record) for provider, record, _ in projection_keys]
    if len(set(record_keys)) != len(record_keys):
        raise CertificationError("field evidence contains multiple selected revisions")
    ledger = reconcile_cross_provider_field_evidence(evidence.projections)
    total = math.fsum(item.weight for item in ledger.assignments)
    total += ledger.unmapped_field_mass
    reasons: tuple[str, ...] = ()
    state: CertificationState = "certified"
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        state, reasons = "conflicted", ("field-weight conservation failed",)
    elif not ledger.assignments or ledger.unmapped_field_mass > 0:
        state = "insufficient_evidence"
        reasons = ("selected provider classifications include absent or unmapped mass",)
    elif any(
        PHYSICS_FIELD_ONTOLOGY_V1.get(item.field_id).node_kind != "field"
        for item in ledger.assignments
    ):
        state = "insufficient_evidence"
        reasons = ("broad provider branches do not establish canonical leaf fields",)
    return _Evaluation(
        state,
        reasons,
        ledger,
        "field-classification",
        AUTOMATIC_FIELD_RULE_VERSION,
        "paper",
        evidence.context.paper_id,
        references,
    )


def _date_interval(value: str) -> tuple[date, date, str] | None:
    """Retain partial-date intervals; their lower bound is never an exact date."""
    try:
        if re.fullmatch(r"\d{4}", value):
            year = int(value)
            return date(year, 1, 1), date(year, 12, 31), "year"
        if re.fullmatch(r"\d{4}-\d{2}", value):
            year, month = (int(part) for part in value.split("-"))
            return (
                date(year, month, 1),
                date(year, month, calendar.monthrange(year, month)[1]),
                "month",
            )
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parsed = date.fromisoformat(value)
            return parsed, parsed, "day"
        if "T" in value:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                return None
            parsed = timestamp.astimezone(UTC).date()
            return parsed, parsed, "day"
    except ValueError:
        pass
    return None


def _date_evaluation(evidence: AutomaticDateEvidence) -> _Evaluation:
    if not isinstance(evidence.facts, tuple) or any(
        not isinstance(item, ProviderDateFact) for item in evidence.facts
    ):
        raise CertificationError("automatic dates require typed provider date facts")
    references = _references(tuple(item.reference for item in evidence.facts))
    basis = evidence.declared_basis
    result = ResolvedDateBasis(basis, None, None, None, None)
    selected = tuple(item for item in evidence.facts if item.basis == basis)
    state: CertificationState = "insufficient_evidence"
    reasons: tuple[str, ...] = (
        "declared date basis has no supported exact source evidence",
    )
    origin = _DATE_ORIGINS.get(basis)
    if origin is not None and selected:
        intervals = []
        for fact in selected:
            if (fact.reference.provider, fact.source_field) != origin:
                break
            interval = _date_interval(fact.value)
            if interval is None:
                break
            intervals.append(interval)
        if len(intervals) == len(selected):
            earliest = max(item[0] for item in intervals)
            latest = min(item[1] for item in intervals)
            if earliest > latest:
                state = "conflicted"
                reasons = ("source dates contradict the same declared date basis",)
            else:
                exact = any(item[2] == "day" for item in intervals)
                precision = "year"
                if exact:
                    precision = "day"
                elif any(item[2] == "month" for item in intervals):
                    precision = "month"
                result = ResolvedDateBasis(
                    basis, earliest if exact else None, precision, earliest, latest
                )
                if exact:
                    state, reasons = "certified", ()
                else:
                    reasons = ("partial date retained; exact metric date is missing",)
    return _Evaluation(
        state,
        reasons,
        result,
        "publication-metric-date",
        AUTOMATIC_DATE_RULE_VERSION,
        "paper",
        evidence.context.paper_id,
        references,
    )


def _researcher_evaluation(evidence: AutomaticResearcherEvidence) -> _Evaluation:
    if not evidence.appearance_id.strip():
        raise CertificationError(
            "researcher assessment requires an authorship identity"
        )
    if not isinstance(evidence.facts, tuple) or any(
        not isinstance(item, ResearcherIdentifierFact) for item in evidence.facts
    ):
        raise CertificationError(
            "automatic identities require typed paper-native facts"
        )
    references = _references(tuple(item.reference for item in evidence.facts))
    identifiers: set[tuple[str, str]] = set()
    invalid = False
    for fact in evidence.facts:
        if (
            fact.reference.provider != "inspire"
            or fact.source_field not in _IDENTIFIER_FIELDS.get(fact.scheme, ())
        ):
            invalid = True
            continue
        normalized = normalize_external_id(fact.scheme, fact.value)
        if normalized is None or (
            normalized[0] == "inspire-author"
            and (not normalized[1].isdigit() or int(normalized[1]) < 1)
        ):
            invalid = True
            continue
        identifiers.add(normalized)
    state: CertificationState = "certified"
    reasons: tuple[str, ...] = ()
    if any(
        len({value for candidate, value in identifiers if candidate == scheme}) > 1
        for scheme in _IDENTIFIER_FIELDS
    ):
        state, reasons = "conflicted", ("paper-native authority identifiers conflict",)
    elif invalid or not identifiers:
        state = "insufficient_evidence"
        reasons = ("missing, invalid or unsupported paper-native authority identifier",)
    return _Evaluation(
        state,
        reasons,
        ResolvedResearcherIdentifiers(tuple(sorted(identifiers))),
        "researcher-identity",
        AUTOMATIC_RESEARCHER_RULE_VERSION,
        "authorship-appearance",
        evidence.appearance_id,
        references,
    )


def _evaluate(evidence: AutomaticEvidence) -> _Evaluation:
    if not isinstance(
        evidence,
        (AutomaticFieldEvidence, AutomaticDateEvidence, AutomaticResearcherEvidence),
    ):
        raise CertificationError("unsupported automatic evidence contract")
    if not isinstance(evidence.context, AutomaticEvidenceContext):
        raise CertificationError("automatic evidence requires a typed context")
    if isinstance(evidence, AutomaticFieldEvidence):
        return _field_evaluation(evidence)
    if isinstance(evidence, AutomaticDateEvidence):
        return _date_evaluation(evidence)
    if isinstance(evidence, AutomaticResearcherEvidence):
        return _researcher_evaluation(evidence)
    raise CertificationError("unsupported automatic evidence contract")


@dataclass(frozen=True)
class AutomaticCertification:
    """A reconstructable assessment: status/value are derived, never supplied.

    The evidence is retained in this in-memory object. Production persistence
    should retain necessary compact facts, input/output digests and references,
    not a second full deterministic decision ledger.
    """

    evidence: AutomaticEvidence

    def __post_init__(self) -> None:
        _evaluate(self.evidence)

    @property
    def input_digest(self) -> str:
        return canonical_digest(self.evidence)

    @property
    def value(self) -> AutomaticValue:
        return _evaluate(self.evidence).value

    @property
    def decision(self) -> EvidenceCertificationDecision:
        evaluation = _evaluate(self.evidence)
        return EvidenceCertificationDecision(
            subject_type=evaluation.subject_type,
            subject_id=evaluation.subject_id,
            evidence_kind=evaluation.kind,
            state=evaluation.state,
            rule_version=evaluation.rule_version,
            dataset_version=self.evidence.context.dataset_version,
            acquisition_scope=self.evidence.context.acquisition_scope,
            evidence=evaluation.references,
            certified_value_digest=(
                canonical_digest((self.input_digest, evaluation.value))
                if evaluation.state == "certified"
                else None
            ),
            reasons=evaluation.reasons,
        )


def verify_automatic_decision(
    evidence: AutomaticEvidence,
    decision: EvidenceCertificationDecision,
) -> bool:
    """Re-run the exact rule; a matching digest or supplied status is insufficient."""
    return AutomaticCertification(evidence).decision == decision
