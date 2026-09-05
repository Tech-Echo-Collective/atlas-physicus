"""Staging-only exact authority enrichment for the paired January 2020 capture.

The raw paired capture contains exact INSPIRE institution references and some
strictly alignable paper-time ROR identifiers.  This module follows only those
identifiers, preserves each provider response with HTTP lineage, and follows
exact ROR parent relationships.  It performs no search, fuzzy matching,
database access, cursor mutation, certification, metric calculation, or public
activation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse

from .capture_lineage import (
    CaptureTextTransport,
    HttpCaptureLineage,
    LineageProviderHttpTransport,
)
from .config import Settings, get_settings
from .connectors.base import normalize_external_id
from .paired_capture import (
    DOWNSTREAM_TARGET_CAPS,
    PAIR_ID,
    TRIAL_SCOPE_BY_ID,
    PairedCaptureSafetyError,
    PairedCaptureVerificationError,
    validate_staging_output,
    verify_paired_capture_manifest,
)

ENRICHMENT_ID = "physics-paired-certification-2020w03-enrichment-v2"
ENRICHMENT_MANIFEST_VERSION = "physics-paired-authority-enrichment-manifest-v2"
INTERNAL_LIVE_TRANSPORT_ATTESTATION = "internal-lineage-http-transport"
INJECTED_TRANSPORT_ATTESTATION = "injected-transport"
OFFICIAL_INSPIRE_INSTITUTION_BASE_URL = "https://inspirehep.net/api/institutions"
OFFICIAL_ROR_ORGANIZATION_BASE_URL = "https://api.ror.org/v2/organizations"

ProviderRecordKind = Literal["inspire-institution", "ror"]


class PairedEnrichmentSafetyError(ValueError):
    """Raised before an unbounded or scientifically unsafe enrichment."""


class PairedEnrichmentVerificationError(ValueError):
    """Raised when staged enrichment evidence no longer verifies."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _aware_utc(value: datetime, *, label: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PairedEnrichmentSafetyError(f"{label} must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _base_origin(url: str) -> tuple[str, str, int, str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise PairedEnrichmentSafetyError(
            "authority endpoints must be fixed HTTPS base URLs"
        )
    try:
        port = parsed.port or 443
    except ValueError as error:
        raise PairedEnrichmentSafetyError(
            "authority endpoint contains an invalid port"
        ) from error
    return parsed.scheme, host, port, parsed.path.rstrip("/")


def _same_exact_endpoint(observed: str, expected: str) -> bool:
    observed_parsed = urlparse(observed)
    expected_parsed = urlparse(expected)
    try:
        observed_port = observed_parsed.port or 443
        expected_port = expected_parsed.port or 443
    except ValueError:
        return False
    return (
        observed_parsed.scheme == expected_parsed.scheme == "https"
        and (observed_parsed.hostname or "").casefold().rstrip(".")
        == (expected_parsed.hostname or "").casefold().rstrip(".")
        and observed_port == expected_port
        and observed_parsed.path.rstrip("/") == expected_parsed.path.rstrip("/")
        and not observed_parsed.query
        and not observed_parsed.fragment
        and observed_parsed.username is None
        and observed_parsed.password is None
    )


def _record_path(kind: ProviderRecordKind, record_id: str, checksum: str) -> Path:
    return Path("records") / kind / record_id / f"{checksum}.json"


def _paired_root(manifest_path: Path) -> Path:
    resolved = manifest_path.expanduser().resolve()
    if resolved.parent.name != "manifests":
        raise PairedEnrichmentSafetyError(
            "paired manifest must remain in its content-addressed manifest directory"
        )
    return resolved.parent.parent


def _exact_inspire_institution_id(value: object) -> str | None:
    reference: object = value
    if isinstance(value, Mapping):
        reference = value.get("$ref")
    normalized = normalize_external_id("inspire-institution", reference)
    if normalized is None or not normalized[1].isdigit():
        return None
    return normalized[1]


def _ror_ids(values: object) -> tuple[tuple[str, ...], int]:
    if values is None:
        return (), 0
    if not isinstance(values, list):
        raise PairedEnrichmentSafetyError("ROR identifier evidence is malformed")
    valid: set[str] = set()
    invalid = 0
    for item in values:
        if not isinstance(item, Mapping):
            raise PairedEnrichmentSafetyError("ROR identifier row is malformed")
        scheme = str(item.get("schema") or item.get("scheme") or "")
        if scheme.strip().casefold() != "ror":
            continue
        normalized = normalize_external_id("ror", item.get("value"))
        if normalized is None:
            invalid += 1
        else:
            valid.add(normalized[1])
    return tuple(sorted(valid)), invalid


def _author_affiliations(author: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    value = author.get("affiliations")
    if not isinstance(value, list) or not value:
        value = author.get("raw_affiliations")
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise PairedEnrichmentSafetyError(
            "paper-time affiliation evidence is malformed"
        )
    return tuple(cast(Mapping[str, Any], item) for item in value)


@dataclass(frozen=True)
class _BaseScopeTargets:
    scope_id: str
    atlas_field_id: str
    inspire_partition_checksum: str
    inspire_page_checksums: tuple[str, ...]
    institution_ids: tuple[str, ...]
    strict_author_ror_ids: tuple[str, ...]
    invalid_institution_reference_count: int
    invalid_ror_identifier_count: int
    ambiguous_author_ror_alignment_count: int

    def plan_dict(self) -> dict[str, object]:
        return {
            "scope_id": self.scope_id,
            "atlas_field_id": self.atlas_field_id,
            "inspire_partition_checksum": self.inspire_partition_checksum,
            "inspire_page_checksums": list(self.inspire_page_checksums),
            "inspire_institution_target_count": len(self.institution_ids),
            "inspire_institution_target_ids": list(self.institution_ids),
            "strict_author_ror_target_count": len(self.strict_author_ror_ids),
            "strict_author_ror_target_ids": list(self.strict_author_ror_ids),
            "invalid_institution_reference_count": (
                self.invalid_institution_reference_count
            ),
            "invalid_ror_identifier_count": self.invalid_ror_identifier_count,
            "ambiguous_author_ror_alignment_count": (
                self.ambiguous_author_ror_alignment_count
            ),
        }


def _derive_base_targets(
    paired_manifest_path: Path,
) -> tuple[dict[str, Any], tuple[_BaseScopeTargets, ...]]:
    paired_root = _paired_root(paired_manifest_path)
    try:
        paired = verify_paired_capture_manifest(
            paired_manifest_path.expanduser().resolve(), output=paired_root
        )
    except (PairedCaptureSafetyError, PairedCaptureVerificationError) as error:
        raise PairedEnrichmentVerificationError(
            "paired capture manifest or pages failed verification"
        ) from error
    if paired.get("capture_complete") is not True:
        raise PairedEnrichmentSafetyError(
            "authority enrichment requires the complete paired capture"
        )

    targets: list[_BaseScopeTargets] = []
    for raw_partition in paired["partitions"]:
        if raw_partition.get("provider") != "inspire":
            continue
        scope_id = raw_partition.get("scope_id")
        atlas_field_id = raw_partition.get("atlas_field_id")
        partition_checksum = raw_partition.get("partition_checksum")
        pages = raw_partition.get("pages")
        if (
            not isinstance(scope_id, str)
            or scope_id not in TRIAL_SCOPE_BY_ID
            or not isinstance(atlas_field_id, str)
            or not isinstance(partition_checksum, str)
            or not isinstance(pages, list)
        ):
            raise PairedEnrichmentVerificationError(
                "paired INSPIRE partition is malformed"
            )
        institution_ids: set[str] = set()
        strict_ror_ids: set[str] = set()
        invalid_institution_refs = 0
        invalid_rors = 0
        ambiguous_alignments = 0
        page_checksums: list[str] = []
        for raw_page in pages:
            if not isinstance(raw_page, Mapping):
                raise PairedEnrichmentVerificationError("paired page is malformed")
            path_value = raw_page.get("path")
            page_checksum = raw_page.get("checksum")
            record_count = raw_page.get("record_count")
            if (
                not isinstance(path_value, str)
                or not isinstance(page_checksum, str)
                or isinstance(record_count, bool)
                or not isinstance(record_count, int)
            ):
                raise PairedEnrichmentVerificationError(
                    "paired INSPIRE page metadata is incomplete"
                )
            page_checksums.append(page_checksum)
            try:
                page = json.loads(
                    (paired_root / path_value).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as error:
                raise PairedEnrichmentVerificationError(
                    "paired INSPIRE page cannot be parsed"
                ) from error
            hits = page.get("hits", {}).get("hits") if isinstance(page, dict) else None
            if not isinstance(hits, list) or len(hits) != record_count:
                raise PairedEnrichmentVerificationError(
                    "paired INSPIRE record count no longer reconciles"
                )
            for hit in hits:
                metadata = hit.get("metadata") if isinstance(hit, Mapping) else None
                if not isinstance(metadata, Mapping):
                    raise PairedEnrichmentVerificationError(
                        "paired INSPIRE record lacks metadata"
                    )
                authors = metadata.get("authors", [])
                if not isinstance(authors, list) or any(
                    not isinstance(author, Mapping) for author in authors
                ):
                    raise PairedEnrichmentVerificationError(
                        "paired INSPIRE author evidence is malformed"
                    )
                for author_value in authors:
                    author = cast(Mapping[str, Any], author_value)
                    affiliations = _author_affiliations(author)
                    author_rors, invalid = _ror_ids(
                        author.get("affiliations_identifiers")
                    )
                    invalid_rors += invalid
                    for affiliation in affiliations:
                        record = affiliation.get("record")
                        if record is not None:
                            institution_id = _exact_inspire_institution_id(record)
                            if institution_id is None:
                                invalid_institution_refs += 1
                            else:
                                institution_ids.add(institution_id)
                        local_rors: set[str] = set()
                        for key in ("identifiers", "external_ids", "externalIds"):
                            observed, invalid = _ror_ids(affiliation.get(key))
                            local_rors.update(observed)
                            invalid_rors += invalid
                        aligned: str | None = None
                        if len(local_rors) == 1:
                            aligned = next(iter(local_rors))
                        elif len(local_rors) > 1:
                            ambiguous_alignments += 1
                        elif len(affiliations) == 1 and len(author_rors) == 1:
                            aligned = author_rors[0]
                        elif author_rors:
                            ambiguous_alignments += 1
                        if aligned is not None:
                            strict_ror_ids.add(aligned)
        DOWNSTREAM_TARGET_CAPS.validate(
            paper_lookups=0,
            institution_recids=len(institution_ids),
            child_ror_records=0,
            parent_ror_records=0,
        )
        targets.append(
            _BaseScopeTargets(
                scope_id=scope_id,
                atlas_field_id=atlas_field_id,
                inspire_partition_checksum=partition_checksum,
                inspire_page_checksums=tuple(page_checksums),
                institution_ids=tuple(sorted(institution_ids)),
                strict_author_ror_ids=tuple(sorted(strict_ror_ids)),
                invalid_institution_reference_count=invalid_institution_refs,
                invalid_ror_identifier_count=invalid_rors,
                ambiguous_author_ror_alignment_count=ambiguous_alignments,
            )
        )
    if len(targets) != 2:
        raise PairedEnrichmentVerificationError(
            "paired capture does not contain both INSPIRE trial scopes"
        )
    return paired, tuple(targets)


@dataclass(frozen=True)
class _FetchedRecord:
    metadata: dict[str, object]
    raw: dict[str, Any]


def _organization_document(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    items = payload.get("items")
    if items is None:
        return payload
    if (
        not isinstance(items, list)
        or len(items) != 1
        or not isinstance(items[0], Mapping)
    ):
        raise PairedEnrichmentSafetyError("ROR exact response is not one organization")
    return cast(Mapping[str, Any], items[0])


def _validate_exact_payload(
    kind: ProviderRecordKind,
    record_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if kind == "inspire-institution":
        metadata = payload.get("metadata")
        if not isinstance(metadata, Mapping):
            raise PairedEnrichmentSafetyError(
                f"INSPIRE institution response {record_id} lacks metadata"
            )
        observed = payload.get("id")
        control_number = metadata.get("control_number")
        if str(observed) != record_id or str(control_number) != record_id:
            raise PairedEnrichmentSafetyError(
                f"INSPIRE institution response did not match target {record_id}"
            )
        return dict(payload)
    organization = _organization_document(payload)
    observed = normalize_external_id("ror", organization.get("id"))
    if observed != ("ror", record_id):
        raise PairedEnrichmentSafetyError(
            f"ROR response did not match exact target {record_id}"
        )
    return dict(organization)


def _capture_exact_record(
    *,
    transport: CaptureTextTransport,
    output: Path,
    kind: ProviderRecordKind,
    record_id: str,
    base_url: str,
    paired_manifest_checksum: str,
) -> _FetchedRecord:
    expected_url = f"{base_url.rstrip('/')}/{record_id}"
    response = transport.get_captured_text(expected_url)
    if (
        response.lineage.status_code != 200
        or not _same_exact_endpoint(response.lineage.request_url, expected_url)
        or not _same_exact_endpoint(response.lineage.response_url, expected_url)
    ):
        raise PairedEnrichmentSafetyError(
            f"{kind} HTTP lineage did not remain on exact target {record_id}"
        )
    try:
        parsed = json.loads(response.body)
    except json.JSONDecodeError as error:
        raise PairedEnrichmentSafetyError(
            f"{kind} response {record_id} is malformed JSON"
        ) from error
    if not isinstance(parsed, dict):
        raise PairedEnrichmentSafetyError(
            f"{kind} response {record_id} is not an object"
        )
    raw = _validate_exact_payload(kind, record_id, parsed)
    payload = response.body.encode("utf-8")
    checksum = hashlib.sha256(payload).hexdigest()
    relative = _record_path(kind, record_id, checksum)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        if destination.read_bytes() != payload:
            raise PairedEnrichmentVerificationError(
                "content-addressed authority record contains different bytes"
            ) from error
    metadata: dict[str, object] = {
        "provider": "inspire" if kind == "inspire-institution" else "ror",
        "record_kind": kind,
        "source_record_id": record_id,
        "path": relative.as_posix(),
        "checksum": checksum,
        "http_lineage": response.lineage.as_dict(),
        "paired_manifest_checksum": paired_manifest_checksum,
    }
    return _FetchedRecord(metadata=metadata, raw=raw)


def _inspire_record_ror_ids(raw: Mapping[str, Any]) -> tuple[tuple[str, ...], int]:
    metadata = raw.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedEnrichmentSafetyError("INSPIRE institution metadata is malformed")
    return _ror_ids(metadata.get("external_system_identifiers"))


def _ror_parent_ids(raw: Mapping[str, Any]) -> tuple[tuple[str, ...], int]:
    relationships = raw.get("relationships", [])
    if relationships is None:
        return (), 0
    if not isinstance(relationships, list):
        raise PairedEnrichmentSafetyError("ROR relationship evidence is malformed")
    result: set[str] = set()
    invalid = 0
    for relationship in relationships:
        if not isinstance(relationship, Mapping):
            raise PairedEnrichmentSafetyError("ROR relationship row is malformed")
        if str(relationship.get("type", "")).strip().casefold() != "parent":
            continue
        normalized = normalize_external_id("ror", relationship.get("id"))
        if normalized is None:
            invalid += 1
        else:
            result.add(normalized[1])
    return tuple(sorted(result)), invalid


def _record_status(raw: Mapping[str, Any]) -> str:
    return str(raw.get("status") or "unknown").strip().casefold()


def enrichment_plan(paired_manifest_path: Path) -> dict[str, object]:
    paired, targets = _derive_base_targets(paired_manifest_path)
    return {
        "enrichment_id": ENRICHMENT_ID,
        "manifest_version": ENRICHMENT_MANIFEST_VERSION,
        "paired_capture_id": PAIR_ID,
        "paired_manifest_checksum": paired["manifest_checksum"],
        "executed": False,
        "staging_only": True,
        "database_access": False,
        "database_writes": False,
        "cursor_access": False,
        "metric_calculation": False,
        "public_metric_activation": False,
        "registry_search": False,
        "name_matching": False,
        "downstream_target_caps": DOWNSTREAM_TARGET_CAPS.as_dict(),
        "scopes": [item.plan_dict() for item in targets],
    }


def _write_manifest(output: Path, value: dict[str, object]) -> Path:
    checksum = _checksum(value)
    value["manifest_checksum"] = checksum
    destination = output / "manifests" / f"{checksum}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    except FileExistsError as error:
        if destination.read_text(encoding="utf-8") != rendered:
            raise PairedEnrichmentVerificationError(
                "content-addressed enrichment manifest differs"
            ) from error
    return destination


def _scope_manifest(
    base: _BaseScopeTargets,
    *,
    institution_records: Mapping[str, _FetchedRecord],
    child_records: Mapping[str, _FetchedRecord],
    parent_records: Mapping[str, _FetchedRecord],
) -> dict[str, object]:
    institution_rors: set[str] = set()
    invalid_institution_rors = 0
    institutions_without_ror = 0
    institutions_with_multiple_rors = 0
    for record_id in base.institution_ids:
        rors, invalid = _inspire_record_ror_ids(institution_records[record_id].raw)
        invalid_institution_rors += invalid
        institution_rors.update(rors)
        if not rors:
            institutions_without_ror += 1
        elif len(rors) > 1:
            institutions_with_multiple_rors += 1

    child_ids = tuple(sorted(set(base.strict_author_ror_ids) | institution_rors))
    DOWNSTREAM_TARGET_CAPS.validate(
        paper_lookups=0,
        institution_recids=len(base.institution_ids),
        child_ror_records=len(child_ids),
        parent_ror_records=0,
    )
    parent_ids: set[str] = set()
    invalid_parent_rors = 0
    inactive_children = 0
    multiple_parent_children = 0
    for ror_id in child_ids:
        raw = child_records[ror_id].raw
        if _record_status(raw) != "active":
            inactive_children += 1
            continue
        observed, invalid = _ror_parent_ids(raw)
        invalid_parent_rors += invalid
        parent_ids.update(observed)
        if len(observed) > 1:
            multiple_parent_children += 1
    ordered_parent_ids = tuple(sorted(parent_ids))
    DOWNSTREAM_TARGET_CAPS.validate(
        paper_lookups=0,
        institution_recids=len(base.institution_ids),
        child_ror_records=len(child_ids),
        parent_ror_records=len(ordered_parent_ids),
    )
    active_parents = tuple(
        ror_id
        for ror_id in ordered_parent_ids
        if _record_status(parent_records[ror_id].raw) == "active"
    )
    inactive_parents = tuple(
        ror_id for ror_id in ordered_parent_ids if ror_id not in set(active_parents)
    )
    body: dict[str, object] = {
        **base.plan_dict(),
        "institution_record_ror_target_count": len(institution_rors),
        "institution_record_ror_target_ids": sorted(institution_rors),
        "child_ror_target_count": len(child_ids),
        "child_ror_target_ids": list(child_ids),
        "parent_ror_relationship_target_count": len(ordered_parent_ids),
        "parent_ror_relationship_target_ids": list(ordered_parent_ids),
        "active_parent_ror_count": len(active_parents),
        "active_parent_ror_ids": list(active_parents),
        "inactive_parent_ror_count": len(inactive_parents),
        "inactive_parent_ror_ids": list(inactive_parents),
        "invalid_institution_record_ror_count": invalid_institution_rors,
        "institutions_without_explicit_ror_count": institutions_without_ror,
        "institutions_with_multiple_explicit_rors_count": (
            institutions_with_multiple_rors
        ),
        "inactive_child_ror_count": inactive_children,
        "children_with_multiple_parent_rors_count": multiple_parent_children,
        "invalid_parent_ror_count": invalid_parent_rors,
    }
    body["scope_checksum"] = _checksum(body)
    return body


def _execute_with_transport(
    *,
    paired_manifest_path: Path,
    output: Path,
    transport: CaptureTextTransport,
    inspire_base_url: str,
    ror_base_url: str,
    completed_at: datetime | None,
    transport_attestation: str,
) -> tuple[dict[str, object], Path]:
    paired, base_targets = _derive_base_targets(paired_manifest_path)
    paired_checksum = cast(str, paired["manifest_checksum"])

    institution_ids = sorted(
        {record_id for scope in base_targets for record_id in scope.institution_ids}
    )
    institution_records = {
        record_id: _capture_exact_record(
            transport=transport,
            output=output,
            kind="inspire-institution",
            record_id=record_id,
            base_url=inspire_base_url,
            paired_manifest_checksum=paired_checksum,
        )
        for record_id in institution_ids
    }

    child_ids_by_scope: dict[str, tuple[str, ...]] = {}
    for base in base_targets:
        institution_rors: set[str] = set()
        for record_id in base.institution_ids:
            observed, _invalid = _inspire_record_ror_ids(
                institution_records[record_id].raw
            )
            institution_rors.update(observed)
        child_ids = tuple(sorted(set(base.strict_author_ror_ids) | institution_rors))
        DOWNSTREAM_TARGET_CAPS.validate(
            paper_lookups=0,
            institution_recids=len(base.institution_ids),
            child_ror_records=len(child_ids),
            parent_ror_records=0,
        )
        child_ids_by_scope[base.scope_id] = child_ids

    all_child_ids = sorted(
        {record_id for values in child_ids_by_scope.values() for record_id in values}
    )
    child_records = {
        record_id: _capture_exact_record(
            transport=transport,
            output=output,
            kind="ror",
            record_id=record_id,
            base_url=ror_base_url,
            paired_manifest_checksum=paired_checksum,
        )
        for record_id in all_child_ids
    }

    parent_ids_by_scope: dict[str, tuple[str, ...]] = {}
    for base in base_targets:
        parent_ids: set[str] = set()
        for record_id in child_ids_by_scope[base.scope_id]:
            raw = child_records[record_id].raw
            if _record_status(raw) == "active":
                observed, _invalid = _ror_parent_ids(raw)
                parent_ids.update(observed)
        ordered = tuple(sorted(parent_ids))
        DOWNSTREAM_TARGET_CAPS.validate(
            paper_lookups=0,
            institution_recids=len(base.institution_ids),
            child_ror_records=len(child_ids_by_scope[base.scope_id]),
            parent_ror_records=len(ordered),
        )
        parent_ids_by_scope[base.scope_id] = ordered

    all_parent_ids = sorted(
        {record_id for values in parent_ids_by_scope.values() for record_id in values}
    )
    ror_cache = dict(child_records)
    for record_id in all_parent_ids:
        if record_id not in ror_cache:
            ror_cache[record_id] = _capture_exact_record(
                transport=transport,
                output=output,
                kind="ror",
                record_id=record_id,
                base_url=ror_base_url,
                paired_manifest_checksum=paired_checksum,
            )
    parent_records = {record_id: ror_cache[record_id] for record_id in all_parent_ids}

    scope_documents = [
        _scope_manifest(
            base,
            institution_records=institution_records,
            child_records=child_records,
            parent_records=parent_records,
        )
        for base in base_targets
    ]
    scope_checksums = [cast(str, item["scope_checksum"]) for item in scope_documents]
    institution_metadata = [
        institution_records[item].metadata for item in institution_ids
    ]
    child_metadata = [child_records[item].metadata for item in all_child_ids]
    parent_metadata = [parent_records[item].metadata for item in all_parent_ids]
    evidence_identity = {
        "paired_manifest_checksum": paired_checksum,
        "scope_checksums": scope_checksums,
        "record_checksums": sorted(
            {
                cast(str, item["checksum"])
                for item in [
                    *institution_metadata,
                    *child_metadata,
                    *parent_metadata,
                ]
            }
        ),
    }
    completion_time = completed_at or datetime.now(UTC)
    manifest: dict[str, object] = {
        "manifest_version": ENRICHMENT_MANIFEST_VERSION,
        "enrichment_id": ENRICHMENT_ID,
        "paired_capture_id": PAIR_ID,
        "paired_manifest_checksum": paired_checksum,
        "paired_evidence_set_checksum": paired["evidence_set_checksum"],
        "completed_at": _aware_utc(completion_time, label="completed_at"),
        "staging_only": True,
        "database_access": False,
        "database_writes": False,
        "cursor_access": False,
        "metric_calculation": False,
        "metric_observations_created": 0,
        "public_metric_activation": False,
        "registry_search": False,
        "name_matching": False,
        "positional_identifier_join": False,
        "transport_attestation": transport_attestation,
        "provider_endpoints_official": (
            transport_attestation == INTERNAL_LIVE_TRANSPORT_ATTESTATION
            and inspire_base_url == OFFICIAL_INSPIRE_INSTITUTION_BASE_URL
            and ror_base_url == OFFICIAL_ROR_ORGANIZATION_BASE_URL
        ),
        "inspire_institution_base_url": inspire_base_url,
        "ror_organization_base_url": ror_base_url,
        "downstream_target_caps": DOWNSTREAM_TARGET_CAPS.as_dict(),
        "scope_checksums": scope_checksums,
        "scopes": scope_documents,
        "records": {
            "inspire_institutions": institution_metadata,
            "child_ror": child_metadata,
            "parent_ror": parent_metadata,
        },
        "unique_inspire_institution_fetch_count": len(institution_metadata),
        "unique_ror_fetch_count": len(ror_cache),
        "enrichment_evidence_checksum": _checksum(evidence_identity),
        "enrichment_complete": True,
    }
    path = _write_manifest(output, manifest)
    return manifest, path


def execute_paired_enrichment(
    *,
    paired_manifest_path: Path,
    output: Path,
    transport: CaptureTextTransport | None = None,
    inspire_base_url: str = OFFICIAL_INSPIRE_INSTITUTION_BASE_URL,
    ror_base_url: str = OFFICIAL_ROR_ORGANIZATION_BASE_URL,
    completed_at: datetime | None = None,
    settings: Settings | None = None,
) -> tuple[dict[str, object], Path]:
    """Fetch every exact bounded authority target or fail without a final manifest."""

    _base_origin(inspire_base_url)
    _base_origin(ror_base_url)
    output_root = validate_staging_output(output)
    if transport is None and (
        inspire_base_url != OFFICIAL_INSPIRE_INSTITUTION_BASE_URL
        or ror_base_url != OFFICIAL_ROR_ORGANIZATION_BASE_URL
    ):
        raise PairedEnrichmentSafetyError(
            "live enrichment is restricted to official provider endpoints"
        )
    if transport is not None:
        return _execute_with_transport(
            paired_manifest_path=paired_manifest_path,
            output=output_root,
            transport=transport,
            inspire_base_url=inspire_base_url,
            ror_base_url=ror_base_url,
            completed_at=completed_at,
            transport_attestation=INJECTED_TRANSPORT_ATTESTATION,
        )
    active_settings = settings or get_settings()
    hosts = {
        cast(str, urlparse(inspire_base_url).hostname),
        cast(str, urlparse(ror_base_url).hostname),
    }
    with LineageProviderHttpTransport(
        timeout_seconds=active_settings.provider_timeout_seconds,
        allowed_hosts=hosts,
        minimum_intervals={
            cast(str, urlparse(inspire_base_url).hostname): 1.0,
            cast(str, urlparse(ror_base_url).hostname): 0.2,
        },
    ) as active_transport:
        return _execute_with_transport(
            paired_manifest_path=paired_manifest_path,
            output=output_root,
            transport=active_transport,
            inspire_base_url=inspire_base_url,
            ror_base_url=ror_base_url,
            completed_at=completed_at,
            transport_attestation=INTERNAL_LIVE_TRANSPORT_ATTESTATION,
        )


def _load_manifest(path: Path, output: Path) -> dict[str, Any]:
    resolved_path = path.expanduser().resolve()
    resolved_output = output.expanduser().resolve()
    if not _is_within(resolved_path, resolved_output / "manifests"):
        raise PairedEnrichmentVerificationError(
            "enrichment manifest is outside its evidence directory"
        )
    try:
        value = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PairedEnrichmentVerificationError(
            "enrichment manifest cannot be read"
        ) from error
    if not isinstance(value, dict):
        raise PairedEnrichmentVerificationError("enrichment manifest is not an object")
    checksum = value.get("manifest_checksum")
    unsigned = dict(value)
    unsigned.pop("manifest_checksum", None)
    if (
        not _is_sha256(checksum)
        or checksum != _checksum(unsigned)
        or resolved_path.name != f"{checksum}.json"
    ):
        raise PairedEnrichmentVerificationError(
            "enrichment manifest checksum is invalid"
        )
    return value


def _verified_record(
    output: Path,
    metadata: Mapping[str, Any],
    *,
    kind: ProviderRecordKind,
    base_url: str,
    paired_checksum: str,
) -> _FetchedRecord:
    record_id = metadata.get("source_record_id")
    checksum = metadata.get("checksum")
    path_value = metadata.get("path")
    lineage_value = metadata.get("http_lineage")
    if (
        not isinstance(record_id, str)
        or not isinstance(checksum, str)
        or not isinstance(path_value, str)
        or not isinstance(lineage_value, Mapping)
        or metadata.get("record_kind") != kind
        or metadata.get("paired_manifest_checksum") != paired_checksum
        or Path(path_value) != _record_path(kind, record_id, checksum)
    ):
        raise PairedEnrichmentVerificationError(f"{kind} record metadata is malformed")
    path = (output / path_value).resolve()
    if not _is_within(path, output / "records"):
        raise PairedEnrichmentVerificationError("authority record leaves output")
    try:
        body = path.read_bytes()
    except OSError as error:
        raise PairedEnrichmentVerificationError(
            "authority record is missing"
        ) from error
    if hashlib.sha256(body).hexdigest() != checksum:
        raise PairedEnrichmentVerificationError("authority record checksum is invalid")
    try:
        parsed = json.loads(body)
        started = datetime.fromisoformat(str(lineage_value["request_started_at"]))
        received = datetime.fromisoformat(str(lineage_value["response_received_at"]))
        lineage = HttpCaptureLineage(
            request_started_at=started,
            response_received_at=received,
            request_url=str(lineage_value["request_url"]),
            response_url=str(lineage_value["response_url"]),
            status_code=int(lineage_value["status_code"]),
            provider_date=cast(str | None, lineage_value.get("provider_date")),
            etag=cast(str | None, lineage_value.get("etag")),
            last_modified=cast(str | None, lineage_value.get("last_modified")),
            content_type=cast(str | None, lineage_value.get("content_type")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PairedEnrichmentVerificationError(
            "authority record or HTTP lineage is invalid"
        ) from error
    if not isinstance(parsed, dict):
        raise PairedEnrichmentVerificationError("authority record is not an object")
    expected_url = f"{base_url.rstrip('/')}/{record_id}"
    if (
        lineage.status_code != 200
        or not _same_exact_endpoint(lineage.request_url, expected_url)
        or not _same_exact_endpoint(lineage.response_url, expected_url)
    ):
        raise PairedEnrichmentVerificationError(
            "authority record HTTP lineage changed exact target"
        )
    try:
        raw = _validate_exact_payload(kind, record_id, parsed)
    except PairedEnrichmentSafetyError as error:
        raise PairedEnrichmentVerificationError(
            "authority record identity is invalid"
        ) from error
    return _FetchedRecord(metadata=dict(metadata), raw=raw)


def verify_paired_enrichment_manifest(
    path: Path,
    *,
    output: Path,
    paired_manifest_path: Path,
) -> dict[str, Any]:
    """Re-derive every target and verify all immutable response evidence."""

    output_root = output.expanduser().resolve()
    value = _load_manifest(path, output_root)
    paired, base_targets = _derive_base_targets(paired_manifest_path)
    paired_checksum = paired["manifest_checksum"]
    required = {
        "manifest_version": ENRICHMENT_MANIFEST_VERSION,
        "enrichment_id": ENRICHMENT_ID,
        "paired_capture_id": PAIR_ID,
        "paired_manifest_checksum": paired_checksum,
        "paired_evidence_set_checksum": paired["evidence_set_checksum"],
        "staging_only": True,
        "database_access": False,
        "database_writes": False,
        "cursor_access": False,
        "metric_calculation": False,
        "metric_observations_created": 0,
        "public_metric_activation": False,
        "registry_search": False,
        "name_matching": False,
        "positional_identifier_join": False,
        "downstream_target_caps": DOWNSTREAM_TARGET_CAPS.as_dict(),
        "enrichment_complete": True,
    }
    if any(value.get(key) != expected for key, expected in required.items()):
        raise PairedEnrichmentVerificationError(
            "enrichment identity or safety flags changed"
        )
    try:
        completed = datetime.fromisoformat(str(value["completed_at"]))
    except (KeyError, ValueError) as error:
        raise PairedEnrichmentVerificationError(
            "enrichment completion timestamp is invalid"
        ) from error
    if completed.tzinfo is None or completed.utcoffset() is None:
        raise PairedEnrichmentVerificationError(
            "enrichment completion timestamp is not timezone-aware"
        )
    inspire_base = value.get("inspire_institution_base_url")
    ror_base = value.get("ror_organization_base_url")
    if not isinstance(inspire_base, str) or not isinstance(ror_base, str):
        raise PairedEnrichmentVerificationError("authority endpoints are missing")
    try:
        _base_origin(inspire_base)
        _base_origin(ror_base)
    except PairedEnrichmentSafetyError as error:
        raise PairedEnrichmentVerificationError(
            "authority endpoint is invalid"
        ) from error
    transport_attestation = value.get("transport_attestation")
    if transport_attestation not in {
        INTERNAL_LIVE_TRANSPORT_ATTESTATION,
        INJECTED_TRANSPORT_ATTESTATION,
    }:
        raise PairedEnrichmentVerificationError(
            "authority transport attestation is invalid"
        )
    official = (
        transport_attestation == INTERNAL_LIVE_TRANSPORT_ATTESTATION
        and inspire_base == OFFICIAL_INSPIRE_INSTITUTION_BASE_URL
        and ror_base == OFFICIAL_ROR_ORGANIZATION_BASE_URL
    )
    if value.get("provider_endpoints_official") is not official:
        raise PairedEnrichmentVerificationError(
            "authority endpoint classification is invalid"
        )
    records = value.get("records")
    if not isinstance(records, Mapping):
        raise PairedEnrichmentVerificationError("enrichment records are malformed")

    def record_map(
        role: str, kind: ProviderRecordKind, base_url: str
    ) -> dict[str, _FetchedRecord]:
        rows = records.get(role)
        if not isinstance(rows, list) or any(
            not isinstance(row, Mapping) for row in rows
        ):
            raise PairedEnrichmentVerificationError(f"{role} record list is malformed")
        result: dict[str, _FetchedRecord] = {}
        for row in rows:
            verified = _verified_record(
                output_root,
                cast(Mapping[str, Any], row),
                kind=kind,
                base_url=base_url,
                paired_checksum=cast(str, paired_checksum),
            )
            record_id = cast(str, row["source_record_id"])
            if record_id in result:
                raise PairedEnrichmentVerificationError(
                    f"{role} contains a duplicate authority record"
                )
            result[record_id] = verified
        if list(result) != sorted(result):
            raise PairedEnrichmentVerificationError(
                f"{role} authority records are not ordered"
            )
        return result

    institution_records = record_map(
        "inspire_institutions", "inspire-institution", inspire_base
    )
    child_records = record_map("child_ror", "ror", ror_base)
    parent_records = record_map("parent_ror", "ror", ror_base)
    response_times: list[datetime] = []
    for record in (
        *institution_records.values(),
        *child_records.values(),
        *parent_records.values(),
    ):
        lineage = record.metadata.get("http_lineage")
        if not isinstance(lineage, Mapping):
            raise PairedEnrichmentVerificationError(
                "authority record HTTP lineage is missing"
            )
        try:
            response_times.append(
                datetime.fromisoformat(str(lineage["response_received_at"]))
            )
        except (KeyError, ValueError) as error:
            raise PairedEnrichmentVerificationError(
                "authority response timestamp is invalid"
            ) from error
    if any(response_time > completed for response_time in response_times):
        raise PairedEnrichmentVerificationError(
            "enrichment completion predates an authority response"
        )
    expected_institutions = sorted(
        {record_id for base in base_targets for record_id in base.institution_ids}
    )
    if sorted(institution_records) != expected_institutions:
        raise PairedEnrichmentVerificationError(
            "INSPIRE institution acquisition does not cover exact base targets"
        )

    expected_scopes = [
        _scope_manifest(
            base,
            institution_records=institution_records,
            child_records=child_records,
            parent_records=parent_records,
        )
        for base in base_targets
    ]
    scopes = value.get("scopes")
    if scopes != expected_scopes:
        raise PairedEnrichmentVerificationError(
            "enrichment scope targets do not re-derive from preserved evidence"
        )
    expected_children = sorted(
        {
            item
            for scope in expected_scopes
            for item in cast(list[str], scope["child_ror_target_ids"])
        }
    )
    expected_parents = sorted(
        {
            item
            for scope in expected_scopes
            for item in cast(list[str], scope["parent_ror_relationship_target_ids"])
        }
    )
    if (
        sorted(child_records) != expected_children
        or sorted(parent_records) != expected_parents
    ):
        raise PairedEnrichmentVerificationError(
            "ROR acquisition does not cover exact child and parent targets"
        )
    scope_checksums = [cast(str, item["scope_checksum"]) for item in expected_scopes]
    if value.get("scope_checksums") != scope_checksums:
        raise PairedEnrichmentVerificationError("scope checksum binding is invalid")
    record_rows = [
        *cast(list[Mapping[str, object]], records["inspire_institutions"]),
        *cast(list[Mapping[str, object]], records["child_ror"]),
        *cast(list[Mapping[str, object]], records["parent_ror"]),
    ]
    evidence_identity = {
        "paired_manifest_checksum": paired_checksum,
        "scope_checksums": scope_checksums,
        "record_checksums": sorted(
            {cast(str, item["checksum"]) for item in record_rows}
        ),
    }
    if value.get("enrichment_evidence_checksum") != _checksum(evidence_identity):
        raise PairedEnrichmentVerificationError(
            "enrichment evidence checksum binding is invalid"
        )
    unique_rors = set(child_records) | set(parent_records)
    if value.get("unique_inspire_institution_fetch_count") != len(
        institution_records
    ) or value.get("unique_ror_fetch_count") != len(unique_rors):
        raise PairedEnrichmentVerificationError(
            "unique authority fetch counts are inconsistent"
        )
    return value


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paired-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-enrichment-id")
    args = parser.parse_args(argv)
    if not args.execute:
        sys.stdout.write(
            json.dumps(enrichment_plan(args.paired_manifest), indent=2, sort_keys=True)
            + "\n"
        )
        return 0
    if args.output is None:
        parser.error("--output is required with --execute")
    if args.confirm_enrichment_id != ENRICHMENT_ID:
        parser.error(f"--confirm-enrichment-id must equal {ENRICHMENT_ID}")
    manifest, path = execute_paired_enrichment(
        paired_manifest_path=args.paired_manifest,
        output=args.output,
    )
    verified = verify_paired_enrichment_manifest(
        path,
        output=args.output,
        paired_manifest_path=args.paired_manifest,
    )
    sys.stdout.write(
        json.dumps({"manifest_path": str(path), **verified}, indent=2, sort_keys=True)
        + "\n"
    )
    return 0 if manifest["enrichment_complete"] is True else 1


if __name__ == "__main__":
    raise SystemExit(run())
