"""Staging-only exact ROR acquisition and offline authority projections.

Targets derive only from checksum-verified INSPIRE pages.  Acquisition never
searches the ROR registry; canonicalization and replay resolution are separate,
explicit offline passes over immutable evidence.  No pass imports database
models, changes a provider cursor, calculates a metric, or mutates production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urlparse

from .connectors.base import SourceTransport, normalize_external_id
from .connectors.http import ProviderHttpTransport
from .connectors.ror import RorConnector

HISTORICAL_ROR_TARGET_VERSION = "hep-th-v1-historical-ror-targets-v1"
HISTORICAL_ROR_STATE_VERSION = "hep-th-v1-historical-ror-state-v1"
HISTORICAL_ROR_ACQUISITION_VERSION = "hep-th-v1-historical-ror-acquisition-v1"
HISTORICAL_CANONICAL_INSTITUTION_VERSION = (
    "hep-th-v1-historical-canonical-institutions-v2"
)
HISTORICAL_INSTITUTION_RESOLUTION_VERSION = (
    "hep-th-v1-historical-institution-resolutions-v2"
)
EXPECTED_REPLAY_BUNDLE_VERSION = "hep-th-v1-historical-replay-bundle-v1"
PARENT_ROLLUP_POLICY_VERSION = "pa-035-statistical-unit-rollup-v1"
SUPPORTED_INSPIRE_ROR_CROSSWALK_VERSION = "hep-th-v1-inspire-ror-crosswalk-v1"
OFFICIAL_ROR_BASE_URL = "https://api.ror.org/v2"
EXPECTED_SCOPE = "hep-th-v1"
EXPECTED_YEARS = tuple(range(2020, 2026))
STATE_CHECKPOINT_INTERVAL = 25


class HistoricalRorSafetyError(ValueError):
    """Raised before unsafe or unverifiable staged evidence can be used."""


def _explicit_inspire_institution_ror_evidence(
    payload: Mapping[str, Any],
) -> tuple[tuple[str, ...], str]:
    """Re-derive exact ROR IDs and their status from one INSPIRE snapshot."""

    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        raise HistoricalRorSafetyError("INSPIRE institution metadata is malformed")
    identifiers = metadata.get("external_system_identifiers", [])
    if not isinstance(identifiers, list):
        raise HistoricalRorSafetyError(
            "INSPIRE institution external identifiers are malformed"
        )
    result: set[str] = set()
    for item in identifiers:
        if not isinstance(item, Mapping):
            raise HistoricalRorSafetyError(
                "INSPIRE institution external identifier is malformed"
            )
        if str(item.get("schema", "")).strip().casefold() != "ror":
            continue
        normalized = normalize_external_id("ror", item.get("value"))
        if normalized is None:
            raise HistoricalRorSafetyError(
                "INSPIRE institution contains an invalid explicit ROR identifier"
            )
        result.add(normalized[1])
    ror_ids = tuple(sorted(result))
    if len(ror_ids) == 1:
        status = "resolved-exact-explicit-ror-cross-reference"
    elif ror_ids:
        status = "ambiguous-multiple-explicit-ror-cross-references"
    else:
        status = "unresolved-no-explicit-ror-cross-reference"
    return ror_ids, status


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _validate_external_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path(resolved.anchor):
        raise HistoricalRorSafetyError("the filesystem root is not a safe path")
    if _is_within(resolved, _repository_root().resolve()):
        raise HistoricalRorSafetyError(
            "historical authority evidence must remain outside the repository"
        )
    return resolved


def _content_addressed_document(
    path: Path,
    *,
    checksum_field: str,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HistoricalRorSafetyError(
            f"cannot read content-addressed document {path}"
        ) from error
    if not isinstance(value, dict):
        raise HistoricalRorSafetyError("content-addressed document is not an object")
    expected = value.get(checksum_field)
    unsigned = dict(value)
    unsigned.pop(checksum_field, None)
    if (
        not isinstance(expected, str)
        or path.stem != expected
        or _checksum(unsigned) != expected
    ):
        raise HistoricalRorSafetyError(f"content-addressed checksum failed for {path}")
    return value


def _write_content_addressed(
    directory: Path,
    body: Mapping[str, Any],
    *,
    checksum_field: str,
) -> tuple[Path, dict[str, Any]]:
    unsigned = dict(body)
    unsigned.pop(checksum_field, None)
    checksum = _checksum(unsigned)
    document = {**unsigned, checksum_field: checksum}
    payload = _canonical_json(document) + b"\n"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{checksum}.json"
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        if destination.read_bytes() != payload:
            raise HistoricalRorSafetyError(
                "content-addressed path contains different bytes"
            ) from error
    return destination, document


def _normalized_ror(value: object) -> str:
    normalized = normalize_external_id("ror", value)
    if normalized is None:
        raise HistoricalRorSafetyError(
            f"staged INSPIRE evidence contains an invalid ROR identifier: {value!r}"
        )
    return normalized[1]


def _ror_targets_from_hit(hit: Mapping[str, Any]) -> set[str]:
    metadata = hit.get("metadata")
    if not isinstance(metadata, Mapping):
        return set()
    authors = metadata.get("authors", [])
    if not isinstance(authors, list):
        raise HistoricalRorSafetyError("INSPIRE authors evidence is malformed")
    targets: set[str] = set()
    for author in authors:
        if not isinstance(author, Mapping):
            continue
        identifier_groups: list[object] = [author.get("affiliations_identifiers")]
        for affiliation_key in ("affiliations", "raw_affiliations"):
            affiliations = author.get(affiliation_key, [])
            if not isinstance(affiliations, list):
                raise HistoricalRorSafetyError(
                    f"INSPIRE {affiliation_key} evidence is malformed"
                )
            for affiliation in affiliations:
                if not isinstance(affiliation, Mapping):
                    continue
                identifier_groups.extend(
                    affiliation.get(key)
                    for key in ("identifiers", "external_ids", "externalIds")
                )
        for group in identifier_groups:
            if group is None:
                continue
            if not isinstance(group, list):
                raise HistoricalRorSafetyError(
                    "INSPIRE affiliation identifiers evidence is malformed"
                )
            for identifier in group:
                if not isinstance(identifier, Mapping):
                    continue
                if str(identifier.get("schema", "")).strip().casefold() != "ror":
                    continue
                targets.add(_normalized_ror(identifier.get("value")))
    return targets


def build_target_manifest(source_manifest_path: Path) -> dict[str, Any]:
    """Verify the historical acquisition and derive exact staged ROR targets."""

    manifest_path = _validate_external_path(source_manifest_path)
    manifest = _content_addressed_document(
        manifest_path, checksum_field="manifest_checksum"
    )
    if (
        manifest.get("mode") != "acquire"
        or manifest.get("executed") is not True
        or manifest.get("acquisition_complete") is not True
        or manifest.get("acquisition_scope") != EXPECTED_SCOPE
    ):
        raise HistoricalRorSafetyError(
            "source manifest is not the completed bounded hep-th-v1 acquisition"
        )
    staging_root = manifest_path.parent.parent.resolve()
    if not _is_within(manifest_path, staging_root):
        raise HistoricalRorSafetyError("source manifest leaves its staging root")

    partitions = manifest.get("partitions")
    if not isinstance(partitions, list):
        raise HistoricalRorSafetyError("source manifest partitions are malformed")
    inspire_partitions: dict[int, Mapping[str, Any]] = {}
    for partition_value in partitions:
        if not isinstance(partition_value, Mapping):
            raise HistoricalRorSafetyError("source manifest partition is malformed")
        partition = dict(partition_value)
        partition_checksum = partition.pop("partition_checksum", None)
        if (
            not isinstance(partition_checksum, str)
            or _checksum(partition) != partition_checksum
        ):
            raise HistoricalRorSafetyError("source partition checksum failed")
        if partition_value.get("provider") != "inspire":
            continue
        year = partition_value.get("year")
        if (
            not isinstance(year, int)
            or year not in EXPECTED_YEARS
            or partition_value.get("complete") is not True
            or year in inspire_partitions
        ):
            raise HistoricalRorSafetyError(
                "source manifest lacks one complete INSPIRE partition per year"
            )
        inspire_partitions[year] = partition_value
    if set(inspire_partitions) != set(EXPECTED_YEARS):
        raise HistoricalRorSafetyError(
            "source manifest lacks one complete INSPIRE partition per year"
        )

    targets: set[str] = set()
    source_pages: list[dict[str, Any]] = []
    for year in EXPECTED_YEARS:
        pages = inspire_partitions[year].get("pages")
        if not isinstance(pages, list) or not pages:
            raise HistoricalRorSafetyError("complete INSPIRE partition has no pages")
        for page_value in pages:
            if not isinstance(page_value, Mapping):
                raise HistoricalRorSafetyError("source page metadata is malformed")
            checksum = page_value.get("checksum")
            relative_value = page_value.get("path")
            record_count = page_value.get("record_count")
            if (
                not isinstance(checksum, str)
                or not isinstance(relative_value, str)
                or not isinstance(record_count, int)
                or isinstance(record_count, bool)
            ):
                raise HistoricalRorSafetyError("source page metadata is incomplete")
            expected_relative = (
                Path("pages") / "inspire" / str(year) / f"{checksum}.json"
            )
            relative = Path(relative_value)
            if relative != expected_relative:
                raise HistoricalRorSafetyError("source page path is noncanonical")
            page_path = (staging_root / relative).resolve()
            if not _is_within(page_path, staging_root):
                raise HistoricalRorSafetyError("source page leaves its staging root")
            try:
                payload = page_path.read_bytes()
            except OSError as error:
                raise HistoricalRorSafetyError("source page is missing") from error
            if hashlib.sha256(payload).hexdigest() != checksum:
                raise HistoricalRorSafetyError("source page checksum failed")
            try:
                page = json.loads(payload)
            except json.JSONDecodeError as error:
                raise HistoricalRorSafetyError(
                    "source page is malformed JSON"
                ) from error
            hits = page.get("hits", {}).get("hits") if isinstance(page, dict) else None
            if not isinstance(hits, list) or len(hits) != record_count:
                raise HistoricalRorSafetyError("source page record count failed")
            for hit in hits:
                if isinstance(hit, Mapping):
                    targets.update(_ror_targets_from_hit(hit))
            source_pages.append(
                {"year": year, "path": relative.as_posix(), "checksum": checksum}
            )

    return {
        "manifest_version": HISTORICAL_ROR_TARGET_VERSION,
        "acquisition_scope": EXPECTED_SCOPE,
        "years": list(EXPECTED_YEARS),
        "source_manifest_checksum": manifest["manifest_checksum"],
        "source_manifest_version": manifest.get("manifest_version"),
        "source_inspire_pages": source_pages,
        "target_authority": "ROR",
        "target_method": "exact-identifiers-from-verified-inspire-paper-evidence",
        "registry_search": False,
        "database_access": False,
        "canonical_materialization": False,
        "target_count": len(targets),
        "target_ids": sorted(targets),
    }


def write_target_manifest(
    source_manifest_path: Path, output: Path
) -> tuple[Path, dict[str, Any]]:
    output_root = _validate_external_path(output)
    body = build_target_manifest(source_manifest_path)
    return _write_content_addressed(
        output_root / "target-manifests",
        body,
        checksum_field="target_manifest_checksum",
    )


def _record_relative_path(ror_id: str, checksum: str) -> Path:
    return Path("records") / ror_id / f"{checksum}.json"


def _verify_record(output: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    ror_id = value.get("ror_id")
    checksum = value.get("checksum")
    path_value = value.get("path")
    if not all(isinstance(item, str) for item in (ror_id, checksum, path_value)):
        raise HistoricalRorSafetyError("ROR resume record metadata is malformed")
    assert isinstance(ror_id, str)
    assert isinstance(checksum, str)
    assert isinstance(path_value, str)
    if Path(path_value) != _record_relative_path(ror_id, checksum):
        raise HistoricalRorSafetyError("ROR resume record path is noncanonical")
    path = (output / path_value).resolve()
    if not _is_within(path, output.resolve()):
        raise HistoricalRorSafetyError("ROR resume record leaves output directory")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise HistoricalRorSafetyError("ROR resume record is missing") from error
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise HistoricalRorSafetyError("ROR resume record checksum failed")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise HistoricalRorSafetyError("ROR resume record is malformed") from error
    if not isinstance(document, dict):
        raise HistoricalRorSafetyError("ROR resume record is not an object")
    if document.get("source_record_id") != ror_id or document.get("provider") != "ror":
        raise HistoricalRorSafetyError("ROR resume record identity failed")
    return document


def _load_resume_state(
    output: Path,
    *,
    target_manifest_checksum: str,
    target_ids: Sequence[str],
    ror_base_url: str,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for path in sorted((output / "states").glob("*.json")):
        state = _content_addressed_document(path, checksum_field="state_checksum")
        if state.get("target_manifest_checksum") != target_manifest_checksum:
            continue
        if state.get("state_version") != HISTORICAL_ROR_STATE_VERSION:
            raise HistoricalRorSafetyError("ROR resume state version is unsupported")
        if state.get("ror_base_url") != ror_base_url:
            raise HistoricalRorSafetyError("ROR resume state changed provider endpoint")
        records = state.get("records")
        next_index = state.get("next_index")
        if (
            not isinstance(records, list)
            or not isinstance(next_index, int)
            or isinstance(next_index, bool)
            or next_index != len(records)
            or next_index > len(target_ids)
        ):
            raise HistoricalRorSafetyError("ROR resume state summary is malformed")
        observed_ids = [
            item.get("ror_id") for item in records if isinstance(item, Mapping)
        ]
        if observed_ids != list(target_ids[:next_index]):
            raise HistoricalRorSafetyError("ROR resume state is not a target prefix")
        if any(not isinstance(record, Mapping) for record in records):
            raise HistoricalRorSafetyError("ROR resume record metadata is malformed")
        candidates.append(state)
    if not candidates:
        return None
    maximum = max(int(item["next_index"]) for item in candidates)
    finalists = [item for item in candidates if item["next_index"] == maximum]
    record_sets = {_checksum(item["records"]) for item in finalists}
    if len(record_sets) != 1:
        raise HistoricalRorSafetyError("ROR resume states conflict at one checkpoint")
    selected = sorted(finalists, key=lambda item: str(item["state_checksum"]))[-1]
    for record in selected["records"]:
        _verify_record(output, record)
    return selected


def _write_state(
    output: Path,
    *,
    target_manifest: Mapping[str, Any],
    ror_base_url: str,
    records: Sequence[Mapping[str, Any]],
    status: str,
    error: str | None,
) -> dict[str, Any]:
    _path, state = _write_content_addressed(
        output / "states",
        {
            "state_version": HISTORICAL_ROR_STATE_VERSION,
            "target_manifest_checksum": target_manifest["target_manifest_checksum"],
            "source_manifest_checksum": target_manifest["source_manifest_checksum"],
            "ror_base_url": ror_base_url,
            "next_index": len(records),
            "records": list(records),
            "status": status,
            "error": error,
        },
        checksum_field="state_checksum",
    )
    return state


def _store_ror_record(
    output: Path,
    *,
    ror_id: str,
    raw: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    document = {
        "provider": "ror",
        "source_version": RorConnector.source_version,
        "source_record_id": ror_id,
        "evidence_type": "provider-content-snapshot",
        "target_manifest_checksum": target_manifest["target_manifest_checksum"],
        "source_manifest_checksum": target_manifest["source_manifest_checksum"],
        "raw": dict(raw),
    }
    payload = _canonical_json(document) + b"\n"
    checksum = hashlib.sha256(payload).hexdigest()
    relative = _record_relative_path(ror_id, checksum)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        if destination.read_bytes() != payload:
            raise HistoricalRorSafetyError(
                "content-addressed ROR record contains different bytes"
            ) from error
    return {"ror_id": ror_id, "path": relative.as_posix(), "checksum": checksum}


def acquire_target_records(
    target_manifest_path: Path,
    output: Path,
    transport: SourceTransport,
    *,
    ror_base_url: str = OFFICIAL_ROR_BASE_URL,
    max_new_records: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Fetch exact staged ROR IDs and preserve resumable immutable evidence."""

    output_root = _validate_external_path(output)
    target_manifest = _content_addressed_document(
        target_manifest_path.resolve(), checksum_field="target_manifest_checksum"
    )
    if (
        target_manifest.get("manifest_version") != HISTORICAL_ROR_TARGET_VERSION
        or target_manifest.get("registry_search") is not False
        or target_manifest.get("acquisition_scope") != EXPECTED_SCOPE
    ):
        raise HistoricalRorSafetyError("ROR target manifest is not approved")
    target_ids = target_manifest.get("target_ids")
    if (
        not isinstance(target_ids, list)
        or target_ids != sorted(set(target_ids))
        or target_manifest.get("target_count") != len(target_ids)
        or any(
            normalize_external_id("ror", item) != ("ror", item) for item in target_ids
        )
    ):
        raise HistoricalRorSafetyError("ROR target identifiers are malformed")
    parsed_base = urlparse(ror_base_url)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.hostname:
        raise HistoricalRorSafetyError("ROR endpoint is malformed")
    if max_new_records is not None and max_new_records < 1:
        raise ValueError("max_new_records must be positive")

    previous = _load_resume_state(
        output_root,
        target_manifest_checksum=str(target_manifest["target_manifest_checksum"]),
        target_ids=target_ids,
        ror_base_url=ror_base_url,
    )
    records: list[Mapping[str, Any]] = (
        list(previous["records"]) if previous is not None else []
    )
    connector = RorConnector(transport, ror_base_url)
    terminal_status = "complete"
    error_message: str | None = None
    stop_index = len(target_ids)
    if max_new_records is not None:
        stop_index = min(stop_index, len(records) + max_new_records)
    for ror_id in target_ids[len(records) : stop_index]:
        try:
            source_record = connector.fetch_record(ror_id)
            if source_record is None or source_record.source_record_id != ror_id:
                raise HistoricalRorSafetyError(
                    f"ROR response did not match exact target {ror_id}"
                )
            records.append(
                _store_ror_record(
                    output_root,
                    ror_id=ror_id,
                    raw=source_record.raw,
                    target_manifest=target_manifest,
                )
            )
            if len(records) % STATE_CHECKPOINT_INTERVAL == 0:
                _write_state(
                    output_root,
                    target_manifest=target_manifest,
                    ror_base_url=ror_base_url,
                    records=records,
                    status="in-progress",
                    error=None,
                )
        except Exception as error:  # noqa: BLE001 - persisted for safe resume
            terminal_status = "failed"
            error_message = f"{type(error).__name__}: {error}"[:1000]
            _write_state(
                output_root,
                target_manifest=target_manifest,
                ror_base_url=ror_base_url,
                records=records,
                status=terminal_status,
                error=error_message,
            )
            break
    complete = len(records) == len(target_ids) and terminal_status != "failed"
    if not complete and terminal_status != "failed":
        terminal_status = "paused-limit"
    _write_state(
        output_root,
        target_manifest=target_manifest,
        ror_base_url=ror_base_url,
        records=records,
        status="complete" if complete else terminal_status,
        error=error_message,
    )
    return _write_content_addressed(
        output_root / "acquisition-manifests",
        {
            "manifest_version": HISTORICAL_ROR_ACQUISITION_VERSION,
            "target_manifest_checksum": target_manifest["target_manifest_checksum"],
            "source_manifest_checksum": target_manifest["source_manifest_checksum"],
            "ror_base_url": ror_base_url,
            "target_count": len(target_ids),
            "records_completed": len(records),
            "records": list(records),
            "terminal_status": "complete" if complete else terminal_status,
            "acquisition_complete": complete,
            "error": None if complete else error_message,
            "registry_search": False,
            "database_access": False,
            "canonical_materialization": False,
        },
        checksum_field="acquisition_manifest_checksum",
    )


class _OfflineTransport:
    """A connector dependency that proves offline normalization performs no I/O."""

    def close(self) -> None:
        pass

    def __enter__(self) -> _OfflineTransport:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del url, params, headers
        raise AssertionError("offline canonical institution normalization used network")

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        raise AssertionError("offline canonical institution normalization used network")


def _relationship_evidence(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    relationships = raw.get("relationships", [])
    if relationships is None:
        return []
    if not isinstance(relationships, list):
        raise HistoricalRorSafetyError("ROR relationship evidence is malformed")
    result: list[dict[str, Any]] = []
    for relationship in relationships:
        if not isinstance(relationship, Mapping):
            raise HistoricalRorSafetyError("ROR relationship evidence is malformed")
        relationship_type = str(relationship.get("type", "")).strip().casefold()
        if relationship_type not in {"parent", "predecessor", "successor"}:
            continue
        identifier = normalize_external_id("ror", relationship.get("id"))
        result.append(
            {
                "type": relationship_type,
                "rorId": identifier[1] if identifier is not None else None,
                "label": relationship.get("label"),
                "raw": dict(relationship),
            }
        )
    return result


def materialize_canonical_institutions(
    acquisition_manifest_path: Path,
    output: Path,
) -> tuple[Path, dict[str, Any]]:
    """Normalize a complete exact-ROR acquisition into an offline JSONL artifact."""

    acquisition_path = _validate_external_path(acquisition_manifest_path)
    acquisition = _content_addressed_document(
        acquisition_path, checksum_field="acquisition_manifest_checksum"
    )
    if (
        acquisition.get("manifest_version") != HISTORICAL_ROR_ACQUISITION_VERSION
        or acquisition.get("acquisition_complete") is not True
        or acquisition.get("terminal_status") != "complete"
        or acquisition.get("registry_search") is not False
        or acquisition.get("database_access") is not False
    ):
        raise HistoricalRorSafetyError(
            "canonical institution normalization requires a complete exact-ROR "
            "acquisition"
        )
    records = acquisition.get("records")
    target_count = acquisition.get("target_count")
    if (
        not isinstance(records, list)
        or not isinstance(target_count, int)
        or isinstance(target_count, bool)
        or acquisition.get("records_completed") != target_count
        or len(records) != target_count
    ):
        raise HistoricalRorSafetyError("complete ROR acquisition count is inconsistent")

    acquisition_root = acquisition_path.parent.parent.resolve()
    target_checksum = acquisition.get("target_manifest_checksum")
    if not isinstance(target_checksum, str):
        raise HistoricalRorSafetyError("ROR acquisition lacks target lineage")
    target_path = acquisition_root / "target-manifests" / f"{target_checksum}.json"
    target = _content_addressed_document(
        target_path, checksum_field="target_manifest_checksum"
    )
    target_ids = target.get("target_ids")
    if (
        not isinstance(target_ids, list)
        or target_ids != sorted(set(target_ids))
        or target.get("source_manifest_checksum")
        != acquisition.get("source_manifest_checksum")
    ):
        raise HistoricalRorSafetyError("ROR target lineage is inconsistent")

    raw_documents: dict[str, tuple[dict[str, Any], Mapping[str, Any]]] = {}
    for metadata in records:
        if not isinstance(metadata, Mapping):
            raise HistoricalRorSafetyError("ROR acquisition record is malformed")
        document = _verify_record(acquisition_root, metadata)
        ror_id = document["source_record_id"]
        if ror_id in raw_documents:
            raise HistoricalRorSafetyError(
                "ROR acquisition contains a duplicate target"
            )
        raw_documents[ror_id] = (document, metadata)
    if sorted(raw_documents) != target_ids:
        raise HistoricalRorSafetyError(
            "ROR acquisition does not cover its exact targets"
        )

    connector = RorConnector(_OfflineTransport(), OFFICIAL_ROR_BASE_URL)
    canonical_rows: list[dict[str, Any]] = []
    for ror_id in target_ids:
        document, metadata = raw_documents[ror_id]
        raw = document.get("raw")
        if not isinstance(raw, dict):
            raise HistoricalRorSafetyError("ROR record raw authority body is malformed")
        source_records = connector._records({"items": [raw]})
        if len(source_records) != 1 or source_records[0].source_record_id != ror_id:
            raise HistoricalRorSafetyError(
                "ROR record failed offline identity validation"
            )
        normalized = connector.normalize_record(source_records[0])
        canonical_rows.append(
            {
                "canonicalInstitutionId": f"institution-ror-{ror_id}",
                "rorId": ror_id,
                "canonicalName": normalized.canonical_name,
                "aliases": list(normalized.attributes.get("aliases", [])),
                "organizationStatus": raw.get("status"),
                "countryCode": normalized.attributes.get("country_code"),
                "city": normalized.attributes.get("city"),
                "latitude": normalized.attributes.get("latitude"),
                "longitude": normalized.attributes.get("longitude"),
                "authorityRelationshipEvidence": _relationship_evidence(raw),
                "sourceRecordId": ror_id,
                "sourceRecordEvidenceType": "provider-content-snapshot",
                "sourceRecordChecksum": metadata["checksum"],
                "sourceRecordPath": metadata["path"],
                "sourceVersion": RorConnector.source_version,
                "targetManifestChecksum": target_checksum,
                "sourceManifestChecksum": acquisition["source_manifest_checksum"],
                "acquisitionManifestChecksum": acquisition[
                    "acquisition_manifest_checksum"
                ],
            }
        )

    output_root = _validate_external_path(output)
    lines = b"".join(_canonical_json(row) + b"\n" for row in canonical_rows)
    artifact_checksum = hashlib.sha256(lines).hexdigest()
    relative = Path("canonical-institutions") / f"{artifact_checksum}.jsonl"
    artifact_path = output_root / relative
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with artifact_path.open("xb") as stream:
            stream.write(lines)
    except FileExistsError as error:
        if artifact_path.read_bytes() != lines:
            raise HistoricalRorSafetyError(
                "canonical institution artifact path contains different bytes"
            ) from error

    return _write_content_addressed(
        output_root / "canonical-manifests",
        {
            "manifest_version": HISTORICAL_CANONICAL_INSTITUTION_VERSION,
            "acquisition_manifest_checksum": acquisition[
                "acquisition_manifest_checksum"
            ],
            "target_manifest_checksum": target_checksum,
            "source_manifest_checksum": acquisition["source_manifest_checksum"],
            "record_count": len(canonical_rows),
            "artifact_path": relative.as_posix(),
            "artifact_checksum": artifact_checksum,
            "artifact_format": "canonical-json-lines",
            "authority": "ROR",
            "source_evidence_type": "provider-content-snapshot",
            "fetch_timestamp_available": False,
            "offline_normalization": True,
            "database_access": False,
            "affiliation_join": False,
            "canonical_materialization_complete": True,
        },
        checksum_field="canonical_manifest_checksum",
    )


def _verified_jsonl_artifact(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    *,
    role: str,
) -> list[dict[str, Any]]:
    entries = manifest.get("artifacts")
    if not isinstance(entries, list):
        raise HistoricalRorSafetyError("evidence manifest artifacts are malformed")
    matches = [
        item
        for item in entries
        if isinstance(item, Mapping) and item.get("role") == role
    ]
    if len(matches) != 1:
        raise HistoricalRorSafetyError(
            f"evidence manifest must contain exactly one {role!r} artifact"
        )
    entry = matches[0]
    relative_value = entry.get("path")
    checksum = entry.get("checksum")
    row_count = entry.get("row_count")
    if (
        not isinstance(relative_value, str)
        or not isinstance(checksum, str)
        or not isinstance(row_count, int)
        or isinstance(row_count, bool)
    ):
        raise HistoricalRorSafetyError(f"{role} artifact metadata is malformed")
    root = manifest_path.parent.parent.resolve()
    relative = Path(relative_value)
    artifact_path = (root / relative).resolve()
    if relative.is_absolute() or not _is_within(artifact_path, root):
        raise HistoricalRorSafetyError(f"{role} artifact leaves its bundle root")
    try:
        payload = artifact_path.read_bytes()
    except OSError as error:
        raise HistoricalRorSafetyError(f"{role} artifact is missing") from error
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise HistoricalRorSafetyError(f"{role} artifact checksum failed")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise HistoricalRorSafetyError(
                f"{role} artifact has malformed JSON on line {line_number}"
            ) from error
        if not isinstance(row, dict):
            raise HistoricalRorSafetyError(f"{role} artifact row is not an object")
        rows.append(row)
    if len(rows) != row_count:
        raise HistoricalRorSafetyError(f"{role} artifact row count failed")
    return rows


def _fraction_from_payload(value: object) -> Fraction:
    if not isinstance(value, Mapping):
        raise HistoricalRorSafetyError("attribution weight is malformed")
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    exact = value.get("exact")
    if (
        not isinstance(numerator, int)
        or isinstance(numerator, bool)
        or not isinstance(denominator, int)
        or isinstance(denominator, bool)
        or denominator <= 0
    ):
        raise HistoricalRorSafetyError("attribution weight is malformed")
    fraction = Fraction(numerator, denominator)
    if exact != f"{fraction.numerator}/{fraction.denominator}":
        raise HistoricalRorSafetyError("attribution weight exact value is inconsistent")
    return fraction


def _fraction_payload(value: Fraction) -> dict[str, int | str]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "exact": f"{value.numerator}/{value.denominator}",
    }


def _write_jsonl_artifact(
    output: Path,
    *,
    directory: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = b"".join(_canonical_json(dict(row)) + b"\n" for row in rows)
    checksum = hashlib.sha256(payload).hexdigest()
    relative = Path(directory) / f"{checksum}.jsonl"
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        if destination.read_bytes() != payload:
            raise HistoricalRorSafetyError(
                "resolution artifact path contains different bytes"
            ) from error
    return {
        "path": relative.as_posix(),
        "checksum": checksum,
        "row_count": len(rows),
        "byte_count": len(payload),
    }


def _complete_canonical_authority(
    authority: Mapping[str, Any] | None,
    ror_id: str,
) -> bool:
    if authority is None:
        return False
    country_code = authority.get("countryCode")
    return (
        authority.get("canonicalInstitutionId") == f"institution-ror-{ror_id}"
        and isinstance(authority.get("canonicalName"), str)
        and bool(str(authority["canonicalName"]).strip())
        and isinstance(country_code, str)
        and len(country_code) == 2
        and country_code.isalpha()
    )


def _verified_supplemental_inspire_ror_crosswalk(
    manifest_path: Path,
    replay: Mapping[str, Any],
) -> tuple[dict[str, str], str]:
    """Load a complete exact recid-to-ROR crosswalk with immutable lineage."""

    path = _validate_external_path(manifest_path)
    manifest = _content_addressed_document(
        path, checksum_field="crosswalk_manifest_checksum"
    )
    target_count = manifest.get("target_count")
    records_examined = manifest.get("records_examined")
    status_counts = [
        manifest.get(field)
        for field in (
            "exact_ror_crosswalk_count",
            "unresolved_crosswalk_count",
            "ambiguous_crosswalk_count",
        )
    ]
    status_count_total = 0
    for count in status_counts:
        if not isinstance(count, int) or isinstance(count, bool):
            raise HistoricalRorSafetyError(
                "supplemental crosswalk status counts are malformed"
            )
        status_count_total += count
    if (
        manifest.get("manifest_version") != SUPPORTED_INSPIRE_ROR_CROSSWALK_VERSION
        or manifest.get("acquisition_complete") is not True
        or manifest.get("replay_bundle_manifest_checksum")
        != replay.get("bundle_manifest_checksum")
        or manifest.get("source_manifest_checksum")
        != replay.get("source_manifest_checksum")
        or manifest.get("registry_search") is not False
        or manifest.get("name_matching") is not False
        or manifest.get("database_access") is not False
        or manifest.get("metric_observations_created") != 0
        or manifest.get("eligible_for_public_metrics") is not False
        or not isinstance(target_count, int)
        or isinstance(target_count, bool)
        or not isinstance(records_examined, int)
        or isinstance(records_examined, bool)
        or target_count != records_examined
        or status_count_total != target_count
        or not isinstance(manifest.get("target_manifest_checksum"), str)
        or not isinstance(manifest.get("acquisition_manifest_checksum"), str)
    ):
        raise HistoricalRorSafetyError(
            "supplemental INSPIRE-to-ROR crosswalk is not a complete approved input"
        )
    artifact = manifest.get("artifact")
    if not isinstance(artifact, Mapping):
        raise HistoricalRorSafetyError("supplemental crosswalk artifact is malformed")
    relative_value = artifact.get("path")
    checksum = artifact.get("checksum")
    row_count = artifact.get("row_count")
    if (
        not isinstance(relative_value, str)
        or not isinstance(checksum, str)
        or not isinstance(row_count, int)
        or isinstance(row_count, bool)
        or row_count != target_count
    ):
        raise HistoricalRorSafetyError("supplemental crosswalk artifact is malformed")
    root = path.parent.parent.resolve()
    relative = Path(relative_value)
    artifact_path = (root / relative).resolve()
    if relative.is_absolute() or not _is_within(artifact_path, root):
        raise HistoricalRorSafetyError("supplemental crosswalk artifact leaves root")
    try:
        payload = artifact_path.read_bytes()
    except OSError as error:
        raise HistoricalRorSafetyError(
            "supplemental crosswalk artifact is missing"
        ) from error
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise HistoricalRorSafetyError("supplemental crosswalk checksum failed")

    mapping: dict[str, str] = {}
    seen_recids: set[str] = set()
    rows = payload.splitlines()
    if len(rows) != row_count:
        raise HistoricalRorSafetyError("supplemental crosswalk row count failed")
    for line_number, line in enumerate(rows, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise HistoricalRorSafetyError(
                f"supplemental crosswalk has malformed JSON on line {line_number}"
            ) from error
        if not isinstance(row, Mapping):
            raise HistoricalRorSafetyError(
                "supplemental crosswalk row is not an object"
            )
        recid = row.get("inspireInstitutionId")
        ror_ids = row.get("rorIds")
        status = row.get("resolutionStatus")
        source_checksum = row.get("sourceRecordChecksum")
        source_path_value = row.get("sourceRecordPath")
        if (
            not isinstance(recid, str)
            or not recid.isdigit()
            or recid in seen_recids
            or not isinstance(ror_ids, list)
            or any(not isinstance(item, str) for item in ror_ids)
            or not isinstance(source_checksum, str)
            or len(source_checksum) != 64
            or any(character not in "0123456789abcdef" for character in source_checksum)
            or not isinstance(source_path_value, str)
            or Path(source_path_value)
            != Path("records") / recid / f"{source_checksum}.json"
            or row.get("targetManifestChecksum")
            != manifest.get("target_manifest_checksum")
            or row.get("acquisitionManifestChecksum")
            != manifest.get("acquisition_manifest_checksum")
            or row.get("crosswalkVersion") != SUPPORTED_INSPIRE_ROR_CROSSWALK_VERSION
            or row.get("nameMatching") is not False
            or row.get("eligibleForPublicMetrics") is not False
        ):
            raise HistoricalRorSafetyError("supplemental crosswalk row is malformed")
        source_path = (root / source_path_value).resolve()
        if not _is_within(source_path, root):
            raise HistoricalRorSafetyError(
                "supplemental crosswalk source record leaves root"
            )
        try:
            source_payload = source_path.read_bytes()
        except OSError as error:
            raise HistoricalRorSafetyError(
                "supplemental crosswalk source record is missing"
            ) from error
        if hashlib.sha256(source_payload).hexdigest() != source_checksum:
            raise HistoricalRorSafetyError(
                "supplemental crosswalk source record checksum failed"
            )
        try:
            source_document = json.loads(source_payload)
        except json.JSONDecodeError as error:
            raise HistoricalRorSafetyError(
                "supplemental crosswalk source record is malformed"
            ) from error
        if (
            not isinstance(source_document, Mapping)
            or source_document.get("provider") != "inspire"
            or source_document.get("source_record_kind") != "institution"
            or source_document.get("source_record_id") != recid
            or source_document.get("target_manifest_checksum")
            != manifest.get("target_manifest_checksum")
            or source_document.get("source_manifest_checksum")
            != manifest.get("source_manifest_checksum")
            or source_document.get("captured_at") != row.get("capturedAt")
        ):
            raise HistoricalRorSafetyError(
                "supplemental crosswalk source record lineage is inconsistent"
            )
        raw = source_document.get("raw")
        if not isinstance(raw, Mapping):
            raise HistoricalRorSafetyError(
                "supplemental crosswalk source raw snapshot is malformed"
            )
        source_ror_ids, source_status = _explicit_inspire_institution_ror_evidence(raw)
        if tuple(ror_ids) != source_ror_ids or status != source_status:
            raise HistoricalRorSafetyError(
                "supplemental crosswalk ROR evidence differs from its source snapshot"
            )
        seen_recids.add(recid)
        if status == "resolved-exact-explicit-ror-cross-reference":
            if len(ror_ids) != 1 or normalize_external_id("ror", ror_ids[0]) != (
                "ror",
                ror_ids[0],
            ):
                raise HistoricalRorSafetyError(
                    "resolved supplemental crosswalk row is malformed"
                )
            mapping[recid] = ror_ids[0]
        elif status == "unresolved-no-explicit-ror-cross-reference":
            if ror_ids:
                raise HistoricalRorSafetyError(
                    "unresolved supplemental crosswalk row carries a ROR"
                )
        elif status == "ambiguous-multiple-explicit-ror-cross-references":
            if len(set(ror_ids)) < 2 or any(
                normalize_external_id("ror", item) != ("ror", item) for item in ror_ids
            ):
                raise HistoricalRorSafetyError(
                    "ambiguous supplemental crosswalk row is malformed"
                )
        else:
            raise HistoricalRorSafetyError(
                "supplemental crosswalk resolution status is unsupported"
            )
    return mapping, str(manifest["crosswalk_manifest_checksum"])


def _share_inspire_institution_ids(share: Mapping[str, Any]) -> tuple[str, ...]:
    identifiers: set[str] = set()
    evidence = share.get("resolution_evidence", [])
    if not isinstance(evidence, list):
        raise HistoricalRorSafetyError(
            "replay affiliation resolution evidence is malformed"
        )
    for evidence_row in evidence:
        if not isinstance(evidence_row, Mapping):
            raise HistoricalRorSafetyError(
                "replay affiliation resolution evidence row is malformed"
            )
        provider_ids = evidence_row.get("provider_institution_identifiers", [])
        if not isinstance(provider_ids, list):
            raise HistoricalRorSafetyError(
                "replay provider institution identifiers are malformed"
            )
        for identifier in provider_ids:
            if not isinstance(identifier, Mapping):
                raise HistoricalRorSafetyError(
                    "replay provider institution identifier is malformed"
                )
            if identifier.get("scheme") != "inspire-institution":
                continue
            normalized = normalize_external_id(
                "inspire-institution", identifier.get("value")
            )
            if (
                normalized is None
                or normalized[1] != str(identifier.get("value"))
                or not normalized[1].isdigit()
            ):
                raise HistoricalRorSafetyError(
                    "replay INSPIRE institution identifier is not canonical"
                )
            identifiers.add(normalized[1])
    return tuple(sorted(identifiers))


def resolve_replay_institution_anchors(
    replay_manifest_path: Path,
    canonical_manifest_path: Path | Sequence[Path],
    output: Path,
    *,
    supplemental_crosswalk_manifest_path: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Resolve exact replay/crosswalk anchors against verified canonical bundles.

    The original replay remains immutable.  The returned projection retains every
    attribution share and its exact weight, including unresolved and ambiguous
    mass; it performs no name matching and writes no database state.
    """

    replay_path = _validate_external_path(replay_manifest_path)
    replay = _content_addressed_document(
        replay_path, checksum_field="bundle_manifest_checksum"
    )
    if (
        replay.get("bundle_version") != EXPECTED_REPLAY_BUNDLE_VERSION
        or replay.get("network_access") is not False
        or replay.get("database_access") is not False
        or replay.get("canonical_institutions_materialized") != 0
        or replay.get("metric_observations_created") != 0
    ):
        raise HistoricalRorSafetyError("replay bundle is not an approved offline input")

    canonical_paths = (
        (canonical_manifest_path,)
        if isinstance(canonical_manifest_path, Path)
        else tuple(canonical_manifest_path)
    )
    if not canonical_paths:
        raise HistoricalRorSafetyError(
            "at least one canonical institution bundle is required"
        )
    canonical_manifests: dict[str, dict[str, Any]] = {}
    canonical_by_ror: dict[str, dict[str, Any]] = {}
    canonical_manifest_checksum_by_ror: dict[str, str] = {}
    for manifest_path in canonical_paths:
        canonical_path = _validate_external_path(manifest_path)
        canonical = _content_addressed_document(
            canonical_path, checksum_field="canonical_manifest_checksum"
        )
        manifest_checksum = canonical.get("canonical_manifest_checksum")
        if (
            not isinstance(manifest_checksum, str)
            or manifest_checksum in canonical_manifests
            or canonical.get("manifest_version")
            != HISTORICAL_CANONICAL_INSTITUTION_VERSION
            or canonical.get("canonical_materialization_complete") is not True
            or canonical.get("offline_normalization") is not True
            or canonical.get("database_access") is not False
            or canonical.get("affiliation_join") is not False
            or canonical.get("source_manifest_checksum")
            != replay.get("source_manifest_checksum")
            or not isinstance(canonical.get("target_manifest_checksum"), str)
            or not isinstance(canonical.get("acquisition_manifest_checksum"), str)
        ):
            raise HistoricalRorSafetyError(
                "canonical institution bundle is not an approved distinct lineage input"
            )
        canonical_manifests[manifest_checksum] = canonical
        canonical_root = canonical_path.parent.parent.resolve()
        canonical_relative_value = canonical.get("artifact_path")
        canonical_checksum = canonical.get("artifact_checksum")
        canonical_count = canonical.get("record_count")
        if (
            not isinstance(canonical_relative_value, str)
            or not isinstance(canonical_checksum, str)
            or not isinstance(canonical_count, int)
            or isinstance(canonical_count, bool)
        ):
            raise HistoricalRorSafetyError(
                "canonical institution artifact is malformed"
            )
        canonical_relative = Path(canonical_relative_value)
        canonical_artifact = (canonical_root / canonical_relative).resolve()
        if canonical_relative.is_absolute() or not _is_within(
            canonical_artifact, canonical_root
        ):
            raise HistoricalRorSafetyError(
                "canonical institution artifact leaves its bundle root"
            )
        try:
            canonical_payload = canonical_artifact.read_bytes()
        except OSError as error:
            raise HistoricalRorSafetyError(
                "canonical institution artifact is missing"
            ) from error
        if hashlib.sha256(canonical_payload).hexdigest() != canonical_checksum:
            raise HistoricalRorSafetyError(
                "canonical institution artifact checksum failed"
            )
        manifest_ror_ids: set[str] = set()
        for line_number, line in enumerate(canonical_payload.splitlines(), start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise HistoricalRorSafetyError(
                    "canonical institution artifact has malformed JSON on line "
                    f"{line_number}"
                ) from error
            if not isinstance(row, dict):
                raise HistoricalRorSafetyError(
                    "canonical institution artifact row is not an object"
                )
            ror_id = row.get("rorId")
            if (
                not isinstance(ror_id, str)
                or normalize_external_id("ror", ror_id) != ("ror", ror_id)
                or ror_id in canonical_by_ror
                or row.get("canonicalInstitutionId") != f"institution-ror-{ror_id}"
                or row.get("sourceManifestChecksum")
                != canonical.get("source_manifest_checksum")
                or row.get("targetManifestChecksum")
                != canonical.get("target_manifest_checksum")
                or row.get("acquisitionManifestChecksum")
                != canonical.get("acquisition_manifest_checksum")
            ):
                raise HistoricalRorSafetyError(
                    "canonical institution row identity, uniqueness, or lineage "
                    "is inconsistent"
                )
            canonical_by_ror[ror_id] = row
            canonical_manifest_checksum_by_ror[ror_id] = manifest_checksum
            manifest_ror_ids.add(ror_id)
        if len(manifest_ror_ids) != canonical_count:
            raise HistoricalRorSafetyError(
                "canonical institution artifact record count failed"
            )

    canonical_manifest_checksums = sorted(canonical_manifests)
    target_manifest_checksums = sorted(
        {
            str(manifest["target_manifest_checksum"])
            for manifest in canonical_manifests.values()
        }
    )
    acquisition_manifest_checksums = sorted(
        {
            str(manifest["acquisition_manifest_checksum"])
            for manifest in canonical_manifests.values()
        }
    )
    extended_resolution_schema = (
        len(canonical_manifest_checksums) != 1
        or supplemental_crosswalk_manifest_path is not None
    )

    anchors = _verified_jsonl_artifact(
        replay_path, replay, role="institution-authority-anchors"
    )
    shares = _verified_jsonl_artifact(
        replay_path, replay, role="paper-time-affiliation-shares"
    )
    ledgers = _verified_jsonl_artifact(
        replay_path, replay, role="fractional-attribution-ledgers"
    )
    supplemental_ror_by_recid: dict[str, str] = {}
    supplemental_crosswalk_checksum: str | None = None
    if supplemental_crosswalk_manifest_path is not None:
        (
            supplemental_ror_by_recid,
            supplemental_crosswalk_checksum,
        ) = _verified_supplemental_inspire_ror_crosswalk(
            supplemental_crosswalk_manifest_path,
            replay,
        )
    all_anchors = list(anchors)
    supplemental_anchor_by_recid: dict[str, str] = {}
    for recid, ror_id in sorted(supplemental_ror_by_recid.items()):
        anchor_id = f"institution-authority-supplemental-inspire-{recid}-ror-{ror_id}"
        supplemental_anchor_by_recid[recid] = anchor_id
        all_anchors.append(
            {
                "institution_authority_anchor_id": anchor_id,
                "authority_identifier": {"scheme": "ror", "value": ror_id},
                "required_authority_bundle_version": (
                    HISTORICAL_CANONICAL_INSTITUTION_VERSION
                ),
                "source_assertion_ids": [],
                "source_occurrence_ids": [],
                "supplemental_inspire_institution_id": recid,
                "supplemental_crosswalk_manifest_checksum": (
                    supplemental_crosswalk_checksum
                ),
            }
        )
    resolution_by_anchor: dict[str, dict[str, Any]] = {}
    resolution_rows: list[dict[str, Any]] = []
    for anchor in sorted(
        all_anchors,
        key=lambda item: str(item.get("institution_authority_anchor_id", "")),
    ):
        anchor_id_value = anchor.get("institution_authority_anchor_id")
        identifier = anchor.get("authority_identifier")
        supplemental_recid = anchor.get("supplemental_inspire_institution_id")
        if (
            not isinstance(anchor_id_value, str)
            or not isinstance(identifier, Mapping)
            or str(identifier.get("scheme", "")).strip().casefold() != "ror"
            or anchor.get("required_authority_bundle_version")
            != HISTORICAL_CANONICAL_INSTITUTION_VERSION
            or (
                supplemental_recid is not None
                and (
                    not isinstance(supplemental_recid, str)
                    or not supplemental_recid.isdigit()
                    or anchor.get("supplemental_crosswalk_manifest_checksum")
                    != supplemental_crosswalk_checksum
                )
            )
        ):
            raise HistoricalRorSafetyError("replay institution anchor is malformed")
        normalized = normalize_external_id("ror", identifier.get("value"))
        expected_anchor_id = (
            f"institution-authority-supplemental-inspire-{supplemental_recid}"
            f"-ror-{normalized[1]}"
            if normalized is not None and supplemental_recid is not None
            else (
                f"institution-authority-ror-{normalized[1]}"
                if normalized is not None
                else None
            )
        )
        if (
            normalized is None
            or anchor_id_value != expected_anchor_id
            or anchor_id_value in resolution_by_anchor
        ):
            raise HistoricalRorSafetyError(
                "replay institution anchor identity is inconsistent"
            )
        authority = canonical_by_ror.get(normalized[1])
        country_code = authority.get("countryCode") if authority is not None else None
        canonical_institution_id = (
            authority.get("canonicalInstitutionId") if authority is not None else None
        )
        metadata_complete = _complete_canonical_authority(authority, normalized[1])
        resolution_status = (
            "resolved-exact-ror"
            if metadata_complete
            else (
                "unresolved-ror-metadata-incomplete"
                if authority is not None
                else "unresolved-ror-not-in-canonical-bundle"
            )
        )
        resolved_name: str | None = None
        resolved_country_id: str | None = None
        resolved_city: object | None = None
        resolved_latitude: object | None = None
        resolved_longitude: object | None = None
        if metadata_complete:
            assert authority is not None
            assert isinstance(canonical_institution_id, str)
            assert isinstance(country_code, str)
            resolved_name = str(authority["canonicalName"])
            resolved_country_id = f"country-{country_code.casefold()}"
            resolved_city = authority.get("city")
            resolved_latitude = authority.get("latitude")
            resolved_longitude = authority.get("longitude")

        parent_evidence: list[Mapping[str, Any]] = []
        predecessor_evidence_count = 0
        successor_evidence_count = 0
        if authority is not None:
            relationships = authority.get("authorityRelationshipEvidence", [])
            if not isinstance(relationships, list):
                raise HistoricalRorSafetyError(
                    "canonical institution relationship evidence is malformed"
                )
            for relationship in relationships:
                if not isinstance(relationship, Mapping):
                    raise HistoricalRorSafetyError(
                        "canonical institution relationship evidence is malformed"
                    )
                relationship_type = relationship.get("type")
                if relationship_type == "parent":
                    parent_evidence.append(relationship)
                elif relationship_type == "predecessor":
                    predecessor_evidence_count += 1
                elif relationship_type == "successor":
                    successor_evidence_count += 1

        parent_ids: set[str] = set()
        invalid_parent_evidence_count = 0
        for relationship in parent_evidence:
            parent_identifier = normalize_external_id("ror", relationship.get("rorId"))
            if parent_identifier is None:
                invalid_parent_evidence_count += 1
            else:
                parent_ids.add(parent_identifier[1])

        organization_status = (
            str(authority.get("organizationStatus", "")).strip().casefold()
            if authority is not None
            else ""
        )
        rollup_status = "withheld-child-ror-unresolved"
        rollup_authority: dict[str, Any] | None = None
        if metadata_complete:
            if organization_status != "active":
                rollup_status = "withheld-child-lifecycle-status-not-active"
            elif invalid_parent_evidence_count:
                rollup_status = "withheld-invalid-parent-ror-evidence"
            elif len(parent_ids) == 0:
                rollup_status = "eligible-self-rollup"
                rollup_authority = authority
            elif len(parent_ids) > 1:
                rollup_status = "withheld-multiple-parent-rors"
            else:
                parent_id = next(iter(parent_ids))
                parent_authority = canonical_by_ror.get(parent_id)
                if not _complete_canonical_authority(parent_authority, parent_id):
                    rollup_status = "withheld-parent-ror-metadata-unavailable"
                else:
                    assert parent_authority is not None
                    if (
                        str(parent_authority.get("organizationStatus", ""))
                        .strip()
                        .casefold()
                        != "active"
                    ):
                        rollup_status = "withheld-parent-lifecycle-status-not-active"
                    else:
                        rollup_status = "eligible-exact-ror-parent-rollup"
                        rollup_authority = parent_authority

        canonical_manifest_checksum = canonical_manifest_checksum_by_ror.get(
            normalized[1]
        )
        if not extended_resolution_schema:
            canonical_manifest_checksum = canonical_manifest_checksums[0]
        resolution = {
            "institutionAuthorityAnchorId": anchor_id_value,
            "authorityIdentifier": {"scheme": "ror", "value": normalized[1]},
            "resolutionStatus": resolution_status,
            "canonicalInstitutionId": (
                canonical_institution_id if metadata_complete else None
            ),
            "canonicalName": resolved_name,
            "countryId": resolved_country_id,
            "countryCode": country_code if metadata_complete else None,
            "city": resolved_city,
            "latitude": resolved_latitude,
            "longitude": resolved_longitude,
            "organizationStatus": organization_status or "unknown",
            "parentRorIds": sorted(parent_ids),
            "invalidParentEvidenceCount": invalid_parent_evidence_count,
            "predecessorEvidenceCount": predecessor_evidence_count,
            "successorEvidenceCount": successor_evidence_count,
            "statisticalRollupStatus": rollup_status,
            "statisticalRollupInstitutionId": (
                rollup_authority["canonicalInstitutionId"]
                if rollup_authority is not None
                else None
            ),
            "statisticalRollupRorId": (
                rollup_authority["rorId"] if rollup_authority is not None else None
            ),
            "statisticalRollupCountryId": (
                f"country-{str(rollup_authority['countryCode']).casefold()}"
                if rollup_authority is not None
                else None
            ),
            "sourceAssertionIds": anchor.get("source_assertion_ids", []),
            "sourceOccurrenceIds": anchor.get("source_occurrence_ids", []),
            "replayBundleManifestChecksum": replay["bundle_manifest_checksum"],
            "canonicalManifestChecksum": canonical_manifest_checksum,
            "sourceManifestChecksum": replay["source_manifest_checksum"],
            "resolutionVersion": HISTORICAL_INSTITUTION_RESOLUTION_VERSION,
            "eligibleForPublicMetrics": False,
        }
        if extended_resolution_schema:
            resolution.update(
                {
                    "resolutionEvidenceType": (
                        "exact-inspire-institution-recid-to-explicit-ror-cross-reference"
                        if supplemental_recid is not None
                        else "direct-paper-time-ror-anchor"
                    ),
                    "supplementalInspireInstitutionId": supplemental_recid,
                    "supplementalCrosswalkManifestChecksum": (
                        supplemental_crosswalk_checksum
                        if supplemental_recid is not None
                        else None
                    ),
                    "canonicalManifestChecksums": canonical_manifest_checksums,
                }
            )
        resolution_by_anchor[anchor_id_value] = resolution
        resolution_rows.append(resolution)

    evaluated_mass = Fraction(0)
    authority_linked_mass = Fraction(0)
    child_resolved_mass = Fraction(0)
    activation_rollup_mass = Fraction(0)
    child_resolution_mass_by_status: dict[str, Fraction] = {}
    rollup_mass_by_status: dict[str, Fraction] = {}
    share_mass_by_candidate: dict[str, Fraction] = {}
    projection_rows: list[dict[str, Any]] = []
    seen_share_ids: set[str] = set()
    for share in sorted(
        shares, key=lambda item: str(item.get("paper_time_affiliation_share_id", ""))
    ):
        share_id = share.get("paper_time_affiliation_share_id")
        anchor_ids_value = share.get("institution_authority_anchor_ids")
        if (
            not isinstance(share_id, str)
            or share_id in seen_share_ids
            or not isinstance(anchor_ids_value, list)
            or any(not isinstance(item, str) for item in anchor_ids_value)
        ):
            raise HistoricalRorSafetyError(
                "replay paper-time affiliation share is malformed"
            )
        seen_share_ids.add(share_id)
        anchor_ids = list(dict.fromkeys(anchor_ids_value))
        inspire_institution_ids = (
            _share_inspire_institution_ids(share)
            if supplemental_crosswalk_manifest_path is not None
            else ()
        )
        supplemental_anchor_ids = (
            [supplemental_anchor_by_recid[inspire_institution_ids[0]]]
            if (
                not anchor_ids
                and len(inspire_institution_ids) == 1
                and inspire_institution_ids[0] in supplemental_anchor_by_recid
            )
            else []
        )
        effective_anchor_ids = anchor_ids or supplemental_anchor_ids
        matching_resolution = (
            resolution_by_anchor.get(effective_anchor_ids[0])
            if len(effective_anchor_ids) == 1
            else None
        )
        authority_linked = (
            matching_resolution is not None
            and matching_resolution["resolutionStatus"] == "resolved-exact-ror"
        )
        paper_identity_status = share.get("paper_identity_status")
        if not isinstance(paper_identity_status, str):
            raise HistoricalRorSafetyError(
                "replay paper-time affiliation share lacks paper identity status"
            )
        child_resolved = authority_linked and paper_identity_status == "matched"
        rollup_eligible = (
            child_resolved
            and matching_resolution is not None
            and str(matching_resolution["statisticalRollupStatus"]).startswith(
                "eligible-"
            )
        )
        weight = _fraction_from_payload(share.get("attribution_weight"))
        evaluated_mass += weight
        candidate_id = share.get("candidate_id")
        if not isinstance(candidate_id, str):
            raise HistoricalRorSafetyError(
                "replay paper-time affiliation share lacks a candidate identity"
            )
        share_mass_by_candidate[candidate_id] = (
            share_mass_by_candidate.get(candidate_id, Fraction(0)) + weight
        )
        if authority_linked:
            authority_linked_mass += weight
        if child_resolved:
            child_resolved_mass += weight
        if rollup_eligible:
            activation_rollup_mass += weight
        authority_linked_institution_id = (
            matching_resolution["canonicalInstitutionId"]
            if matching_resolution is not None and authority_linked
            else None
        )
        projected_institution_id = (
            matching_resolution["canonicalInstitutionId"]
            if matching_resolution is not None and child_resolved
            else None
        )
        projected_country_id = (
            matching_resolution["countryId"]
            if matching_resolution is not None and child_resolved
            else None
        )
        statistical_rollup_institution_id = (
            matching_resolution["statisticalRollupInstitutionId"]
            if matching_resolution is not None and rollup_eligible
            else None
        )
        statistical_rollup_country_id = (
            matching_resolution["statisticalRollupCountryId"]
            if matching_resolution is not None and rollup_eligible
            else None
        )
        if child_resolved:
            child_resolution_status = "resolved-exact-ror-child"
        elif authority_linked and paper_identity_status != "matched":
            child_resolution_status = "withheld-paper-identity-needs-review"
        elif len(anchor_ids) > 1:
            child_resolution_status = "unresolved-multiple-direct-ror-anchors"
        elif not anchor_ids and len(inspire_institution_ids) > 1:
            child_resolution_status = (
                "unresolved-multiple-inspire-institution-identifiers"
            )
        elif (
            not anchor_ids
            and len(inspire_institution_ids) == 1
            and not supplemental_anchor_ids
        ):
            child_resolution_status = "unresolved-no-explicit-ror-crosswalk"
        elif matching_resolution is not None:
            child_resolution_status = str(matching_resolution["resolutionStatus"])
        else:
            child_resolution_status = "unresolved-no-direct-ror-anchor"
        if matching_resolution is not None and child_resolved:
            rollup_projection_status = str(
                matching_resolution["statisticalRollupStatus"]
            )
        elif authority_linked and paper_identity_status != "matched":
            rollup_projection_status = "withheld-paper-identity-needs-review"
        else:
            rollup_projection_status = "withheld-no-resolved-child-ror"
        child_resolution_mass_by_status[child_resolution_status] = (
            child_resolution_mass_by_status.get(child_resolution_status, Fraction(0))
            + weight
        )
        rollup_mass_by_status[rollup_projection_status] = (
            rollup_mass_by_status.get(rollup_projection_status, Fraction(0)) + weight
        )
        projection_canonical_manifest_checksum = (
            matching_resolution.get("canonicalManifestChecksum")
            if matching_resolution is not None
            else None
        )
        if not extended_resolution_schema:
            projection_canonical_manifest_checksum = canonical_manifest_checksums[0]
        projection = {
            "paperTimeAffiliationShareId": share_id,
            "candidateId": share.get("candidate_id"),
            "canonicalPaperId": share.get("canonical_paper_id"),
            "authorshipAppearanceId": share.get("authorship_appearance_id"),
            "paperIdentityStatus": paper_identity_status,
            "institutionAuthorityAnchorIds": anchor_ids,
            "originalResolutionStatus": share.get("resolution_status"),
            "resolutionStatus": child_resolution_status,
            "authorityLinkedCanonicalInstitutionId": authority_linked_institution_id,
            "canonicalInstitutionId": projected_institution_id,
            "countryId": projected_country_id,
            "statisticalRollupStatus": rollup_projection_status,
            "statisticalRollupInstitutionId": statistical_rollup_institution_id,
            "statisticalRollupCountryId": statistical_rollup_country_id,
            "attributionWeight": share["attribution_weight"],
            "replayBundleManifestChecksum": replay["bundle_manifest_checksum"],
            "canonicalManifestChecksum": projection_canonical_manifest_checksum,
            "sourceManifestChecksum": replay["source_manifest_checksum"],
            "resolutionVersion": HISTORICAL_INSTITUTION_RESOLUTION_VERSION,
            "eligibleForPublicMetrics": False,
        }
        if extended_resolution_schema:
            projection.update(
                {
                    "supplementalInstitutionAuthorityAnchorIds": (
                        supplemental_anchor_ids
                    ),
                    "effectiveInstitutionAuthorityAnchorIds": effective_anchor_ids,
                    "supplementalInspireInstitutionIds": list(inspire_institution_ids),
                    "supplementalCrosswalkManifestChecksum": (
                        supplemental_crosswalk_checksum
                        if supplemental_crosswalk_manifest_path is not None
                        else None
                    ),
                    "canonicalManifestChecksums": canonical_manifest_checksums,
                }
            )
        projection_rows.append(projection)

    expected_mass = Fraction(0)
    ledger_evaluated_mass = Fraction(0)
    unmaterialized_mass = Fraction(0)
    seen_candidates: set[str] = set()
    for ledger in ledgers:
        candidate_id = ledger.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in seen_candidates:
            raise HistoricalRorSafetyError(
                "fractional attribution ledger candidate identity is malformed"
            )
        seen_candidates.add(candidate_id)
        total_weight = _fraction_from_payload(ledger.get("total_weight"))
        missing_weight = _fraction_from_payload(ledger.get("unmaterialized_paper_mass"))
        if total_weight + missing_weight != Fraction(1):
            raise HistoricalRorSafetyError(
                "fractional attribution ledger does not conserve one paper"
            )
        if share_mass_by_candidate.get(candidate_id, Fraction(0)) != total_weight:
            raise HistoricalRorSafetyError(
                "affiliation share mass differs from its attribution ledger"
            )
        expected_mass += total_weight + missing_weight
        ledger_evaluated_mass += total_weight
        unmaterialized_mass += missing_weight
    if set(share_mass_by_candidate) - seen_candidates:
        raise HistoricalRorSafetyError(
            "affiliation share has no fractional attribution ledger"
        )
    if evaluated_mass != ledger_evaluated_mass:
        raise HistoricalRorSafetyError(
            "evaluated affiliation share mass differs from attribution ledgers"
        )
    child_withheld_mass = expected_mass - child_resolved_mass
    activation_withheld_mass = expected_mass - activation_rollup_mass
    if child_resolved_mass + child_withheld_mass != expected_mass:
        raise AssertionError(
            "institution resolution projection failed mass conservation"
        )
    if activation_rollup_mass + activation_withheld_mass != expected_mass:
        raise AssertionError("institution rollup projection failed mass conservation")
    child_coverage = (
        child_resolved_mass / expected_mass if expected_mass != 0 else Fraction(0)
    )
    gate_coverage = (
        activation_rollup_mass / expected_mass if expected_mass != 0 else Fraction(0)
    )
    authority_linked_coverage = (
        authority_linked_mass / expected_mass if expected_mass != 0 else Fraction(0)
    )
    output_root = _validate_external_path(output)
    resolution_artifact = _write_jsonl_artifact(
        output_root,
        directory="institution-resolutions",
        rows=resolution_rows,
    )
    projection_artifact = _write_jsonl_artifact(
        output_root,
        directory="affiliation-resolution-projections",
        rows=projection_rows,
    )
    return _write_content_addressed(
        output_root / "institution-resolution-manifests",
        {
            "manifest_version": HISTORICAL_INSTITUTION_RESOLUTION_VERSION,
            "replay_bundle_manifest_checksum": replay["bundle_manifest_checksum"],
            "canonical_manifest_checksum": (
                canonical_manifest_checksums[0]
                if len(canonical_manifest_checksums) == 1
                else None
            ),
            "acquisition_manifest_checksum": (
                acquisition_manifest_checksums[0]
                if len(acquisition_manifest_checksums) == 1
                else None
            ),
            "target_manifest_checksum": (
                target_manifest_checksums[0]
                if len(target_manifest_checksums) == 1
                else None
            ),
            "source_manifest_checksum": replay["source_manifest_checksum"],
            **(
                {
                    "canonical_manifest_checksums": canonical_manifest_checksums,
                    "supplemental_crosswalk_manifest_checksum": (
                        supplemental_crosswalk_checksum
                    ),
                    "acquisition_manifest_checksums": acquisition_manifest_checksums,
                    "target_manifest_checksums": target_manifest_checksums,
                }
                if extended_resolution_schema
                else {}
            ),
            "artifacts": [
                {
                    "role": "institution-authority-resolutions",
                    **resolution_artifact,
                },
                {
                    "role": "paper-time-affiliation-resolution-projections",
                    **projection_artifact,
                },
            ],
            "anchor_count": len(resolution_rows),
            **(
                {
                    "direct_anchor_count": len(anchors),
                    "supplemental_anchor_count": len(supplemental_anchor_by_recid),
                }
                if extended_resolution_schema
                else {}
            ),
            "resolved_anchor_count": sum(
                row["resolutionStatus"] == "resolved-exact-ror"
                for row in resolution_rows
            ),
            "unresolved_anchor_count": sum(
                row["resolutionStatus"] != "resolved-exact-ror"
                for row in resolution_rows
            ),
            "anchor_rollup_status_counts": {
                status: sum(
                    row["statisticalRollupStatus"] == status for row in resolution_rows
                )
                for status in sorted(
                    {str(row["statisticalRollupStatus"]) for row in resolution_rows}
                )
            },
            "organization_status_counts": {
                status: sum(
                    row["organizationStatus"] == status for row in resolution_rows
                )
                for status in sorted(
                    {str(row["organizationStatus"]) for row in resolution_rows}
                )
            },
            "affiliation_share_count": len(projection_rows),
            "resolved_affiliation_share_count": sum(
                row["resolutionStatus"] == "resolved-exact-ror-child"
                for row in projection_rows
            ),
            "unresolved_affiliation_share_count": sum(
                row["resolutionStatus"] != "resolved-exact-ror-child"
                for row in projection_rows
            ),
            "activation_eligible_rollup_share_count": sum(
                str(row["statisticalRollupStatus"]).startswith("eligible-")
                for row in projection_rows
            ),
            "activation_withheld_rollup_share_count": sum(
                not str(row["statisticalRollupStatus"]).startswith("eligible-")
                for row in projection_rows
            ),
            "child_resolution_mass_by_status": {
                status: _fraction_payload(mass)
                for status, mass in sorted(child_resolution_mass_by_status.items())
            },
            "rollup_mass_by_status": {
                status: _fraction_payload(mass)
                for status, mass in sorted(rollup_mass_by_status.items())
            },
            "expected_paper_mass": _fraction_payload(expected_mass),
            "evaluated_attribution_mass": _fraction_payload(evaluated_mass),
            "unmaterialized_paper_mass": _fraction_payload(unmaterialized_mass),
            "authority_linked_attribution_mass": _fraction_payload(
                authority_linked_mass
            ),
            "authority_linked_coverage": _fraction_payload(authority_linked_coverage),
            "resolved_attribution_mass": _fraction_payload(child_resolved_mass),
            "withheld_attribution_mass": _fraction_payload(child_withheld_mass),
            "canonical_child_resolution_coverage": _fraction_payload(child_coverage),
            "activation_eligible_rollup_attribution_mass": _fraction_payload(
                activation_rollup_mass
            ),
            "activation_withheld_rollup_attribution_mass": _fraction_payload(
                activation_withheld_mass
            ),
            "canonical_institution_coverage": _fraction_payload(gate_coverage),
            "canonical_institution_coverage_basis": (
                "activation-eligible-rollup-mass-over-expected-paper-mass"
            ),
            "statistical_rollup_policy_version": PARENT_ROLLUP_POLICY_VERSION,
            "mass_conservation_passed": True,
            "resolution_method": (
                "exact-direct-ror-anchor-plus-exact-inspire-recid-ror-crosswalk"
                if supplemental_crosswalk_manifest_path is not None
                else "exact-direct-ror-anchor-only"
            ),
            "name_matching": False,
            "positional_identifier_join": False,
            "offline_resolution": True,
            "database_access": False,
            "metric_observations_created": 0,
            "eligible_for_public_metrics": False,
            "institution_resolution_complete": True,
        },
        checksum_field="institution_resolution_manifest_checksum",
    )


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    target_path, target = write_target_manifest(args.source_manifest, args.output)
    result: dict[str, Any] = {
        "targetManifestPath": str(target_path),
        "targetManifest": target,
        "executed": args.execute,
    }
    exit_code = 0
    if args.execute:
        host = urlparse(OFFICIAL_ROR_BASE_URL).hostname
        assert host is not None
        with ProviderHttpTransport(
            allowed_hosts={host},
            minimum_intervals={host: RorConnector.min_interval_seconds},
        ) as transport:
            acquisition_path, acquisition = acquire_target_records(
                target_path,
                args.output,
                transport,
            )
        result["acquisitionManifestPath"] = str(acquisition_path)
        result["acquisitionManifest"] = acquisition
        exit_code = 0 if acquisition["acquisition_complete"] else 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
