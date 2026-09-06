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
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime

from ..connectors.base import SourceRecord, normalize_external_id
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


@dataclass(frozen=True)
class SourceBoundPaperFacts:
    """Compact facts extracted at the existing verified source-record boundary.

    The original record checksum and occurrence remain linked, while only date
    and paper-native identity facts are retained. Checksums bind supplied source
    content; provider authenticity remains the transport/parser responsibility.
    """

    context: AutomaticEvidenceContext
    reference: EvidenceReference
    declared_date_basis: str
    date_facts: tuple[ProviderDateFact, ...]
    author_count: int | None
    authors: tuple[AutomaticResearcherEvidence, ...]
    extraction_version: str = "source-bound-paper-facts-v1"
    researcher_namespace: str = "inspire-author"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, AutomaticEvidenceContext)
            or not isinstance(self.reference, EvidenceReference)
            or not self.reference.source_snapshot_id
            or self.reference.provider not in {"inspire", "arxiv"}
            or self.extraction_version != "source-bound-paper-facts-v1"
            or self.researcher_namespace != "inspire-author"
            or not isinstance(self.date_facts, tuple)
            or any(not isinstance(item, ProviderDateFact) for item in self.date_facts)
            or any(item.reference != self.reference for item in self.date_facts)
            or not isinstance(self.authors, tuple)
            or any(
                not isinstance(item, AutomaticResearcherEvidence)
                for item in self.authors
            )
        ):
            raise CertificationError(
                "source-bound paper facts have invalid lineage or version"
            )
        expected_origin = _DATE_ORIGINS.get(self.declared_date_basis)
        if expected_origin is None or expected_origin[0] != self.reference.provider:
            raise CertificationError(
                "declared metric date basis does not match the source"
            )
        if self.author_count is None:
            if self.authors:
                raise CertificationError(
                    "missing author inventory cannot contain selected authors"
                )
        elif (
            not isinstance(self.author_count, int)
            or isinstance(self.author_count, bool)
            or self.author_count < 0
            or self.author_count != len(self.authors)
        ):
            raise CertificationError("paper-native author inventory is incomplete")
        for position, author in enumerate(self.authors):
            if (
                author.context != self.context
                or author.appearance_id
                != f"{self.reference.source_record_id}:author:{position}"
                or any(item.reference != self.reference for item in author.facts)
            ):
                raise CertificationError(
                    "paper-native author inventory differs from source positions"
                )
        _ = self.date_assessment
        _ = self.researcher_assessments

    @property
    def date_assessment(self) -> AutomaticCertification:
        return AutomaticCertification(
            AutomaticDateEvidence(
                self.context,
                self.declared_date_basis,
                self.date_facts,
            )
        )

    @property
    def exact_date(self) -> date | None:
        value = self.date_assessment.value
        assert isinstance(value, ResolvedDateBasis)
        return value.exact_date

    @property
    def researcher_assessments(self) -> tuple[AutomaticCertification, ...]:
        return tuple(AutomaticCertification(item) for item in self.authors)

    @property
    def researcher_ids(self) -> tuple[str, ...]:
        """Fixed native namespace, never a name/ORCID fallback or a global merge."""
        result = []
        for assessment in self.researcher_assessments:
            value = assessment.value
            assert isinstance(value, ResolvedResearcherIdentifiers)
            selected = [
                identifier
                for scheme, identifier in value.identifiers
                if scheme == self.researcher_namespace
            ]
            if assessment.decision.state != "certified" or len(selected) != 1:
                continue
            result.append(f"{self.researcher_namespace}:{selected[0]}")
        return tuple(sorted(result))


def capture_automatic_paper_facts(
    record: SourceRecord,
    *,
    context: AutomaticEvidenceContext,
    reference: EvidenceReference,
    declared_date_basis: str,
) -> SourceBoundPaperFacts:
    """Extract compact facts from an exact record returned by the existing parser.

    No transport is invoked. The caller supplies the immutable occurrence from
    its validated page inventory; mismatching metadata, ID or hash is rejected.
    """
    if (
        not isinstance(record, SourceRecord)
        or not isinstance(reference, EvidenceReference)
        or record.provider != reference.provider
        or record.source_record_id != reference.source_record_id
        or record.checksum != reference.checksum
    ):
        raise CertificationError(
            "automatic facts do not match the parsed source record checksum"
        )
    origin = _DATE_ORIGINS.get(declared_date_basis)
    if origin is None or origin[0] != record.provider:
        raise CertificationError(
            "automatic source extraction requires an explicit supported date basis"
        )
    raw_date = record.raw.get(origin[1])
    dates = (
        (ProviderDateFact(reference, declared_date_basis, origin[1], raw_date),)
        if isinstance(raw_date, str)
        else ()
    )
    raw_authors = record.raw.get("authors") if record.provider == "inspire" else None
    authors = []
    if isinstance(raw_authors, list):
        for position, author in enumerate(raw_authors):
            if not isinstance(author, dict):
                raise CertificationError(
                    "paper-native author inventory contains a malformed author"
                )
            facts: list[ResearcherIdentifierFact] = []
            candidates: list[tuple[str, str, object]] = []
            for key in ("ORCID", "orcid"):
                if key in author:
                    candidates.append((f"authors[].{key}", "orcid", author[key]))
            if "record" in author:
                target = author["record"]
                if isinstance(target, dict):
                    target = target.get("$ref")
                candidates.append(("authors[].record", "inspire-author", target))
            if "recid" in author:
                candidates.append(
                    ("authors[].recid", "inspire-author", author["recid"])
                )
            identifiers = author.get("ids", [])
            if not isinstance(identifiers, list):
                raise CertificationError(
                    "paper-native author identifiers are malformed"
                )
            for item in identifiers:
                if not isinstance(item, dict):
                    raise CertificationError(
                        "paper-native author identifier is malformed"
                    )
                scheme = str(item.get("schema") or item.get("scheme") or "").casefold()
                if scheme == "orcid":
                    candidates.append(("authors[].ids", "orcid", item.get("value")))
            for source_field, scheme, value in candidates:
                # Retain invalid assertions as invalid evidence; never silently
                # drop a conflicting/invalid ID to certify the remaining one.
                text_value = (
                    str(value)
                    if isinstance(value, (str, int)) and not isinstance(value, bool)
                    else ""
                )
                facts.append(
                    ResearcherIdentifierFact(
                        reference, source_field, scheme, text_value
                    )
                )
            authors.append(
                AutomaticResearcherEvidence(
                    context,
                    f"{reference.source_record_id}:author:{position}",
                    tuple(facts),
                )
            )
    return SourceBoundPaperFacts(
        context,
        reference,
        declared_date_basis,
        dates,
        len(raw_authors) if isinstance(raw_authors, list) else None,
        tuple(authors),
    )


def _paper_identity_decision_value(
    facts: SourceBoundPaperFacts,
    kind: EvidenceKind,
) -> tuple[CertificationState, tuple[str, ...], object, str]:
    facts.__post_init__()
    if kind == "publication-metric-date":
        decision = facts.date_assessment.decision
        return (
            decision.state,
            decision.reasons,
            {
                "paper_id": facts.context.paper_id,
                "publication_date": facts.exact_date,
            },
            AUTOMATIC_DATE_RULE_VERSION,
        )
    if kind != "researcher-identity":
        raise CertificationError(
            "automatic paper identity supports only dates and researcher identity"
        )
    assessments = facts.researcher_assessments
    ids = facts.researcher_ids
    state: CertificationState = "certified"
    reasons: tuple[str, ...] = ()
    if any(item.decision.state == "conflicted" for item in assessments) or len(
        set(ids)
    ) != len(ids):
        state, reasons = (
            "conflicted",
            ("paper-native identities conflict or repeat across author positions",),
        )
    elif not assessments or facts.author_count != len(ids):
        state, reasons = (
            "insufficient_evidence",
            ("complete paper-native INSPIRE author identities are unavailable",),
        )
    # A co-asserted ORCID cannot identify two different native author IDs.
    native_by_orcid: dict[str, set[str]] = {}
    for assessment in assessments:
        value = assessment.value
        assert isinstance(value, ResolvedResearcherIdentifiers)
        identifiers = dict(value.identifiers)
        if "orcid" in identifiers and "inspire-author" in identifiers:
            native_by_orcid.setdefault(identifiers["orcid"], set()).add(
                identifiers["inspire-author"]
            )
    if any(len(values) > 1 for values in native_by_orcid.values()):
        state, reasons = (
            "conflicted",
            ("one ORCID conflicts with multiple paper-native researcher identities",),
        )
    return (
        state,
        reasons,
        {
            "paper_id": facts.context.paper_id,
            "researcher_ids": ids,
        },
        AUTOMATIC_RESEARCHER_RULE_VERSION,
    )


@dataclass(frozen=True, kw_only=True)
class AutomaticPaperIdentityDecision(EvidenceCertificationDecision):
    source_facts: SourceBoundPaperFacts

    def __post_init__(self) -> None:
        EvidenceCertificationDecision.__post_init__(self)
        expected = _automatic_paper_identity_view(self.source_facts, self.evidence_kind)
        if any(
            getattr(self, item.name) != getattr(expected, item.name)
            for item in fields(EvidenceCertificationDecision)
        ):
            raise CertificationError(
                "automatic paper identity does not reconstruct "
                "its consumed source evidence"
            )


def _automatic_paper_identity_view(
    facts: SourceBoundPaperFacts,
    kind: EvidenceKind,
) -> EvidenceCertificationDecision:
    if not isinstance(facts, SourceBoundPaperFacts):
        raise CertificationError(
            "automatic paper admission requires source-bound facts"
        )
    state, reasons, value, version = _paper_identity_decision_value(facts, kind)
    return EvidenceCertificationDecision(
        subject_type="paper",
        subject_id=facts.context.paper_id,
        evidence_kind=kind,
        state=state,
        rule_version=version,
        dataset_version=facts.context.dataset_version,
        acquisition_scope=facts.context.acquisition_scope,
        evidence=(facts.reference,),
        certified_value_digest=canonical_digest(value),
        reasons=reasons,
    )


def automatic_paper_identity_decision(
    facts: SourceBoundPaperFacts,
    *,
    evidence_kind: EvidenceKind,
) -> AutomaticPaperIdentityDecision:
    view = _automatic_paper_identity_view(facts, evidence_kind)
    return AutomaticPaperIdentityDecision(
        **{
            item.name: getattr(view, item.name)
            for item in fields(EvidenceCertificationDecision)
        },
        source_facts=facts,
    )


def verify_automatic_source_binding(
    decision: EvidenceCertificationDecision,
    projection: object,
) -> None:
    """Bind opt-in decision to its canonical year's exact source occurrence.

    Physical storage locations may change; the provider/record/snapshot/content
    identity may not. Legacy reviewed decisions retain their existing contract.
    """
    if not isinstance(decision, AutomaticPaperIdentityDecision):
        return
    decision.__post_init__()
    facts = decision.source_facts
    references = getattr(projection, "occurrence_references", ())
    if getattr(
        projection, "paper_id", None
    ) != facts.context.paper_id or _source_identity(facts.reference) not in {
        _source_identity(item)
        for item in references
        if isinstance(item, EvidenceReference)
    }:
        raise CertificationError(
            "automatic identity evidence is outside "
            "the certified source occurrence inventory"
        )
    if (
        decision.evidence_kind == "publication-metric-date"
        and facts.exact_date != getattr(projection, "publication_date", None)
    ):
        raise CertificationError(
            "automatic date differs from the certified source-year date"
        )


def _source_identity(reference: EvidenceReference) -> tuple[str, str, str | None, str]:
    return (
        reference.provider,
        reference.source_record_id,
        reference.source_snapshot_id,
        reference.checksum,
    )


def verify_automatic_date_axis(
    decisions: tuple[EvidenceCertificationDecision, ...],
    source_years: tuple[object, ...],
) -> None:
    """An automatic metric time axis must cover the complete source window."""
    metric_dates = tuple(
        item
        for item in decisions
        if item.subject_type == "paper"
        and item.evidence_kind == "publication-metric-date"
    )
    if not any(
        isinstance(item, AutomaticPaperIdentityDecision) for item in metric_dates
    ):
        return
    source_dates = tuple(
        item
        for year in source_years
        for item in getattr(getattr(year, "evidence", None), "structural_decisions", ())
        if isinstance(item, EvidenceCertificationDecision)
        and item.evidence_kind == "publication-metric-date"
    )
    combined = (*metric_dates, *source_dates)
    if not source_dates or any(
        not isinstance(item, AutomaticPaperIdentityDecision) for item in combined
    ):
        raise CertificationError(
            "automatic metric dates require an explicitly based complete source window"
        )
    bases = {
        item.source_facts.declared_date_basis
        for item in combined
        if isinstance(item, AutomaticPaperIdentityDecision)
    }
    if len(bases) != 1:
        raise CertificationError("automatic metric dates mix incompatible source bases")
