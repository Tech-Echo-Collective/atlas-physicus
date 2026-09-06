"""Certify the bounded paired trial without touching production state.

This adapter consumes only the immutable January 13--19, 2020 paired raw
capture and its exact authority enrichment.  It deliberately emits a
withheld, staging-only evidence bundle: provider field mappings are not human
review, provider dates are not a selected canonical metric date, and author
identifiers are not a reviewed researcher identity decision.

There is no network, database, cursor, metric calculation, or activation path
in this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal, cast

from .attribution.affiliation_identifiers import (
    align_affiliation_ror_evidence as _align_affiliation_ror_evidence,
)
from .certification.citations import (
    CITATION_CERTIFICATION_RULE_VERSION,
    CITATION_POLICY_VERSION,
    CitationCohortCertification,
    CitationObservationCertification,
    CitationObservationEvidence,
    certify_citation_cohort,
    certify_citation_observation,
)
from .certification.contracts import (
    CERTIFICATION_POLICY_VERSION,
    CertificationState,
    EvidenceCertificationDecision,
    EvidenceKind,
    EvidenceReference,
    canonical_digest,
)
from .certification.fields import (
    FIELD_CERTIFICATION_RULE_VERSION,
    FieldCertificationResult,
    FieldLedgerEvidence,
    FieldWeight,
    certify_field_ledger,
)
from .certification.institutions import (
    INSTITUTION_CERTIFICATION_RULE_VERSION,
    InstitutionAuthorityRecord,
    InstitutionResolutionEvidence,
    certify_institution,
    institution_authority_version,
)
from .certification.validation_artifacts import (
    check_validation_size,
    require_validation_runtime,
)
from .connectors.arxiv import ArxivConnector
from .connectors.base import (
    NormalizedRecord,
    SourceRecord,
    SourceTransport,
    normalize_external_id,
)
from .connectors.field_mapping import (
    ProviderCategoryEvidence,
    ProviderCategoryRole,
)
from .connectors.inspire import InspireConnector
from .fields.mapping import (
    CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
    ProviderFieldProjection,
    reconcile_cross_provider_field_evidence,
)
from .paired_capture import (
    PAIR_ID,
    TRIAL_SCOPE_BY_ID,
    PairedCaptureSafetyError,
    PairedCaptureVerificationError,
    validate_staging_output,
    verify_paired_capture_manifest,
)
from .paired_enrichment import (
    ENRICHMENT_ID,
    PairedEnrichmentSafetyError,
    PairedEnrichmentVerificationError,
    verify_paired_enrichment_manifest,
)
from .search_index import normalize_search_term
from .storage.historical_read import HistoricalReadError, open_artifact

SUPERSEDED_CERTIFICATION_ID = "physics-paired-certification-2020w03-v1"
CERTIFICATION_ID = "physics-paired-certification-2020w03-v2"
CERTIFICATION_MANIFEST_VERSION = "physics-paired-trial-certification-manifest-v2"
CERTIFICATION_REPORT_VERSION = "physics-paired-trial-certification-report-v2"
PROJECTION_PIPELINE_VERSION = "paired-certification-projection-v2"
PAPER_IDENTITY_RULE_VERSION = "exact-strong-paper-identifier-v1"
METRIC_DATE_RULE_VERSION = "canonical-metric-date-selection-v1"
RELATIONSHIP_PROJECTION_VERSION = "paper-time-affiliation-precedence-v1"
RESEARCHER_PROJECTION_VERSION = "paired-unreviewed-researcher-projection-v1"
# Two scopes; INSPIRE permits 250 and arXiv remains strictly below 1,000.
MAX_SOURCE_OCCURRENCES = 2 * (250 + 999)


def _generator_rule_versions() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                CERTIFICATION_POLICY_VERSION,
                PROJECTION_PIPELINE_VERSION,
                PAPER_IDENTITY_RULE_VERSION,
                METRIC_DATE_RULE_VERSION,
                RELATIONSHIP_PROJECTION_VERSION,
                RESEARCHER_PROJECTION_VERSION,
                FIELD_CERTIFICATION_RULE_VERSION,
                CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
                INSTITUTION_CERTIFICATION_RULE_VERSION,
                CITATION_CERTIFICATION_RULE_VERSION,
                CITATION_POLICY_VERSION,
            }
        )
    )


class PairedTrialCertificationError(ValueError):
    """Raised when staged evidence cannot be certified reproducibly."""


class _NoNetworkTransport:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"certification attempted network transport method {name}")


@dataclass(frozen=True)
class _Occurrence:
    occurrence_id: str
    scope_id: str
    atlas_field_id: str
    provider: Literal["inspire", "arxiv"]
    record: SourceRecord
    normalized: NormalizedRecord
    page_reference: EvidenceReference
    page_path: str
    page_response_received_at: datetime
    strong_identifiers: tuple[tuple[str, str], ...]
    invalid_identifiers: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class _CanonicalPaper:
    canonical_id: str
    occurrences: tuple[_Occurrence, ...]
    strong_identifiers: tuple[tuple[str, str], ...]
    identity_state: CertificationState
    identity_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _AuthorityBundle:
    records: tuple[InstitutionAuthorityRecord, ...]
    provider_crosswalk: dict[tuple[str, str], str]
    references: dict[tuple[str, str], EvidenceReference]
    raw_rows: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class _CitationCandidate:
    certification: CitationObservationCertification
    reference: EvidenceReference
    provider: str
    raw_citation_count: int | None

    @property
    def comparison_signature(self) -> tuple[int | None, int | None, datetime | None]:
        return (
            self.raw_citation_count,
            self.certification.non_self_citation_count,
            self.certification.cutoff,
        )


def _canonical_json(value: object, *, pretty: bool = False) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            sort_keys=True,
        )
        + ("\n" if pretty else "")
    ).encode("utf-8")


def _checksum_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _checksum(value: object) -> str:
    return _checksum_bytes(_canonical_json(value))


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _fraction(value: Fraction) -> dict[str, object]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "exact": str(value),
        "decimal": float(value),
    }


def _parse_aware(value: object, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise PairedTrialCertificationError(
            f"{label} is not an ISO timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PairedTrialCertificationError(f"{label} is not timezone-aware")
    return parsed.astimezone(UTC)


def _record_categories(
    normalized: NormalizedRecord,
) -> tuple[ProviderCategoryEvidence, ...]:
    result: list[ProviderCategoryEvidence] = []
    raw = normalized.attributes.get("raw_category_evidence")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping) or not isinstance(
                item.get("category"), str
            ):
                continue
            role_value = item.get("role", "unspecified")
            role = cast(
                ProviderCategoryRole,
                role_value
                if role_value in {"primary", "secondary", "unspecified"}
                else "unspecified",
            )
            result.append(
                ProviderCategoryEvidence(
                    category=cast(str, item["category"]),
                    role=role,
                    taxonomy=str(item["taxonomy"]) if item.get("taxonomy") else None,
                    scheme=str(item["scheme"]) if item.get("scheme") else None,
                    source=str(item["source"]) if item.get("source") else None,
                )
            )
    if not result:
        categories = normalized.attributes.get("raw_categories")
        if isinstance(categories, list):
            result.extend(
                ProviderCategoryEvidence(category=item)
                for item in categories
                if isinstance(item, str) and item.strip()
            )
    return tuple(result)


def _strong_identifiers(
    record: SourceRecord, normalized: NormalizedRecord
) -> tuple[tuple[tuple[str, str], ...], tuple[dict[str, str], ...]]:
    candidates: list[tuple[str, object]] = list(normalized.external_ids)
    candidates.append((record.provider, record.source_record_id))
    if record.provider == "inspire":
        for item in record.raw.get("arxiv_eprints") or []:
            if isinstance(item, Mapping):
                candidates.append(("arxiv", item.get("value")))
        for item in record.raw.get("dois") or []:
            candidates.append(
                ("doi", item.get("value") if isinstance(item, Mapping) else item)
            )
    else:
        candidates.append(("doi", record.raw.get("doi")))
    valid: set[tuple[str, str]] = set()
    invalid: set[tuple[str, str]] = set()
    for scheme, raw_value in candidates:
        if scheme not in {"doi", "arxiv", "inspire"} or raw_value is None:
            continue
        normalized_id = normalize_external_id(scheme, raw_value)
        if normalized_id is None:
            invalid.add((scheme, str(raw_value)))
        else:
            valid.add(normalized_id)
    return tuple(sorted(valid)), tuple(
        {"scheme": scheme, "value": value} for scheme, value in sorted(invalid)
    )


def _load_occurrences(
    raw_root: Path, raw_manifest: Mapping[str, Any]
) -> tuple[_Occurrence, ...]:
    no_network = cast(SourceTransport, _NoNetworkTransport())
    result: list[_Occurrence] = []
    for partition in cast(list[Mapping[str, Any]], raw_manifest["partitions"]):
        scope_id = cast(str, partition["scope_id"])
        provider = cast(Literal["inspire", "arxiv"], partition["provider"])
        scope = TRIAL_SCOPE_BY_ID[scope_id]
        connector: InspireConnector | ArxivConnector
        if provider == "inspire":
            connector = InspireConnector(
                no_network,
                "https://inspirehep.net/api",
                acquisition_scope=scope.parser_scope,
            )
        else:
            connector = ArxivConnector(
                no_network,
                "https://export.arxiv.org/api/query",
                acquisition_scope=scope.parser_scope,
            )
        for page in cast(list[Mapping[str, Any]], partition["pages"]):
            path = cast(str, page["path"])
            checksum = cast(str, page["checksum"])
            body = (raw_root / path).read_bytes()
            if isinstance(connector, InspireConnector):
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise PairedTrialCertificationError(
                        "verified INSPIRE page is not an object"
                    )
                records = connector._records(payload)
            else:
                records = connector._records(body.decode("utf-8"))
            if len(records) != page["record_count"]:
                raise PairedTrialCertificationError(
                    "provider row count changed after raw-manifest verification"
                )
            lineage = cast(Mapping[str, Any], page["http_lineage"])
            received = _parse_aware(
                lineage.get("response_received_at"), "raw response_received_at"
            )
            for record in records:
                normalized = connector.normalize_record(record)
                identifiers, invalid = _strong_identifiers(record, normalized)
                occurrence_id = f"{scope_id}:{provider}:{record.source_record_id}"
                reference = EvidenceReference(
                    provider=provider,
                    source_record_id=f"{scope_id}:{record.source_record_id}",
                    checksum=checksum,
                    source_snapshot_id=checksum,
                    storage_reference=f"{path}#{provider}:{record.source_record_id}",
                )
                result.append(
                    _Occurrence(
                        occurrence_id=occurrence_id,
                        scope_id=scope_id,
                        atlas_field_id=cast(str, partition["atlas_field_id"]),
                        provider=provider,
                        record=record,
                        normalized=normalized,
                        page_reference=reference,
                        page_path=path,
                        page_response_received_at=received,
                        strong_identifiers=identifiers,
                        invalid_identifiers=invalid,
                    )
                )
    if len(result) > MAX_SOURCE_OCCURRENCES:
        raise PairedTrialCertificationError(
            "paired source rows exceed the fixed trial cap"
        )
    ordered = tuple(sorted(result, key=lambda item: item.occurrence_id))
    if len({item.occurrence_id for item in ordered}) != len(ordered):
        raise PairedTrialCertificationError(
            "paired capture contains duplicate scoped rows"
        )
    return ordered


def _canonicalize(occurrences: tuple[_Occurrence, ...]) -> tuple[_CanonicalPaper, ...]:
    parent = list(range(len(occurrences)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    by_identifier: dict[tuple[str, str], int] = {}
    for index, occurrence in enumerate(occurrences):
        for identifier in occurrence.strong_identifiers:
            existing = by_identifier.setdefault(identifier, index)
            union(existing, index)

    components: dict[int, list[_Occurrence]] = defaultdict(list)
    for index, occurrence in enumerate(occurrences):
        components[find(index)].append(occurrence)
    papers: list[_CanonicalPaper] = []
    scheme_priority = {"doi": 0, "arxiv": 1, "inspire": 2}
    for values in components.values():
        ordered = tuple(sorted(values, key=lambda item: item.occurrence_id))
        identifiers = tuple(
            sorted(
                {
                    identifier
                    for item in ordered
                    for identifier in item.strong_identifiers
                },
                key=lambda item: (scheme_priority[item[0]], item[1]),
            )
        )
        values_by_scheme: dict[str, set[str]] = defaultdict(set)
        for scheme, value in identifiers:
            values_by_scheme[scheme].add(value)
        conflict_schemes = tuple(
            sorted(
                scheme for scheme, values in values_by_scheme.items() if len(values) > 1
            )
        )
        identity = identifiers or tuple(
            (item.provider, item.record.source_record_id) for item in ordered
        )
        canonical_id = f"paired-paper-{canonical_digest(identity)[:28]}"
        papers.append(
            _CanonicalPaper(
                canonical_id=canonical_id,
                occurrences=ordered,
                strong_identifiers=identifiers,
                identity_state="conflicted" if conflict_schemes else "certified",
                identity_reasons=(
                    (
                        "exact-identifier component contains multiple values for: "
                        + ", ".join(conflict_schemes),
                    )
                    if conflict_schemes
                    else ()
                ),
            )
        )
    return tuple(sorted(papers, key=lambda item: item.canonical_id))


def _normalize_ror(value: object) -> str | None:
    normalized = normalize_external_id("ror", value)
    return normalized[1] if normalized else None


def _ror_ids(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    result: set[str] = set()
    for item in values:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("schema") or item.get("scheme") or "").casefold() != "ror":
            continue
        if normalized := _normalize_ror(item.get("value")):
            result.add(normalized)
    return tuple(sorted(result))


def _ror_name(raw: Mapping[str, Any], record_id: str) -> tuple[str, tuple[str, ...]]:
    names = raw.get("names")
    observed: list[tuple[str, tuple[str, ...]]] = []
    if isinstance(names, list):
        for item in names:
            if (
                not isinstance(item, Mapping)
                or not str(item.get("value") or "").strip()
            ):
                continue
            types = item.get("types")
            observed.append(
                (
                    " ".join(str(item["value"]).split()),
                    tuple(str(value) for value in types)
                    if isinstance(types, list)
                    else (),
                )
            )
    display = next((name for name, types in observed if "ror_display" in types), None)
    canonical = display or (observed[0][0] if observed else f"ROR {record_id}")
    return canonical, tuple(
        sorted({name for name, _types in observed if name != canonical})
    )


def _authority_bundle(
    enrichment_root: Path, enrichment: Mapping[str, Any]
) -> _AuthorityBundle:
    references: dict[tuple[str, str], EvidenceReference] = {}
    raw_rows: list[dict[str, object]] = []
    ror_raw: dict[str, Mapping[str, Any]] = {}
    inspire_raw: dict[str, Mapping[str, Any]] = {}
    records = cast(Mapping[str, list[Mapping[str, Any]]], enrichment["records"])
    for role, rows in records.items():
        for record_metadata in rows:
            record_id = cast(str, record_metadata["source_record_id"])
            path = cast(str, record_metadata["path"])
            checksum = cast(str, record_metadata["checksum"])
            raw = json.loads((enrichment_root / path).read_text(encoding="utf-8"))
            kind = cast(str, record_metadata["record_kind"])
            provider = cast(str, record_metadata["provider"])
            references[(kind, record_id)] = EvidenceReference(
                provider=provider,
                source_record_id=record_id,
                checksum=checksum,
                source_snapshot_id=checksum,
                storage_reference=path,
            )
            raw_rows.append(
                {
                    "role": role,
                    "record_kind": kind,
                    "provider": provider,
                    "source_record_id": record_id,
                    "path": path,
                    "checksum": checksum,
                    "http_lineage": record_metadata["http_lineage"],
                    "raw": raw,
                }
            )
            if kind == "ror":
                ror_raw[record_id] = raw
            else:
                inspire_raw[record_id] = raw

    authority_records: list[InstitutionAuthorityRecord] = []
    for record_id, raw in sorted(ror_raw.items()):
        canonical, aliases = _ror_name(raw, record_id)
        parents: set[str] = set()
        relationships = raw.get("relationships")
        if isinstance(relationships, list):
            for relationship in relationships:
                if (
                    isinstance(relationship, Mapping)
                    and str(relationship.get("type") or "").casefold() == "parent"
                    and (parent := _normalize_ror(relationship.get("id")))
                ):
                    parents.add(parent)
        authority_records.append(
            InstitutionAuthorityRecord(
                institution_id=f"institution-ror-{record_id}",
                ror_id=record_id,
                canonical_name=canonical,
                aliases=aliases,
                active=str(raw.get("status") or "").casefold() == "active",
                parent_ror_ids=tuple(sorted(parents)),
            )
        )
    crosswalk: dict[tuple[str, str], str] = {}
    for record_id, inspire_document in sorted(inspire_raw.items()):
        metadata = inspire_document.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        rors = _ror_ids(metadata.get("external_system_identifiers"))
        if len(rors) == 1 and rors[0] in ror_raw:
            crosswalk[("inspire", record_id)] = rors[0]
    return _AuthorityBundle(
        records=tuple(authority_records),
        provider_crosswalk=crosswalk,
        references=references,
        raw_rows=tuple(
            sorted(
                raw_rows,
                key=lambda item: (str(item["role"]), str(item["source_record_id"])),
            )
        ),
    )


def _evidence_rows(references: Iterable[EvidenceReference]) -> list[dict[str, object]]:
    return [
        {
            "provider": item.provider,
            "source_record_id": item.source_record_id,
            "checksum": item.checksum,
            "source_snapshot_id": item.source_snapshot_id,
            "storage_reference": item.storage_reference,
        }
        for item in sorted(set(references))
    ]


def _decision_row(
    decision: EvidenceCertificationDecision, *, mass: Fraction
) -> dict[str, object]:
    return {
        "decision_id": decision.decision_id,
        "subject_type": decision.subject_type,
        "subject_id": decision.subject_id,
        "evidence_kind": decision.evidence_kind,
        "state": decision.state,
        "rule_version": decision.rule_version,
        "dataset_version": decision.dataset_version,
        "acquisition_scope": decision.acquisition_scope,
        "evidence": _evidence_rows(decision.evidence),
        "reasons": list(decision.reasons),
        "reviewed_by": decision.reviewed_by,
        "reviewed_at": decision.reviewed_at.isoformat()
        if decision.reviewed_at
        else None,
        "mass": _fraction(mass),
    }


def _make_decision(
    *,
    subject_type: str,
    subject_id: str,
    kind: EvidenceKind,
    state: CertificationState,
    rule_version: str,
    evidence: Iterable[EvidenceReference],
    reasons: Iterable[str] = (),
) -> EvidenceCertificationDecision:
    reason_values = tuple(dict.fromkeys(reason for reason in reasons if reason))
    if state != "certified" and not reason_values:
        reason_values = ("evidence did not satisfy the explicit certification rule",)
    return EvidenceCertificationDecision(
        subject_type=subject_type,
        subject_id=subject_id,
        evidence_kind=kind,
        state=state,
        rule_version=rule_version,
        dataset_version=CERTIFICATION_ID,
        acquisition_scope=PAIR_ID,
        evidence=tuple(sorted(set(evidence))),
        reasons=reason_values,
    )


def _source_rows(occurrences: tuple[_Occurrence, ...]) -> list[dict[str, object]]:
    return [
        {
            "occurrence_id": item.occurrence_id,
            "scope_id": item.scope_id,
            "atlas_field_id": item.atlas_field_id,
            "provider": item.provider,
            "source_record_id": item.record.source_record_id,
            "source_record_checksum": item.record.checksum,
            "page_path": item.page_path,
            "page_checksum": item.page_reference.checksum,
            "page_response_received_at": item.page_response_received_at.isoformat(),
            "strong_identifiers": [
                {"scheme": scheme, "value": value}
                for scheme, value in item.strong_identifiers
            ],
            "invalid_identifiers": list(item.invalid_identifiers),
            "raw": item.record.raw,
        }
        for item in occurrences
    ]


def _publication_date_values(paper: _CanonicalPaper) -> tuple[str, ...]:
    candidates: set[str] = set()
    for occurrence in paper.occurrences:
        raw = occurrence.record.raw
        values: list[object] = []
        if occurrence.provider == "inspire":
            values.extend((raw.get("preprint_date"), raw.get("earliest_date")))
        else:
            values.append(raw.get("published"))
        for value in values:
            if isinstance(value, str) and value.strip():
                candidates.add(value.strip())
    return tuple(sorted(candidates))


def _parse_provider_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        if len(normalized) == 4:
            return date(int(normalized), 1, 1)
        if len(normalized) == 7:
            return date.fromisoformat(f"{normalized}-01")
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(normalized[:10])
        except ValueError:
            return None


def _author_name(author: Mapping[str, Any], position: int) -> str:
    value = author.get("full_name") or author.get("name")
    return " ".join(str(value).split()) if value else f"unlabeled-author-{position}"


def _researcher_ids(author: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    candidates: list[tuple[str, object]] = []
    for key in ("ORCID", "orcid"):
        candidates.append(("orcid", author.get(key)))
    record_reference: object = author.get("record")
    if isinstance(record_reference, Mapping):
        record_reference = record_reference.get("$ref")
    candidates.extend(
        (
            ("inspire-author", record_reference),
            ("inspire-author", author.get("recid")),
        )
    )
    ids = author.get("ids")
    if isinstance(ids, list):
        for item in ids:
            if isinstance(item, Mapping):
                candidates.append(
                    (
                        str(item.get("schema") or item.get("scheme") or ""),
                        item.get("value"),
                    )
                )
    result: set[tuple[str, str]] = set()
    for scheme, value in candidates:
        normalized_scheme = scheme.strip().casefold().replace(" ", "-")
        if normalized_scheme in {"inspire", "inspire-bai", "bai"}:
            normalized_scheme = "inspire-bai"
        if normalized_scheme not in {"orcid", "inspire-author", "inspire-bai"}:
            continue
        if normalized := normalize_external_id(normalized_scheme, value):
            result.add(normalized)
    return tuple(sorted(result))


def _raw_affiliations(author: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    value = author.get("affiliations")
    if not isinstance(value, list) or not value:
        value = author.get("raw_affiliations")
    if not isinstance(value, list):
        return ()
    return tuple(
        item
        for item in value
        if isinstance(item, Mapping) and _affiliation_has_evidence(item)
    )


def _provider_institution_id(affiliation: Mapping[str, Any]) -> str | None:
    record: object = affiliation.get("record")
    if isinstance(record, Mapping):
        record = record.get("$ref")
    normalized = normalize_external_id("inspire-institution", record)
    return normalized[1] if normalized else None


def _affiliation_rors(affiliation: Mapping[str, Any]) -> tuple[str, ...]:
    observed: set[str] = set()
    for key in ("identifiers", "external_ids", "externalIds"):
        observed.update(_ror_ids(affiliation.get(key)))
    return tuple(sorted(observed))


def _affiliation_name(affiliation: Mapping[str, Any]) -> str | None:
    value = affiliation.get("value") or affiliation.get("name")
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def _affiliation_has_evidence(affiliation: Mapping[str, Any]) -> bool:
    return bool(
        _affiliation_name(affiliation)
        or _provider_institution_id(affiliation)
        or _affiliation_rors(affiliation)
    )


def _occurrence_authors(occurrence: _Occurrence) -> tuple[Mapping[str, Any], ...]:
    value = occurrence.normalized.attributes.get("authors")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _occurrence_has_affiliation_evidence(occurrence: _Occurrence) -> bool:
    return any(_raw_affiliations(author) for author in _occurrence_authors(occurrence))


def _author_affiliation_assertions(
    author: Mapping[str, Any],
) -> dict[str, frozenset[str]]:
    """Return typed affiliation claims without equating unlike identifiers.

    Asymmetric enrichment is compatible when a shared assertion namespace
    agrees exactly. Within every namespace represented by both sources, the
    complete set must match: partial overlap cannot certify an author's other
    affiliation shares.
    """

    assertions: dict[str, set[str]] = defaultdict(set)
    for affiliation in _raw_affiliations(author):
        if (name := _affiliation_name(affiliation)) and (
            normalized := normalize_search_term(name)
        ):
            assertions["normalized-name"].add(normalized)
        if provider_id := _provider_institution_id(affiliation):
            assertions["inspire-institution"].add(provider_id)
        assertions["ror"].update(_affiliation_rors(affiliation))
    assertions["ror"].update(_ror_ids(author.get("affiliations_identifiers")))
    return {
        namespace: frozenset(values)
        for namespace, values in assertions.items()
        if values
    }


def _crosscheck_author_name(author: Mapping[str, Any]) -> str:
    value = author.get("full_name") or author.get("name")
    return normalize_search_term(str(value)) if value else ""


def _lower_precedence_affiliation_crosscheck(
    paper: _CanonicalPaper,
    selected: _Occurrence,
    author: Mapping[str, Any],
) -> tuple[str, tuple[EvidenceReference, ...], tuple[str, ...]]:
    """Compare only exactly aligned author/name evidence; never infer an alignment."""

    if selected.provider != "inspire":
        return "not-applicable", (), ()
    author_name = _crosscheck_author_name(author)
    primary_assertions = _author_affiliation_assertions(author)
    if not author_name or not primary_assertions:
        return "not-comparable", (), ()

    arxiv_occurrences = tuple(
        item for item in paper.occurrences if item.provider == "arxiv"
    )
    if len(arxiv_occurrences) != 1:
        return "not-comparable", (), ()
    arxiv = arxiv_occurrences[0]
    matches = tuple(
        candidate
        for candidate in _occurrence_authors(arxiv)
        if _crosscheck_author_name(candidate) == author_name
    )
    if len(matches) != 1:
        return (
            "needs-review-ambiguous-author-alignment" if matches else "not-comparable",
            (arxiv.page_reference,) if matches else (),
            ("lower-precedence arXiv evidence has an ambiguous exact author alignment",)
            if matches
            else (),
        )
    arxiv_assertions = _author_affiliation_assertions(matches[0])
    if not arxiv_assertions:
        return "crosscheck-has-no-affiliation", (arxiv.page_reference,), ()
    comparable_namespaces = tuple(
        sorted(set(primary_assertions).intersection(arxiv_assertions))
    )
    if not comparable_namespaces:
        return "not-comparable-typed-assertions", (arxiv.page_reference,), ()
    disagreements = tuple(
        namespace
        for namespace in comparable_namespaces
        if primary_assertions[namespace] != arxiv_assertions[namespace]
    )
    if disagreements:
        return (
            "needs-review-provider-disagreement",
            (arxiv.page_reference,),
            (
                "exactly aligned INSPIRE and arXiv author records retain unequal "
                "paper-time affiliation assertion sets in shared namespaces: "
                + ", ".join(disagreements),
            ),
        )
    return "corroborated-exact-assertions", (arxiv.page_reference,), ()


def _selected_relationship_occurrence(
    paper: _CanonicalPaper,
) -> tuple[_Occurrence | None, str]:
    candidates = [
        item
        for item in paper.occurrences
        if isinstance(item.normalized.attributes.get("authors"), list)
        and item.normalized.attributes["authors"]
    ]
    unique_by_provider: dict[str, tuple[_Occurrence, ...]] = {}
    for provider in ("inspire", "arxiv"):
        unique = {
            (item.record.source_record_id, item.record.checksum): item
            for item in candidates
            if item.provider == provider
        }
        unique_by_provider[provider] = tuple(unique.values())
        if len(unique) > 1:
            return None, f"conflicted-multiple-{provider}-paper-time-projections"

    inspire = unique_by_provider["inspire"]
    arxiv = unique_by_provider["arxiv"]
    if inspire:
        selected = inspire[0]
        if _occurrence_has_affiliation_evidence(selected):
            return selected, "selected-inspire-paper-time-evidence"
        if arxiv and _occurrence_has_affiliation_evidence(arxiv[0]):
            return (
                arxiv[0],
                "selected-arxiv-paper-time-evidence-after-inspire-affiliation-absence",
            )
        return selected, "selected-inspire-authors-without-affiliation-evidence"
    if arxiv:
        return arxiv[0], "selected-arxiv-paper-time-evidence"
    return None, "unresolved-no-paper-time-author-evidence"


def _field_projection(
    paper: _CanonicalPaper,
) -> tuple[dict[str, object], FieldCertificationResult]:
    projections = [
        ProviderFieldProjection(
            provider=item.provider,
            source_record_id=item.record.source_record_id,
            categories=_record_categories(item.normalized),
            source_snapshot_id=item.page_reference.checksum,
        )
        for item in paper.occurrences
    ]
    ledger = reconcile_cross_provider_field_evidence(projections)
    category_count = len(ledger.category_mappings)
    unmapped_count = sum(item.status == "unmapped" for item in ledger.category_mappings)
    exact_unmapped = (
        Fraction(unmapped_count, category_count) if category_count else Fraction(1)
    )
    fields = tuple(item.field_id for item in ledger.assignments)
    exact_mapped = Fraction(1) - exact_unmapped
    exact_assignments = (
        {field_id: exact_mapped / len(fields) for field_id in fields} if fields else {}
    )
    provider_fields: dict[str, set[str]] = defaultdict(set)
    for item in ledger.category_mappings:
        provider_fields[item.provider].update(item.atlas_field_ids)
    disagreement = len({tuple(sorted(value)) for value in provider_fields.values()}) > 1
    evidence = FieldLedgerEvidence(
        paper_id=paper.canonical_id,
        assignments=tuple(
            FieldWeight(field_id=field_id, weight=float(weight))
            for field_id, weight in exact_assignments.items()
        ),
        unmapped_mass=float(exact_unmapped),
        review_state="unreviewed",
        ontology_version=ledger.ontology_version,
        mapping_policy_version=ledger.mapping_version,
        weighting_policy_version=ledger.weighting_policy_version,
        source_evidence_ids=tuple(
            sorted(item.page_reference.source_record_id for item in paper.occurrences)
        ),
        source_manifest_digest=canonical_digest(
            tuple(item.page_reference for item in paper.occurrences)
        ),
        provider_disagreement=disagreement,
    )
    certified = certify_field_ledger(evidence)
    row = {
        "canonical_paper_id": paper.canonical_id,
        "review_state": evidence.review_state,
        "provider_disagreement": disagreement,
        "reconciliation_version": CROSS_PROVIDER_FIELD_RECONCILIATION_VERSION,
        "ontology_version": ledger.ontology_version,
        "mapping_policy_version": ledger.mapping_version,
        "weighting_policy_version": ledger.weighting_policy_version,
        "category_mappings": ledger.provenance_payload()["category_mappings"],
        "assignments": [
            {"field_id": field_id, "weight": _fraction(weight)}
            for field_id, weight in exact_assignments.items()
        ],
        "unmapped_mass": _fraction(exact_unmapped),
        "conservation_total": _fraction(
            sum(exact_assignments.values(), exact_unmapped)
        ),
        "certification_state": certified.state,
        "certification_reasons": list(certified.reasons),
        "eligible_for_metrics": False,
    }
    return row, certified


def _citation_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PairedTrialCertificationError("provider citation count is invalid")
    return value


def _citation_rows(
    paper: _CanonicalPaper,
    field_row: Mapping[str, object],
) -> tuple[list[dict[str, object]], list[CitationObservationCertification]]:
    rows: list[dict[str, object]] = []
    certifications: list[CitationObservationCertification] = []
    assignments = cast(list[Mapping[str, Any]], field_row["assignments"])
    field_id = str(assignments[0]["field_id"]) if len(assignments) == 1 else None
    for occurrence in paper.occurrences:
        raw = occurrence.record.raw
        raw_count = _citation_count(raw.get("citation_count"))
        non_self = _citation_count(raw.get("citation_count_without_self_citations"))
        if raw_count is None and non_self is None:
            continue
        date_candidates = (
            (raw.get("preprint_date"), raw.get("earliest_date"))
            if occurrence.provider == "inspire"
            else (raw.get("published"),)
        )
        provider_date = next(
            (
                parsed
                for value in date_candidates
                if (parsed := _parse_provider_date(value))
            ),
            None,
        )
        if provider_date is None:
            rows.append(
                {
                    "canonical_paper_id": paper.canonical_id,
                    "occurrence_id": occurrence.occurrence_id,
                    "raw_citation_count": raw_count,
                    "non_self_citation_count": non_self,
                    "provider_publication_date": None,
                    "observed_at": occurrence.page_response_received_at.isoformat(),
                    "certifier_invoked": False,
                    "state": "insufficient_evidence",
                    "reasons": ["provider publication date is absent or malformed"],
                }
            )
            continue
        document_type = str(
            occurrence.normalized.attributes.get("document_type") or "unknown"
        )
        if field_id is None:
            rows.append(
                {
                    "canonical_paper_id": paper.canonical_id,
                    "occurrence_id": occurrence.occurrence_id,
                    "raw_citation_count": raw_count,
                    "non_self_citation_count": non_self,
                    "provider_publication_date": provider_date.isoformat(),
                    "canonical_metric_date_certified": False,
                    "observed_at": occurrence.page_response_received_at.isoformat(),
                    "selected_cutoff": occurrence.page_response_received_at.isoformat(),
                    "field_assignments": assignments,
                    "field_classification_state": field_row["certification_state"],
                    "document_type": document_type,
                    "certifier_invoked": False,
                    "state": "insufficient_evidence",
                    "reasons": [
                        "citation evidence is not bound to exactly one canonical field"
                    ],
                }
            )
            continue
        evidence = CitationObservationEvidence(
            paper_id=paper.canonical_id,
            dataset_version=CERTIFICATION_ID,
            acquisition_scope=PAIR_ID,
            citation_source=occurrence.provider,
            raw_citation_count=raw_count,
            non_self_citation_count=non_self,
            observed_at=occurrence.page_response_received_at,
            selected_cutoff=occurrence.page_response_received_at,
            publication_date=provider_date,
            field_id=field_id,
            document_type=document_type,
            source_reference=occurrence.page_reference,
            citation_policy_version=CITATION_POLICY_VERSION,
        )
        certification = certify_citation_observation(evidence)
        certifications.append(certification)
        rows.append(
            {
                "canonical_paper_id": paper.canonical_id,
                "occurrence_id": occurrence.occurrence_id,
                "raw_citation_count": raw_count,
                "non_self_citation_count": non_self,
                "provider_publication_date": provider_date.isoformat(),
                "canonical_metric_date_certified": False,
                "observed_at": occurrence.page_response_received_at.isoformat(),
                "selected_cutoff": occurrence.page_response_received_at.isoformat(),
                "field_id": field_id,
                "field_classification_state": field_row["certification_state"],
                "document_type": document_type,
                "certifier_invoked": True,
                "certification_id": certification.certification_id,
                "state": certification.state,
                "mature": certification.mature,
                "cohort_key": list(certification.cohort_key or ()),
                "reasons": list(certification.reasons),
            }
        )
    return rows, certifications


def _select_citation_candidate(
    candidates: Sequence[_CitationCandidate],
) -> tuple[
    _CitationCandidate | None,
    CertificationState,
    tuple[EvidenceReference, ...],
    tuple[str, ...],
]:
    """Select one reproducible observation or retain cross-source conflict."""

    if not candidates:
        return (
            None,
            "insufficient_evidence",
            (),
            ("no provider citation observation is available",),
        )
    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.provider,
                item.reference.source_record_id,
                item.reference.checksum,
                item.certification.certification_id,
            ),
        )
    )
    signatures = {item.comparison_signature for item in ordered}
    references = tuple(sorted({item.reference for item in ordered}))
    if len(signatures) > 1:
        return (
            None,
            "conflicted",
            references,
            (
                "multiple provider citation observations disagree on raw count, "
                "non-self count, or exact cutoff",
            ),
        )
    certified = tuple(
        item for item in ordered if item.certification.state == "certified"
    )
    selected = certified[0] if certified else ordered[0]
    return (
        selected,
        selected.certification.state,
        references,
        selected.certification.reasons,
    )


def _coverage(
    kind: EvidenceKind,
    decision_rows: Sequence[Mapping[str, Any]],
    *,
    scope_id: str | None = None,
) -> dict[str, object]:
    relevant = [
        item
        for item in decision_rows
        if item["evidence_kind"] == kind
        and (
            scope_id is None
            or scope_id in cast(Sequence[str], item.get("scope_ids", ()))
        )
    ]
    denominator = sum(
        (
            Fraction(
                cast(int, item["mass"]["numerator"]),
                cast(int, item["mass"]["denominator"]),
            )
            for item in relevant
        ),
        Fraction(0),
    )
    numerator = sum(
        (
            Fraction(
                cast(int, item["mass"]["numerator"]),
                cast(int, item["mass"]["denominator"]),
            )
            for item in relevant
            if item["state"] == "certified"
        ),
        Fraction(0),
    )
    return {
        "evidence_kind": kind,
        "certified_mass": _fraction(numerator),
        "total_mass": _fraction(denominator),
        "ratio": float(numerator / denominator) if denominator else None,
        "decision_count": len(relevant),
    }


def _state_summary(
    kind: EvidenceKind,
    decision_rows: Sequence[Mapping[str, Any]],
    *,
    scope_id: str,
) -> dict[str, object]:
    relevant = [
        item
        for item in decision_rows
        if item["evidence_kind"] == kind
        and scope_id in cast(Sequence[str], item.get("scope_ids", ()))
    ]
    by_state: dict[str, dict[str, object]] = {}
    for state in (
        "certified",
        "needs_review",
        "withheld",
        "conflicted",
        "insufficient_evidence",
    ):
        rows = [item for item in relevant if item["state"] == state]
        mass = sum(
            (
                Fraction(
                    cast(int, item["mass"]["numerator"]),
                    cast(int, item["mass"]["denominator"]),
                )
                for item in rows
            ),
            Fraction(0),
        )
        by_state[state] = {"decision_count": len(rows), "mass": _fraction(mass)}
    return {"evidence_kind": kind, "states": by_state}


def _derive_bundle(
    *,
    raw_root: Path,
    raw_manifest: Mapping[str, Any],
    enrichment_root: Path,
    enrichment_manifest: Mapping[str, Any],
) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    require_validation_runtime()
    official_endpoints = bool(
        raw_manifest.get("provider_endpoints_official") is True
        and enrichment_manifest.get("provider_endpoints_official") is True
    )
    occurrences = _load_occurrences(raw_root, raw_manifest)
    papers = _canonicalize(occurrences)
    check_validation_size(paper_count=len(papers))
    authorities = _authority_bundle(enrichment_root, enrichment_manifest)
    authority_version = institution_authority_version(authorities.records)
    artifacts: dict[str, list[dict[str, object]]] = {
        "source-rows": _source_rows(occurrences),
        "authority-rows": list(authorities.raw_rows),
        "canonical-papers": [],
        "researcher-appearances": [],
        "affiliation-shares": [],
        "field-ledgers": [],
        "citation-observations": [],
        "citation-cohorts": [],
        "decisions": [],
    }
    decision_rows = artifacts["decisions"]
    citation_groups: dict[
        tuple[tuple[str, int, str], datetime], list[CitationObservationCertification]
    ] = defaultdict(list)
    citation_by_paper: dict[str, list[_CitationCandidate]] = defaultdict(list)

    for paper in papers:
        references = tuple(item.page_reference for item in paper.occurrences)
        identity_decision = _make_decision(
            subject_type="paper",
            subject_id=paper.canonical_id,
            kind="canonical-paper-identity",
            state=paper.identity_state,
            rule_version=PAPER_IDENTITY_RULE_VERSION,
            evidence=references,
            reasons=paper.identity_reasons,
        )
        decision_rows.append(_decision_row(identity_decision, mass=Fraction(1)))
        dates = _publication_date_values(paper)
        date_decision = _make_decision(
            subject_type="paper",
            subject_id=paper.canonical_id,
            kind="publication-metric-date",
            state="needs_review" if dates else "insufficient_evidence",
            rule_version=METRIC_DATE_RULE_VERSION,
            evidence=references,
            reasons=(
                "provider date evidence exists but no approved canonical "
                "metric-date decision is present"
                if dates
                else "no provider date evidence is available",
            ),
        )
        decision_rows.append(_decision_row(date_decision, mass=Fraction(1)))
        provenance_decision = _make_decision(
            subject_type="paper",
            subject_id=paper.canonical_id,
            kind="provenance-completeness",
            state="certified",
            rule_version=CERTIFICATION_POLICY_VERSION,
            evidence=references,
        )
        decision_rows.append(_decision_row(provenance_decision, mass=Fraction(1)))

        field_row, field_result = _field_projection(paper)
        artifacts["field-ledgers"].append(field_row)
        field_decision = _make_decision(
            subject_type="paper",
            subject_id=paper.canonical_id,
            kind="field-classification",
            state=field_result.state,
            rule_version=FIELD_CERTIFICATION_RULE_VERSION,
            evidence=references,
            reasons=field_result.reasons,
        )
        decision_rows.append(_decision_row(field_decision, mass=Fraction(1)))
        conservation_exact = (
            cast(Mapping[str, Any], field_row["conservation_total"])["exact"] == "1"
        )
        conservation_decision = _make_decision(
            subject_type="paper",
            subject_id=paper.canonical_id,
            kind="field-weight-conservation",
            state="certified" if conservation_exact else "conflicted",
            rule_version=FIELD_CERTIFICATION_RULE_VERSION,
            evidence=references,
            reasons=()
            if conservation_exact
            else ("exact field mass does not total one",),
        )
        decision_rows.append(_decision_row(conservation_decision, mass=Fraction(1)))

        selected, selection_status = _selected_relationship_occurrence(paper)
        authors_value = (
            selected.normalized.attributes.get("authors") if selected else None
        )
        authors = (
            [item for item in authors_value if isinstance(item, Mapping)]
            if isinstance(authors_value, list)
            else []
        )
        if selected is None or not authors:
            subject = f"unmaterialized:{paper.canonical_id}"
            reasons = (selection_status,)
            for kind, rule in (
                ("researcher-identity", RESEARCHER_PROJECTION_VERSION),
                ("paper-time-affiliation", RELATIONSHIP_PROJECTION_VERSION),
                ("canonical-institution", INSTITUTION_CERTIFICATION_RULE_VERSION),
            ):
                decision = _make_decision(
                    subject_type="paper-relationship-projection",
                    subject_id=subject,
                    kind=cast(EvidenceKind, kind),
                    state="conflicted"
                    if selection_status.startswith("conflicted")
                    else "insufficient_evidence",
                    rule_version=rule,
                    evidence=references,
                    reasons=reasons,
                )
                decision_rows.append(_decision_row(decision, mass=Fraction(1)))
        else:
            author_mass = Fraction(1, len(authors))
            for position, author_value in enumerate(authors, start=1):
                author = cast(Mapping[str, Any], author_value)
                appearance_identity = (
                    paper.canonical_id,
                    selected.occurrence_id,
                    position,
                )
                appearance_id = (
                    f"appearance-{canonical_digest(appearance_identity)[:28]}"
                )
                researcher_ids = _researcher_ids(author)
                values_by_scheme: dict[str, set[str]] = defaultdict(set)
                for scheme, value in researcher_ids:
                    values_by_scheme[scheme].add(value)
                conflicts = tuple(
                    sorted(
                        key
                        for key, values in values_by_scheme.items()
                        if len(values) > 1
                    )
                )
                researcher_state: CertificationState = (
                    "conflicted"
                    if conflicts
                    else "needs_review"
                    if researcher_ids
                    else "insufficient_evidence"
                )
                researcher_reasons = (
                    (
                        "conflicting exact researcher identifiers: "
                        + ", ".join(conflicts),
                    )
                    if conflicts
                    else (
                        "exact identifiers are retained but no approved "
                        "researcher identity review exists",
                    )
                    if researcher_ids
                    else (
                        "author appearance has no exact researcher authority "
                        "identifier",
                    )
                )
                researcher_decision = _make_decision(
                    subject_type="authorship-appearance",
                    subject_id=appearance_id,
                    kind="researcher-identity",
                    state=researcher_state,
                    rule_version=RESEARCHER_PROJECTION_VERSION,
                    evidence=(selected.page_reference,),
                    reasons=researcher_reasons,
                )
                decision_rows.append(
                    _decision_row(researcher_decision, mass=author_mass)
                )
                artifacts["researcher-appearances"].append(
                    {
                        "appearance_id": appearance_id,
                        "canonical_paper_id": paper.canonical_id,
                        "source_occurrence_id": selected.occurrence_id,
                        "selection_status": selection_status,
                        "author_position": position,
                        "raw_name": _author_name(author, position),
                        "exact_identifier_candidates": [
                            {"scheme": scheme, "value": value}
                            for scheme, value in researcher_ids
                        ],
                        "canonical_researcher_id": None,
                        "certification_state": researcher_state,
                        "mass": _fraction(author_mass),
                        "eligible_for_metrics": False,
                    }
                )

                affiliations = _raw_affiliations(author)
                author_rors = _ror_ids(author.get("affiliations_identifiers"))
                (
                    affiliation_crosscheck,
                    crosscheck_references,
                    crosscheck_reasons,
                ) = _lower_precedence_affiliation_crosscheck(paper, selected, author)
                if not affiliations:
                    for kind, rule in (
                        ("paper-time-affiliation", RELATIONSHIP_PROJECTION_VERSION),
                        (
                            "canonical-institution",
                            INSTITUTION_CERTIFICATION_RULE_VERSION,
                        ),
                    ):
                        decision = _make_decision(
                            subject_type="authorship-appearance",
                            subject_id=appearance_id,
                            kind=cast(EvidenceKind, kind),
                            state="insufficient_evidence",
                            rule_version=rule,
                            evidence=(selected.page_reference,),
                            reasons=(
                                "selected paper-time author evidence has no "
                                "affiliation",
                            ),
                        )
                        decision_rows.append(_decision_row(decision, mass=author_mass))
                    artifacts["affiliation-shares"].append(
                        {
                            "share_id": f"unresolved-affiliation-{appearance_id}",
                            "appearance_id": appearance_id,
                            "canonical_paper_id": paper.canonical_id,
                            "raw_affiliation": None,
                            "canonical_institution_id": None,
                            "paper_time_affiliation_state": "insufficient_evidence",
                            "institution_state": "insufficient_evidence",
                            "mass": _fraction(author_mass),
                            "eligible_for_metrics": False,
                        }
                    )
                    continue

                share_mass = author_mass / len(affiliations)
                for affiliation_position, affiliation in enumerate(
                    affiliations, start=1
                ):
                    share_identity = (
                        appearance_id,
                        affiliation_position,
                        affiliation,
                    )
                    share_id = (
                        f"affiliation-share-{canonical_digest(share_identity)[:28]}"
                    )
                    local_rors = _affiliation_rors(affiliation)
                    direct_rors, alignment, same_source_ror_reasons = (
                        _align_affiliation_ror_evidence(
                            local_rors=local_rors,
                            author_rors=author_rors,
                            affiliation_count=len(affiliations),
                        )
                    )
                    affiliation_state: CertificationState
                    if same_source_ror_reasons:
                        affiliation_state = "conflicted"
                    elif affiliation_crosscheck.startswith("needs-review"):
                        affiliation_state = "needs_review"
                    else:
                        affiliation_state = "certified"
                    affiliation_reasons = tuple(
                        dict.fromkeys((*crosscheck_reasons, *same_source_ror_reasons))
                    )
                    affiliation_decision = _make_decision(
                        subject_type="paper-time-affiliation-share",
                        subject_id=share_id,
                        kind="paper-time-affiliation",
                        state=affiliation_state,
                        rule_version=RELATIONSHIP_PROJECTION_VERSION,
                        evidence=(selected.page_reference, *crosscheck_references),
                        reasons=affiliation_reasons,
                    )
                    decision_rows.append(
                        _decision_row(affiliation_decision, mass=share_mass)
                    )
                    provider_institution_id = _provider_institution_id(affiliation)
                    raw_name_value = affiliation.get("value") or affiliation.get("name")
                    raw_name = (
                        " ".join(str(raw_name_value).split())
                        if raw_name_value
                        else None
                    )
                    resolution = InstitutionResolutionEvidence(
                        # The bounded ROR subset is complete for exact IDs followed
                        # by this trial, not for global name uniqueness. Retain the
                        # name in the artifact but never use it to auto-certify.
                        raw_name=None,
                        source_evidence_ids=(selected.page_reference.source_record_id,),
                        source_manifest_digest=cast(
                            str, enrichment_manifest["manifest_checksum"]
                        ),
                        authority_version=authority_version,
                        direct_ror_ids=direct_rors,
                        provider=selected.provider,
                        provider_institution_id=provider_institution_id,
                    )
                    institution_result = certify_institution(
                        resolution,
                        authorities.records,
                        provider_crosswalk=authorities.provider_crosswalk,
                    )
                    name_only_withheld = bool(
                        raw_name
                        and not direct_rors
                        and not (
                            provider_institution_id
                            and (
                                "inspire",
                                provider_institution_id,
                            )
                            in authorities.provider_crosswalk
                        )
                    )
                    institution_state = (
                        "conflicted"
                        if same_source_ror_reasons
                        else institution_result.state
                    )
                    institution_reasons = tuple(
                        dict.fromkeys(
                            (*same_source_ror_reasons, *institution_result.reasons)
                        )
                    )
                    if name_only_withheld:
                        institution_reasons = tuple(
                            dict.fromkeys(
                                (
                                    *institution_reasons,
                                    "name-only resolution is withheld because the "
                                    "bounded ROR subset cannot prove global name "
                                    "uniqueness",
                                )
                            )
                        )
                    authority_references: list[EvidenceReference] = []
                    if provider_institution_id and (
                        ref := authorities.references.get(
                            ("inspire-institution", provider_institution_id)
                        )
                    ):
                        authority_references.append(ref)
                    candidate_rors = set(direct_rors)
                    if provider_institution_id and (
                        crossed := authorities.provider_crosswalk.get(
                            ("inspire", provider_institution_id)
                        )
                    ):
                        candidate_rors.add(crossed)
                    for ror_id in candidate_rors:
                        if ref := authorities.references.get(("ror", ror_id)):
                            authority_references.append(ref)
                    if institution_result.source_institution_id:
                        source_ror = (
                            institution_result.source_institution_id.removeprefix(
                                "institution-ror-"
                            )
                        )
                        if ref := authorities.references.get(("ror", source_ror)):
                            authority_references.append(ref)
                    if institution_result.canonical_institution_id:
                        target_ror = (
                            institution_result.canonical_institution_id.removeprefix(
                                "institution-ror-"
                            )
                        )
                        if ref := authorities.references.get(("ror", target_ror)):
                            authority_references.append(ref)
                    institution_decision = _make_decision(
                        subject_type="paper-time-affiliation-share",
                        subject_id=share_id,
                        kind="canonical-institution",
                        state=institution_state,
                        rule_version=INSTITUTION_CERTIFICATION_RULE_VERSION,
                        evidence=(selected.page_reference, *authority_references),
                        reasons=institution_reasons,
                    )
                    decision_rows.append(
                        _decision_row(institution_decision, mass=share_mass)
                    )
                    artifacts["affiliation-shares"].append(
                        {
                            "share_id": share_id,
                            "appearance_id": appearance_id,
                            "canonical_paper_id": paper.canonical_id,
                            "source_occurrence_id": selected.occurrence_id,
                            "precedence": [
                                "paper-native-inspire",
                                "arxiv-paper-metadata",
                                "orcid-dated-cross-check",
                                "current-homepage-profile-only",
                            ],
                            "selected_precedence_source": selected.provider,
                            "lower_precedence_crosscheck": affiliation_crosscheck,
                            "raw_affiliation": affiliation,
                            "raw_name": raw_name,
                            "name_only_resolution_withheld": name_only_withheld,
                            "institution_authority_version": authority_version,
                            "affiliation_local_ror_ids": list(local_rors),
                            "author_level_ror_ids": list(author_rors),
                            "direct_ror_ids": list(direct_rors),
                            "provider_institution_id": provider_institution_id,
                            "ror_alignment": alignment,
                            "same_source_ror_conflict": bool(same_source_ror_reasons),
                            "paper_time_affiliation_state": affiliation_state,
                            "institution_certifier_rule": (
                                institution_result.rule_version
                            ),
                            "institution_state": institution_state,
                            "canonical_institution_id": (
                                None
                                if same_source_ror_reasons
                                else institution_result.canonical_institution_id
                            ),
                            "candidate_institution_ids": list(
                                institution_result.candidate_institution_ids
                            ),
                            "institution_reasons": list(institution_reasons),
                            "mass": _fraction(share_mass),
                            "eligible_for_metrics": False,
                        }
                    )

        citation_rows, citation_certifications = _citation_rows(paper, field_row)
        artifacts["citation-observations"].extend(citation_rows)
        for certification in citation_certifications:
            assert (
                certification.cohort_key is not None
                and certification.cutoff is not None
            )
            citation_groups[(certification.cohort_key, certification.cutoff)].append(
                certification
            )
            matching = next(
                item
                for item in paper.occurrences
                if item.occurrence_id
                == next(
                    cast(str, row["occurrence_id"])
                    for row in citation_rows
                    if row.get("certification_id") == certification.certification_id
                )
            )
            citation_by_paper[paper.canonical_id].append(
                _CitationCandidate(
                    certification=certification,
                    reference=matching.page_reference,
                    provider=matching.provider,
                    raw_citation_count=_citation_count(
                        matching.record.raw.get("citation_count")
                    ),
                )
            )

        artifacts["canonical-papers"].append(
            {
                "canonical_paper_id": paper.canonical_id,
                "identity_state": paper.identity_state,
                "identity_reasons": list(paper.identity_reasons),
                "strong_identifiers": [
                    {"scheme": scheme, "value": value}
                    for scheme, value in paper.strong_identifiers
                ],
                "source_occurrence_ids": [
                    item.occurrence_id for item in paper.occurrences
                ],
                "source_scopes": sorted({item.scope_id for item in paper.occurrences}),
                "publication_date_candidates": list(dates),
                "canonical_metric_date": None,
                "field_review_certified": False,
                "researcher_identity_review_certified": False,
                "eligible_for_metrics": False,
            }
        )

    for paper in papers:
        candidates = citation_by_paper.get(paper.canonical_id, [])
        (
            _citation_selected,
            citation_state,
            citation_references,
            citation_reasons,
        ) = _select_citation_candidate(candidates)
        if not citation_references:
            citation_references = tuple(
                item.page_reference for item in paper.occurrences
            )
        decision = _make_decision(
            subject_type="paper",
            subject_id=paper.canonical_id,
            kind="citation-observation",
            state=citation_state,
            rule_version=CITATION_CERTIFICATION_RULE_VERSION,
            evidence=citation_references,
            reasons=citation_reasons,
        )
        cutoff = _make_decision(
            subject_type="paper",
            subject_id=paper.canonical_id,
            kind="citation-cutoff-compatibility",
            state=citation_state,
            rule_version=CITATION_CERTIFICATION_RULE_VERSION,
            evidence=citation_references,
            reasons=citation_reasons,
        )
        decision_rows.extend(
            (
                _decision_row(decision, mass=Fraction(1)),
                _decision_row(cutoff, mass=Fraction(1)),
            )
        )

    cohort_results: list[CitationCohortCertification] = []
    for (_key, _cutoff), values in sorted(citation_groups.items(), key=str):
        result = certify_citation_cohort(
            tuple(sorted(values, key=lambda item: item.paper_id)),
            dataset_version=CERTIFICATION_ID,
            acquisition_scope=PAIR_ID,
        )
        cohort_results.append(result)
        artifacts["citation-cohorts"].append(
            {
                "certification_id": result.certification_id,
                "cohort_key": list(result.cohort_key),
                "cutoff": result.cutoff.isoformat(),
                "state": result.state,
                "state_scope": "provider-local cutoff/cohort mechanics only",
                "activation_eligible": False,
                "paper_count": result.paper_count,
                "minimum_paper_count": result.minimum_paper_count,
                "observation_certification_ids": list(
                    result.observation_certification_ids
                ),
                "reasons": list(result.reasons),
            }
        )

    paper_scopes = {
        paper.canonical_id: tuple(sorted({item.scope_id for item in paper.occurrences}))
        for paper in papers
    }
    subject_papers: dict[str, str] = {paper_id: paper_id for paper_id in paper_scopes}
    subject_papers.update(
        {f"unmaterialized:{paper_id}": paper_id for paper_id in paper_scopes}
    )
    subject_papers.update(
        {
            cast(str, row["appearance_id"]): cast(str, row["canonical_paper_id"])
            for row in artifacts["researcher-appearances"]
        }
    )
    subject_papers.update(
        {
            cast(str, row["share_id"]): cast(str, row["canonical_paper_id"])
            for row in artifacts["affiliation-shares"]
        }
    )
    for decision_row in decision_rows:
        subject_id = cast(str, decision_row["subject_id"])
        paper_id = subject_papers.get(subject_id)
        if paper_id is None:
            raise PairedTrialCertificationError(
                "certification decision cannot be assigned to a canonical paper"
            )
        decision_row["canonical_paper_id"] = paper_id
        decision_row["scope_ids"] = list(paper_scopes[paper_id])

    for artifact_rows in artifacts.values():
        artifact_rows.sort(key=lambda item: _canonical_json(item))
    coverage_kinds: tuple[EvidenceKind, ...] = (
        "canonical-paper-identity",
        "publication-metric-date",
        "researcher-identity",
        "paper-time-affiliation",
        "canonical-institution",
        "field-classification",
        "field-weight-conservation",
        "citation-observation",
        "citation-cutoff-compatibility",
        "provenance-completeness",
    )
    coverage_by_scope: list[dict[str, object]] = []
    for scope_id, scope in TRIAL_SCOPE_BY_ID.items():
        scope_papers = [
            paper for paper in papers if scope_id in paper_scopes[paper.canonical_id]
        ]
        coverage_by_scope.append(
            {
                "scope_id": scope_id,
                "atlas_field_id": scope.atlas_field_id,
                "source_occurrence_count": sum(
                    item.scope_id == scope_id for item in occurrences
                ),
                "canonical_paper_count": len(scope_papers),
                "coverage": [
                    _coverage(kind, decision_rows, scope_id=scope_id)
                    for kind in coverage_kinds
                ],
                "decision_state_counts": [
                    _state_summary(kind, decision_rows, scope_id=scope_id)
                    for kind in coverage_kinds
                ],
            }
        )
    shared_papers = tuple(
        sorted(paper_id for paper_id, scopes in paper_scopes.items() if len(scopes) > 1)
    )
    report: dict[str, object] = {
        "report_version": CERTIFICATION_REPORT_VERSION,
        "certification_id": CERTIFICATION_ID,
        "supersedes_certification_id": SUPERSEDED_CERTIFICATION_ID,
        "projection_pipeline_version": PROJECTION_PIPELINE_VERSION,
        "paired_capture_id": PAIR_ID,
        "enrichment_id": ENRICHMENT_ID,
        "raw_manifest_checksum": raw_manifest["manifest_checksum"],
        "enrichment_manifest_checksum": enrichment_manifest["manifest_checksum"],
        "raw_provider_endpoints_official": (
            raw_manifest.get("provider_endpoints_official") is True
        ),
        "enrichment_provider_endpoints_official": (
            enrichment_manifest.get("provider_endpoints_official") is True
        ),
        "provider_endpoints_official": official_endpoints,
        "evidence_environment": (
            "official-provider-capture"
            if official_endpoints
            else "fixture-or-non-official-endpoint"
        ),
        "staging_only": True,
        "database_access": False,
        "database_writes": False,
        "cursor_access": False,
        "network_access": False,
        "public_metric_activation": False,
        "metric_calculation": False,
        "metric_observations_created": 0,
        "certified_complete_years": [],
        "certified_metric_windows": [],
        "source_occurrence_count": len(occurrences),
        "canonical_paper_count": len(papers),
        "shared_canonical_paper_count": len(shared_papers),
        "shared_canonical_paper_ids": list(shared_papers),
        "authority_record_count": len(authorities.records),
        "institution_authority_version": authority_version,
        "citation_observation_count": len(artifacts["citation-observations"]),
        "provider_local_citation_cohort_count": len(cohort_results),
        "provider_local_certified_citation_cohort_count": sum(
            item.state == "certified" for item in cohort_results
        ),
        "activation_eligible_citation_cohort_count": 0,
        "coverage": [_coverage(kind, decision_rows) for kind in coverage_kinds],
        "coverage_by_scope": coverage_by_scope,
        "joint_activation_gate": {
            "state": "withheld",
            "all_five_metrics_withheld": True,
            "reasons": [
                "the seven-day paired trial cannot certify a complete calendar year",
                "no canonical metric-date selection has been reviewed",
                "provider field mappings have not received human field review",
                "researcher identities have not received approved identity review",
                "no metric window or activation manifest was created",
            ],
        },
        "rules_invoked": list(_generator_rule_versions()),
    }
    report["report_digest"] = _checksum(report)
    return artifacts, report


def _jsonl(
    rows: Sequence[Mapping[str, object]], *, validation_decisions: bool = False
) -> bytes:
    if not validation_decisions:
        return b"".join(_canonical_json(row) + b"\n" for row in rows)
    check_validation_size(decision_count=len(rows))
    parts: list[bytes] = []
    byte_count = 0
    for row in rows:
        part = _canonical_json(row) + b"\n"
        byte_count += len(part)
        check_validation_size(decision_bytes=byte_count)
        parts.append(part)
    return b"".join(parts)


def _store_bytes(
    output: Path, role: str, suffix: str, payload: bytes, row_count: int | None
) -> dict[str, object]:
    checksum = _checksum_bytes(payload)
    relative = Path("artifacts") / role / f"{checksum}.{suffix}"
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        if destination.read_bytes() != payload:
            raise PairedTrialCertificationError(
                "content-addressed artifact differs"
            ) from error
    return {
        "role": role,
        "path": relative.as_posix(),
        "checksum": checksum,
        "byte_count": len(payload),
        "row_count": row_count,
        "media_type": "application/x-ndjson"
        if suffix == "jsonl"
        else "application/json",
    }


def _manifest_body(
    raw: Mapping[str, Any],
    enrichment: Mapping[str, Any],
    artifact_entries: list[dict[str, object]],
) -> dict[str, object]:
    official_endpoints = bool(
        raw.get("provider_endpoints_official") is True
        and enrichment.get("provider_endpoints_official") is True
    )
    body: dict[str, object] = {
        "manifest_version": CERTIFICATION_MANIFEST_VERSION,
        "certification_id": CERTIFICATION_ID,
        "supersedes_certification_id": SUPERSEDED_CERTIFICATION_ID,
        "projection_pipeline_version": PROJECTION_PIPELINE_VERSION,
        "generator_rule_versions": list(_generator_rule_versions()),
        "paired_capture_id": PAIR_ID,
        "enrichment_id": ENRICHMENT_ID,
        "raw_manifest_checksum": raw["manifest_checksum"],
        "raw_evidence_set_checksum": raw["evidence_set_checksum"],
        "enrichment_manifest_checksum": enrichment["manifest_checksum"],
        "enrichment_evidence_checksum": enrichment["enrichment_evidence_checksum"],
        "raw_provider_endpoints_official": (
            raw.get("provider_endpoints_official") is True
        ),
        "enrichment_provider_endpoints_official": (
            enrichment.get("provider_endpoints_official") is True
        ),
        "provider_endpoints_official": official_endpoints,
        "evidence_environment": (
            "official-provider-capture"
            if official_endpoints
            else "fixture-or-non-official-endpoint"
        ),
        "input_digest": canonical_digest(
            (raw["manifest_checksum"], enrichment["manifest_checksum"])
        ),
        "staging_only": True,
        "database_access": False,
        "database_writes": False,
        "cursor_access": False,
        "network_access": False,
        "production_scope_registration": False,
        "public_metric_activation": False,
        "metric_calculation": False,
        "metric_observations_created": 0,
        "certified_complete_year_count": 0,
        "certified_metric_window_count": 0,
        "artifacts": artifact_entries,
    }
    body["artifact_set_checksum"] = _checksum(
        [(item["role"], item["checksum"]) for item in artifact_entries]
    )
    return body


def certify_paired_trial(
    *,
    raw_root: Path,
    raw_manifest_path: Path,
    enrichment_root: Path,
    enrichment_manifest_path: Path,
    output: Path,
) -> tuple[dict[str, object], Path]:
    """Write one deterministic, externally staged certification bundle."""

    require_validation_runtime()
    output_root = validate_staging_output(output)
    try:
        raw = verify_paired_capture_manifest(raw_manifest_path, output=raw_root)
        enrichment = verify_paired_enrichment_manifest(
            enrichment_manifest_path,
            output=enrichment_root,
            paired_manifest_path=raw_manifest_path,
        )
    except (
        PairedCaptureSafetyError,
        PairedCaptureVerificationError,
        PairedEnrichmentSafetyError,
        PairedEnrichmentVerificationError,
    ) as error:
        raise PairedTrialCertificationError(
            "paired source evidence failed verification"
        ) from error
    if (
        raw.get("capture_complete") is not True
        or enrichment.get("enrichment_complete") is not True
    ):
        raise PairedTrialCertificationError(
            "paired certification requires complete source evidence"
        )
    artifacts, report = _derive_bundle(
        raw_root=raw_root.resolve(),
        raw_manifest=raw,
        enrichment_root=enrichment_root.resolve(),
        enrichment_manifest=enrichment,
    )
    # Validate the verbose trace before publishing any output artifact.
    decisions = _jsonl(artifacts["decisions"], validation_decisions=True)
    entries = [
        _store_bytes(
            output_root,
            role,
            "jsonl",
            decisions if role == "decisions" else _jsonl(rows),
            len(rows),
        )
        for role, rows in sorted(artifacts.items())
    ]
    entries.append(
        _store_bytes(
            output_root, "report", "json", _canonical_json(report, pretty=True), None
        )
    )
    entries.sort(key=lambda item: cast(str, item["role"]))
    manifest = _manifest_body(raw, enrichment, entries)
    checksum = _checksum(manifest)
    manifest["manifest_checksum"] = checksum
    path = output_root / "manifests" / f"{checksum}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _canonical_json(manifest, pretty=True)
    try:
        with path.open("xb") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        if path.read_bytes() != rendered:
            raise PairedTrialCertificationError(
                "content-addressed manifest differs"
            ) from error
    verify_paired_trial_certification_manifest(
        path,
        output=output_root,
        raw_root=raw_root,
        raw_manifest_path=raw_manifest_path,
        enrichment_root=enrichment_root,
        enrichment_manifest_path=enrichment_manifest_path,
    )
    return manifest, path


def verify_paired_trial_certification_manifest(
    path: Path,
    *,
    output: Path,
    raw_root: Path,
    raw_manifest_path: Path,
    enrichment_root: Path,
    enrichment_manifest_path: Path,
) -> dict[str, Any]:
    """Recompute the bounded certification and compare every preserved byte."""

    require_validation_runtime()
    output_root = output.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(output_root / "manifests")
    except ValueError as error:
        raise PairedTrialCertificationError(
            "certification manifest leaves output"
        ) from error
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PairedTrialCertificationError(
            "certification manifest cannot be read"
        ) from error
    if not isinstance(value, dict):
        raise PairedTrialCertificationError("certification manifest is not an object")
    checksum = value.get("manifest_checksum")
    unsigned = dict(value)
    unsigned.pop("manifest_checksum", None)
    if (
        not _is_sha256(checksum)
        or checksum != _checksum(unsigned)
        or resolved.name != f"{checksum}.json"
    ):
        raise PairedTrialCertificationError(
            "certification manifest checksum is invalid"
        )
    try:
        raw = verify_paired_capture_manifest(raw_manifest_path, output=raw_root)
        enrichment = verify_paired_enrichment_manifest(
            enrichment_manifest_path,
            output=enrichment_root,
            paired_manifest_path=raw_manifest_path,
        )
    except (
        PairedCaptureSafetyError,
        PairedCaptureVerificationError,
        PairedEnrichmentSafetyError,
        PairedEnrichmentVerificationError,
    ) as error:
        raise PairedTrialCertificationError(
            "paired source evidence failed verification"
        ) from error
    artifacts, report = _derive_bundle(
        raw_root=raw_root.resolve(),
        raw_manifest=raw,
        enrichment_root=enrichment_root.resolve(),
        enrichment_manifest=enrichment,
    )
    expected_payloads: dict[str, tuple[bytes, int | None, str]] = {
        role: (
            _jsonl(rows, validation_decisions=role == "decisions"),
            len(rows),
            "application/x-ndjson",
        )
        for role, rows in artifacts.items()
    }
    expected_payloads["report"] = (
        _canonical_json(report, pretty=True),
        None,
        "application/json",
    )
    raw_entries = value.get("artifacts")
    if not isinstance(raw_entries, list) or len(raw_entries) != len(expected_payloads):
        raise PairedTrialCertificationError(
            "certification artifact inventory is incomplete"
        )
    expected_entries: list[dict[str, object]] = []
    roles: set[str] = set()
    for entry in raw_entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("role"), str):
            raise PairedTrialCertificationError(
                "certification artifact entry is malformed"
            )
        role = cast(str, entry["role"])
        if role in roles or role not in expected_payloads:
            raise PairedTrialCertificationError(
                "certification artifact roles are invalid"
            )
        roles.add(role)
        payload, row_count, media_type = expected_payloads[role]
        expected_checksum = _checksum_bytes(payload)
        suffix = "json" if role == "report" else "jsonl"
        expected_path = (
            Path("artifacts") / role / f"{expected_checksum}.{suffix}"
        ).as_posix()
        expected_entry = {
            "role": role,
            "path": expected_path,
            "checksum": expected_checksum,
            "byte_count": len(payload),
            "row_count": row_count,
            "media_type": media_type,
        }
        if dict(entry) != expected_entry:
            raise PairedTrialCertificationError(
                "certification artifact metadata differs from recomputation"
            )
        artifact_path = (output_root / expected_path).resolve()
        try:
            artifact_path.relative_to(output_root / "artifacts")
        except ValueError as error:
            raise PairedTrialCertificationError(
                "certification artifact leaves output"
            ) from error
        try:
            with open_artifact(
                artifact_path,
                role=role,
                checksum=expected_checksum,
                byte_count=len(payload),
                row_count=row_count,
                bundle_root=output_root,
            ) as stream:
                observed = stream.read()
        except (OSError, HistoricalReadError) as error:
            raise PairedTrialCertificationError(
                "certification artifact is missing"
            ) from error
        if observed != payload:
            raise PairedTrialCertificationError(
                "certification artifact differs from recomputation"
            )
        expected_entries.append(expected_entry)
    expected_entries.sort(key=lambda item: cast(str, item["role"]))
    expected_body = _manifest_body(raw, enrichment, expected_entries)
    if unsigned != expected_body:
        raise PairedTrialCertificationError(
            "certification manifest differs from recomputation"
        )
    return value


def certification_plan() -> dict[str, object]:
    return {
        "certification_id": CERTIFICATION_ID,
        "manifest_version": CERTIFICATION_MANIFEST_VERSION,
        "paired_capture_id": PAIR_ID,
        "executed": False,
        "staging_only": True,
        "database_access": False,
        "database_writes": False,
        "cursor_access": False,
        "network_access": False,
        "public_metric_activation": False,
        "metric_calculation": False,
        "metric_observations_created": 0,
        "certified_complete_year_count": 0,
        "certified_metric_window_count": 0,
        "maximum_source_occurrences": MAX_SOURCE_OCCURRENCES,
    }


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path)
    parser.add_argument("--raw-manifest", type=Path)
    parser.add_argument("--enrichment-root", type=Path)
    parser.add_argument("--enrichment-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--certify", action="store_true")
    parser.add_argument("--confirm-certification-id")
    args = parser.parse_args(argv)
    if not args.certify:
        sys.stdout.write(
            json.dumps(certification_plan(), indent=2, sort_keys=True) + "\n"
        )
        return 0
    required = {
        "--raw-root": args.raw_root,
        "--raw-manifest": args.raw_manifest,
        "--enrichment-root": args.enrichment_root,
        "--enrichment-manifest": args.enrichment_manifest,
        "--output": args.output,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error("required with --certify: " + ", ".join(missing))
    if args.confirm_certification_id != CERTIFICATION_ID:
        parser.error(f"--confirm-certification-id must equal {CERTIFICATION_ID}")
    manifest, path = certify_paired_trial(
        raw_root=cast(Path, args.raw_root),
        raw_manifest_path=cast(Path, args.raw_manifest),
        enrichment_root=cast(Path, args.enrichment_root),
        enrichment_manifest_path=cast(Path, args.enrichment_manifest),
        output=cast(Path, args.output),
    )
    sys.stdout.write(
        json.dumps({"manifest_path": str(path), **manifest}, indent=2, sort_keys=True)
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
