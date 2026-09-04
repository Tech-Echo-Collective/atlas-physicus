"""Pure, deterministic canonical-paper planning for historical replay.

The planner in this module has no database, provider-transport, cursor, or
metric side effects.  It turns immutable provider occurrences into a
content-addressed merge plan that a later staging writer can apply.  In
particular, it preserves bibliographic date evidence but deliberately does not
select one canonical publication date or cohort field.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from .connectors.base import normalize_external_id

StrongIdentifierScheme = Literal["doi", "arxiv", "inspire"]
DatePrecision = Literal["year", "month", "day"]
MergeStatus = Literal["matched", "needs_review"]

CANONICAL_PAPER_MERGE_POLICY_VERSION = "canonical-paper-merge-policy-v1"
PAPER_MERGE_PLAN_VERSION = "historical-paper-merge-plan-v1"
_SCHEME_PRECEDENCE: tuple[StrongIdentifierScheme, ...] = (
    "doi",
    "arxiv",
    "inspire",
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _safe_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized[:96] or "record"


def _normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).replace("&", " and ")
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(
        re.sub(r"[^\w]+", " ", without_marks.casefold(), flags=re.UNICODE).split()
    )


def _normalized_author(value: str) -> str:
    """Normalize one name without treating it as a researcher resolution."""

    tokens = _normalized_text(value).split()
    return " ".join(sorted(tokens))


def _validate_date(value: str, precision: DatePrecision) -> None:
    patterns: dict[DatePrecision, str] = {
        "year": r"\d{4}",
        "month": r"\d{4}-\d{2}",
        "day": r"\d{4}-\d{2}-\d{2}",
    }
    if re.fullmatch(patterns[precision], value) is None:
        raise ValueError(f"date value {value!r} does not have {precision} precision")
    expanded = value + (
        "-01-01" if precision == "year" else "-01" if precision == "month" else ""
    )
    try:
        date.fromisoformat(expanded)
    except ValueError as error:
        raise ValueError(f"date value {value!r} is invalid") from error


@dataclass(frozen=True, order=True)
class StrongIdentifier:
    """One normalized strong paper identifier."""

    scheme: StrongIdentifierScheme
    value: str

    def __post_init__(self) -> None:
        normalized = normalize_external_id(self.scheme, self.value)
        if normalized is None or normalized[0] != self.scheme:
            raise ValueError(f"invalid {self.scheme} identifier: {self.value!r}")
        object.__setattr__(self, "value", normalized[1])

    def as_dict(self) -> dict[str, str]:
        return {"scheme": self.scheme, "value": self.value}


@dataclass(frozen=True, order=True)
class BibliographicDateEvidence:
    """A dated provider fact whose semantic kind is retained, not collapsed."""

    source_occurrence_id: str
    kind: str
    value: str
    precision: DatePrecision

    def __post_init__(self) -> None:
        if not self.source_occurrence_id.strip():
            raise ValueError("date evidence requires a source occurrence")
        if not self.kind.strip():
            raise ValueError("date evidence requires a semantic kind")
        _validate_date(self.value, self.precision)

    def as_dict(self) -> dict[str, str]:
        return {
            "source_occurrence_id": self.source_occurrence_id,
            "kind": self.kind,
            "value": self.value,
            "precision": self.precision,
        }


@dataclass(frozen=True)
class PaperEvidenceOccurrence:
    """Immutable normalized evidence from exactly one provider occurrence."""

    occurrence_id: str
    provider: str
    source_record_id: str
    source_reference: str
    identifiers: tuple[StrongIdentifier, ...] = ()
    title: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    journal: str | None = None
    document_type: str | None = None
    dates: tuple[BibliographicDateEvidence, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("occurrence_id", self.occurrence_id),
            ("provider", self.provider),
            ("source_record_id", self.source_record_id),
            ("source_reference", self.source_reference),
        ):
            if not value.strip():
                raise ValueError(f"paper occurrence requires {field_name}")
        if self.year is not None and not 1000 <= self.year <= 9999:
            raise ValueError("paper occurrence year must be a four-digit year")
        if any(item.source_occurrence_id != self.occurrence_id for item in self.dates):
            raise ValueError("date evidence must reference its containing occurrence")

        normalized_identifiers = tuple(sorted(set(self.identifiers)))
        normalized_dates = tuple(sorted(set(self.dates)))
        object.__setattr__(self, "identifiers", normalized_identifiers)
        object.__setattr__(self, "dates", normalized_dates)

    @property
    def normalized_title(self) -> str:
        return _normalized_text(self.title or "")

    @property
    def normalized_authors(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    normalized
                    for author in self.authors
                    if (normalized := _normalized_author(author))
                }
            )
        )

    @property
    def normalized_journal(self) -> str:
        return _normalized_text(self.journal or "")

    def secondary_key(self) -> tuple[str, tuple[str, ...], int, str] | None:
        """Return only the exact, independently supported secondary key."""

        if (
            not self.normalized_title
            or not self.normalized_authors
            or self.year is None
            or not self.normalized_journal
        ):
            return None
        return (
            self.normalized_title,
            self.normalized_authors,
            self.year,
            self.normalized_journal,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "occurrence_id": self.occurrence_id,
            "provider": self.provider,
            "source_record_id": self.source_record_id,
            "source_reference": self.source_reference,
            "identifiers": [item.as_dict() for item in self.identifiers],
            "title": self.title,
            "normalized_title": self.normalized_title,
            "authors": list(self.authors),
            "normalized_authors": list(self.normalized_authors),
            "year": self.year,
            "journal": self.journal,
            "normalized_journal": self.normalized_journal,
            "document_type": self.document_type,
            "dates": [item.as_dict() for item in self.dates],
        }


@dataclass(frozen=True, order=True)
class PaperMergeEvidence:
    """One deterministic edge supporting a candidate component."""

    method: Literal["strong-identifier", "secondary-bibliographic"]
    left_occurrence_id: str
    right_occurrence_id: str
    scheme: StrongIdentifierScheme | None = None
    value: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "method": self.method,
            "left_occurrence_id": self.left_occurrence_id,
            "right_occurrence_id": self.right_occurrence_id,
            "scheme": self.scheme,
            "value": self.value,
        }


@dataclass(frozen=True)
class CanonicalPaperComponent:
    """One matched canonical paper or one withheld review candidate."""

    candidate_id: str
    canonical_id: str | None
    status: MergeStatus
    primary_identifier: StrongIdentifier | None
    conflict_schemes: tuple[StrongIdentifierScheme, ...]
    occurrences: tuple[PaperEvidenceOccurrence, ...]
    merge_evidence: tuple[PaperMergeEvidence, ...]
    date_evidence: tuple[BibliographicDateEvidence, ...]
    digest: str

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "candidate_id": self.candidate_id,
            "canonical_id": self.canonical_id,
            "status": self.status,
            "primary_identifier": (
                self.primary_identifier.as_dict()
                if self.primary_identifier is not None
                else None
            ),
            "conflict_schemes": list(self.conflict_schemes),
            "occurrences": [item.as_dict() for item in self.occurrences],
            "merge_evidence": [item.as_dict() for item in self.merge_evidence],
            "date_evidence": [item.as_dict() for item in self.date_evidence],
            "canonical_date_selected": False,
        }
        if include_digest:
            result["digest"] = self.digest
        return result


@dataclass(frozen=True)
class CanonicalPaperMergePlan:
    policy_version: str
    plan_version: str
    components: tuple[CanonicalPaperComponent, ...]
    digest: str

    @property
    def occurrence_count(self) -> int:
        return sum(len(item.occurrences) for item in self.components)

    def as_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "policy_version": self.policy_version,
            "plan_version": self.plan_version,
            "occurrence_count": self.occurrence_count,
            "components": [item.as_dict() for item in self.components],
        }
        if include_digest:
            result["digest"] = self.digest
        return result


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def _link_group(
    indices: list[int],
    occurrences: tuple[PaperEvidenceOccurrence, ...],
    union_find: _UnionFind,
    evidence: set[PaperMergeEvidence],
    *,
    method: Literal["strong-identifier", "secondary-bibliographic"],
    scheme: StrongIdentifierScheme | None = None,
    value: str | None = None,
) -> None:
    ordered = sorted(indices, key=lambda index: occurrences[index].occurrence_id)
    if len(ordered) < 2:
        return
    owner = ordered[0]
    for index in ordered[1:]:
        union_find.union(owner, index)
        evidence.add(
            PaperMergeEvidence(
                method=method,
                left_occurrence_id=occurrences[owner].occurrence_id,
                right_occurrence_id=occurrences[index].occurrence_id,
                scheme=scheme,
                value=value,
            )
        )


def _component_identifier_values(
    occurrences: tuple[PaperEvidenceOccurrence, ...],
) -> dict[StrongIdentifierScheme, set[str]]:
    values: dict[StrongIdentifierScheme, set[str]] = {
        scheme: set() for scheme in _SCHEME_PRECEDENCE
    }
    for occurrence in occurrences:
        for identifier in occurrence.identifiers:
            values[identifier.scheme].add(identifier.value)
    return values


def _primary_identifier(
    values: dict[StrongIdentifierScheme, set[str]],
) -> StrongIdentifier | None:
    for scheme in _SCHEME_PRECEDENCE:
        if values[scheme]:
            return StrongIdentifier(scheme, min(values[scheme]))
    return None


def _matched_canonical_id(
    identifier: StrongIdentifier | None,
    component_digest: str,
) -> str:
    if identifier is None:
        return f"paper-secondary-{component_digest[:24]}"
    identity = f"{identifier.scheme}:{identifier.value}"
    return (
        f"paper-{identifier.scheme}-{_safe_id(identifier.value)}-"
        f"{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
    )


def build_canonical_paper_merge_plan(
    source_occurrences: Iterable[PaperEvidenceOccurrence],
    *,
    enable_secondary_merge: bool = True,
) -> CanonicalPaperMergePlan:
    """Build an order-independent paper merge plan without selecting cohorts."""

    occurrences = tuple(sorted(source_occurrences, key=lambda item: item.occurrence_id))
    occurrence_ids = [item.occurrence_id for item in occurrences]
    if len(set(occurrence_ids)) != len(occurrence_ids):
        raise ValueError("paper evidence occurrence IDs must be unique")

    union_find = _UnionFind(len(occurrences))
    all_evidence: set[PaperMergeEvidence] = set()
    identifier_groups: dict[tuple[StrongIdentifierScheme, str], list[int]] = (
        defaultdict(list)
    )
    for index, occurrence in enumerate(occurrences):
        for identifier in occurrence.identifiers:
            identifier_groups[(identifier.scheme, identifier.value)].append(index)
    for (scheme, value), indices in sorted(identifier_groups.items()):
        _link_group(
            indices,
            occurrences,
            union_find,
            all_evidence,
            method="strong-identifier",
            scheme=scheme,
            value=value,
        )

    if enable_secondary_merge:
        secondary_groups: dict[tuple[str, tuple[str, ...], int, str], list[int]] = (
            defaultdict(list)
        )
        for index, occurrence in enumerate(occurrences):
            key = occurrence.secondary_key()
            if key is not None:
                secondary_groups[key].append(index)
        for key, indices in sorted(secondary_groups.items()):
            _link_group(
                indices,
                occurrences,
                union_find,
                all_evidence,
                method="secondary-bibliographic",
                value=_checksum(key),
            )

    indices_by_root: dict[int, list[int]] = defaultdict(list)
    for index in range(len(occurrences)):
        indices_by_root[union_find.find(index)].append(index)

    occurrence_index_by_id = {
        occurrence.occurrence_id: index for index, occurrence in enumerate(occurrences)
    }
    evidence_by_root: dict[int, list[PaperMergeEvidence]] = defaultdict(list)
    for item in all_evidence:
        left_root = union_find.find(occurrence_index_by_id[item.left_occurrence_id])
        right_root = union_find.find(occurrence_index_by_id[item.right_occurrence_id])
        if left_root != right_root:
            raise AssertionError("merge evidence crosses canonical components")
        evidence_by_root[left_root].append(item)

    components: list[CanonicalPaperComponent] = []
    for root, indices in indices_by_root.items():
        component_occurrences = tuple(
            sorted(
                (occurrences[index] for index in indices),
                key=lambda item: item.occurrence_id,
            )
        )
        component_evidence = tuple(sorted(evidence_by_root.get(root, ())))
        identifier_values = _component_identifier_values(component_occurrences)
        conflict_schemes = tuple(
            scheme
            for scheme in _SCHEME_PRECEDENCE
            if len(identifier_values[scheme]) > 1
        )
        has_secondary_support = any(
            item.method == "secondary-bibliographic" for item in component_evidence
        )
        has_identifier = any(identifier_values[scheme] for scheme in _SCHEME_PRECEDENCE)
        insufficient = not has_identifier and not has_secondary_support
        status: MergeStatus = (
            "needs_review" if conflict_schemes or insufficient else "matched"
        )
        primary = (
            _primary_identifier(identifier_values) if not conflict_schemes else None
        )
        date_evidence = tuple(
            sorted(
                date_item
                for occurrence in component_occurrences
                for date_item in occurrence.dates
            )
        )
        unsigned_component: dict[str, object] = {
            "policy_version": CANONICAL_PAPER_MERGE_POLICY_VERSION,
            "occurrences": [item.as_dict() for item in component_occurrences],
            "merge_evidence": [item.as_dict() for item in component_evidence],
            "conflict_schemes": list(conflict_schemes),
            "status": status,
            "primary_identifier": primary.as_dict() if primary is not None else None,
            "canonical_date_selected": False,
        }
        component_digest = _checksum(unsigned_component)
        canonical_id = (
            _matched_canonical_id(primary, component_digest)
            if status == "matched"
            else None
        )
        candidate_id = canonical_id or f"paper-candidate-{component_digest[:24]}"
        components.append(
            CanonicalPaperComponent(
                candidate_id=candidate_id,
                canonical_id=canonical_id,
                status=status,
                primary_identifier=primary,
                conflict_schemes=conflict_schemes,
                occurrences=component_occurrences,
                merge_evidence=component_evidence,
                date_evidence=date_evidence,
                digest=component_digest,
            )
        )

    ordered_components = tuple(sorted(components, key=lambda item: item.candidate_id))
    unsigned_plan: dict[str, object] = {
        "policy_version": CANONICAL_PAPER_MERGE_POLICY_VERSION,
        "plan_version": PAPER_MERGE_PLAN_VERSION,
        "components": [item.as_dict() for item in ordered_components],
    }
    return CanonicalPaperMergePlan(
        policy_version=CANONICAL_PAPER_MERGE_POLICY_VERSION,
        plan_version=PAPER_MERGE_PLAN_VERSION,
        components=ordered_components,
        digest=_checksum(unsigned_plan),
    )
