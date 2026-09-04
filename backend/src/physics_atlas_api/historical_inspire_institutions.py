"""Staging-only INSPIRE-institution to ROR evidence acquisition.

The canonical replay preserves exact INSPIRE institution record identifiers on
paper-time affiliation assertions.  Those identifiers are provider
cross-references rather than canonical authorities, but the corresponding
INSPIRE institution record can contain an explicit ROR external identifier.
This module acquires only those already-evidenced institution records and
materializes a provenance-preserving exact crosswalk.  It never searches by
name, writes to the database, changes source cursors, or calculates metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .connectors.base import SourceTransport, normalize_external_id
from .connectors.http import ProviderHttpTransport
from .connectors.inspire import InspireConnector
from .historical_ror import (
    EXPECTED_REPLAY_BUNDLE_VERSION,
    EXPECTED_SCOPE,
    HISTORICAL_CANONICAL_INSTITUTION_VERSION,
    HISTORICAL_INSTITUTION_RESOLUTION_VERSION,
    HISTORICAL_ROR_TARGET_VERSION,
    PARENT_ROLLUP_POLICY_VERSION,
    HistoricalRorSafetyError,
    _canonical_json,
    _checksum,
    _content_addressed_document,
    _explicit_inspire_institution_ror_evidence,
    _fraction_from_payload,
    _fraction_payload,
    _is_within,
    _validate_external_path,
    _verified_jsonl_artifact,
    _write_content_addressed,
    _write_jsonl_artifact,
)

INSPIRE_INSTITUTION_TARGET_VERSION = (
    "hep-th-v1-historical-inspire-institution-targets-v1"
)
INSPIRE_INSTITUTION_STATE_VERSION = "hep-th-v1-historical-inspire-institution-state-v1"
INSPIRE_INSTITUTION_ACQUISITION_VERSION = (
    "hep-th-v1-historical-inspire-institution-acquisition-v1"
)
INSPIRE_ROR_CROSSWALK_VERSION = "hep-th-v1-inspire-ror-crosswalk-v1"
INSPIRE_ROR_SUPPLEMENTAL_PROJECTION_VERSION = (
    "hep-th-v1-inspire-ror-supplemental-institution-projection-v1"
)
OFFICIAL_INSPIRE_BASE_URL = "https://inspirehep.net/api"
STATE_CHECKPOINT_INTERVAL = 25


def _exact_inspire_institution_ids(share: Mapping[str, Any]) -> tuple[str, ...]:
    identifiers: set[str] = set()
    evidence = share.get("resolution_evidence", [])
    if not isinstance(evidence, list):
        raise HistoricalRorSafetyError("affiliation resolution evidence is malformed")
    for item in evidence:
        if not isinstance(item, Mapping):
            raise HistoricalRorSafetyError(
                "affiliation resolution evidence row is malformed"
            )
        provider_ids = item.get("provider_institution_identifiers", [])
        if not isinstance(provider_ids, list):
            raise HistoricalRorSafetyError(
                "provider institution identifiers are malformed"
            )
        for identifier in provider_ids:
            if not isinstance(identifier, Mapping):
                raise HistoricalRorSafetyError(
                    "provider institution identifier is malformed"
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
                    "INSPIRE institution identifier is not canonical"
                )
            identifiers.add(normalized[1])
    return tuple(sorted(identifiers))


def build_inspire_institution_target_manifest(
    replay_manifest_path: Path,
) -> dict[str, Any]:
    """Derive exact target recids from checksum-verified replay affiliations."""

    replay_path = _validate_external_path(replay_manifest_path)
    replay = _content_addressed_document(
        replay_path, checksum_field="bundle_manifest_checksum"
    )
    if (
        replay.get("bundle_version") != EXPECTED_REPLAY_BUNDLE_VERSION
        or replay.get("network_access") is not False
        or replay.get("database_access") is not False
        or replay.get("metric_observations_created") != 0
    ):
        raise HistoricalRorSafetyError("replay bundle is not an approved offline input")

    shares = _verified_jsonl_artifact(
        replay_path, replay, role="paper-time-affiliation-shares"
    )
    mass_by_id: dict[str, Fraction] = defaultdict(Fraction)
    share_count_by_id: dict[str, int] = defaultdict(int)
    excluded_direct_anchor_mass = Fraction(0)
    excluded_review_mass = Fraction(0)
    no_provider_id_mass = Fraction(0)
    multiple_provider_id_mass = Fraction(0)
    evaluated_mass = Fraction(0)
    for share in shares:
        weight = _fraction_from_payload(share.get("attribution_weight"))
        evaluated_mass += weight
        if share.get("paper_identity_status") != "matched":
            excluded_review_mass += weight
            continue
        anchors = share.get("institution_authority_anchor_ids")
        if not isinstance(anchors, list) or any(
            not isinstance(item, str) for item in anchors
        ):
            raise HistoricalRorSafetyError(
                "affiliation authority anchors are malformed"
            )
        if anchors:
            excluded_direct_anchor_mass += weight
            continue
        identifiers = _exact_inspire_institution_ids(share)
        if not identifiers:
            no_provider_id_mass += weight
            continue
        if len(identifiers) != 1:
            multiple_provider_id_mass += weight
            continue
        identifier = identifiers[0]
        mass_by_id[identifier] += weight
        share_count_by_id[identifier] += 1

    targets = [
        {
            "inspire_institution_id": identifier,
            "candidate_attribution_mass": _fraction_payload(mass),
            "candidate_share_count": share_count_by_id[identifier],
        }
        for identifier, mass in sorted(
            mass_by_id.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    target_mass = sum(mass_by_id.values(), start=Fraction(0))
    return {
        "manifest_version": INSPIRE_INSTITUTION_TARGET_VERSION,
        "acquisition_scope": EXPECTED_SCOPE,
        "replay_bundle_manifest_checksum": replay["bundle_manifest_checksum"],
        "source_manifest_checksum": replay["source_manifest_checksum"],
        "target_provider": "INSPIRE institutions",
        "target_method": (
            "exact-provider-institution-identifiers-from-matched-paper-time-"
            "affiliation-evidence"
        ),
        "target_priority": "descending-candidate-attribution-mass-then-recid",
        "registry_search": False,
        "name_matching": False,
        "database_access": False,
        "canonical_materialization": False,
        "affiliation_share_count": len(shares),
        "evaluated_attribution_mass": _fraction_payload(evaluated_mass),
        "target_count": len(targets),
        "target_candidate_attribution_mass": _fraction_payload(target_mass),
        "excluded_direct_ror_anchor_mass": _fraction_payload(
            excluded_direct_anchor_mass
        ),
        "excluded_paper_identity_review_mass": _fraction_payload(excluded_review_mass),
        "no_provider_institution_id_mass": _fraction_payload(no_provider_id_mass),
        "multiple_provider_institution_id_mass": _fraction_payload(
            multiple_provider_id_mass
        ),
        "targets": targets,
    }


def write_inspire_institution_target_manifest(
    replay_manifest_path: Path,
    output: Path,
) -> tuple[Path, dict[str, Any]]:
    output_root = _validate_external_path(output)
    return _write_content_addressed(
        output_root / "target-manifests",
        build_inspire_institution_target_manifest(replay_manifest_path),
        checksum_field="target_manifest_checksum",
    )


def _record_relative_path(record_id: str, checksum: str) -> Path:
    return Path("records") / record_id / f"{checksum}.json"


def _verify_record(output: Path, metadata: Mapping[str, Any]) -> dict[str, Any]:
    record_id = metadata.get("inspire_institution_id")
    checksum = metadata.get("checksum")
    path_value = metadata.get("path")
    if not all(isinstance(item, str) for item in (record_id, checksum, path_value)):
        raise HistoricalRorSafetyError(
            "INSPIRE institution record metadata is malformed"
        )
    assert isinstance(record_id, str)
    assert isinstance(checksum, str)
    assert isinstance(path_value, str)
    if Path(path_value) != _record_relative_path(record_id, checksum):
        raise HistoricalRorSafetyError(
            "INSPIRE institution record path is noncanonical"
        )
    path = (output / path_value).resolve()
    if not _is_within(path, output.resolve()):
        raise HistoricalRorSafetyError("INSPIRE institution record leaves output")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise HistoricalRorSafetyError(
            "INSPIRE institution record is missing"
        ) from error
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise HistoricalRorSafetyError("INSPIRE institution record checksum failed")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise HistoricalRorSafetyError(
            "INSPIRE institution record is malformed JSON"
        ) from error
    if (
        not isinstance(document, dict)
        or document.get("provider") != "inspire"
        or document.get("source_record_kind") != "institution"
        or document.get("source_record_id") != record_id
    ):
        raise HistoricalRorSafetyError("INSPIRE institution record identity failed")
    return document


def _load_resume_state(
    output: Path,
    *,
    target_manifest_checksum: str,
    target_ids: Sequence[str],
    base_url: str,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for path in sorted((output / "states").glob("*.json")):
        state = _content_addressed_document(path, checksum_field="state_checksum")
        if state.get("target_manifest_checksum") != target_manifest_checksum:
            continue
        if (
            state.get("state_version") != INSPIRE_INSTITUTION_STATE_VERSION
            or state.get("inspire_base_url") != base_url
        ):
            raise HistoricalRorSafetyError(
                "INSPIRE institution resume state changed acquisition policy"
            )
        records = state.get("records")
        next_index = state.get("next_index")
        if (
            not isinstance(records, list)
            or not isinstance(next_index, int)
            or isinstance(next_index, bool)
            or next_index != len(records)
            or next_index > len(target_ids)
        ):
            raise HistoricalRorSafetyError(
                "INSPIRE institution resume state is malformed"
            )
        observed = [
            item.get("inspire_institution_id")
            for item in records
            if isinstance(item, Mapping)
        ]
        if observed != list(target_ids[:next_index]) or any(
            not isinstance(item, Mapping) for item in records
        ):
            raise HistoricalRorSafetyError(
                "INSPIRE institution resume state is not a target prefix"
            )
        candidates.append(state)
    if not candidates:
        return None
    maximum = max(int(item["next_index"]) for item in candidates)
    finalists = [item for item in candidates if item["next_index"] == maximum]
    if len({_checksum(item["records"]) for item in finalists}) != 1:
        raise HistoricalRorSafetyError(
            "INSPIRE institution resume states conflict at one checkpoint"
        )
    selected = sorted(finalists, key=lambda item: str(item["state_checksum"]))[-1]
    for record in selected["records"]:
        _verify_record(output, record)
    return selected


def _write_state(
    output: Path,
    *,
    target_manifest: Mapping[str, Any],
    base_url: str,
    records: Sequence[Mapping[str, Any]],
    status: str,
    error: str | None,
) -> None:
    _write_content_addressed(
        output / "states",
        {
            "state_version": INSPIRE_INSTITUTION_STATE_VERSION,
            "target_manifest_checksum": target_manifest["target_manifest_checksum"],
            "source_manifest_checksum": target_manifest["source_manifest_checksum"],
            "inspire_base_url": base_url,
            "next_index": len(records),
            "records": list(records),
            "status": status,
            "error": error,
        },
        checksum_field="state_checksum",
    )


def _store_record(
    output: Path,
    *,
    record_id: str,
    payload: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
    captured_at: datetime,
) -> dict[str, Any]:
    document = {
        "provider": "inspire",
        "source_version": "INSPIRE REST API institutions endpoint",
        "source_record_kind": "institution",
        "source_record_id": record_id,
        "evidence_type": "provider-content-snapshot",
        "captured_at": captured_at.astimezone(UTC).isoformat(),
        "target_manifest_checksum": target_manifest["target_manifest_checksum"],
        "source_manifest_checksum": target_manifest["source_manifest_checksum"],
        "raw": dict(payload),
    }
    bytes_value = _canonical_json(document) + b"\n"
    checksum = hashlib.sha256(bytes_value).hexdigest()
    relative = _record_relative_path(record_id, checksum)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(bytes_value)
    except FileExistsError as error:
        if destination.read_bytes() != bytes_value:
            raise HistoricalRorSafetyError(
                "content-addressed INSPIRE institution record differs"
            ) from error
    return {
        "inspire_institution_id": record_id,
        "path": relative.as_posix(),
        "checksum": checksum,
        "captured_at": document["captured_at"],
    }


def acquire_inspire_institution_records(
    target_manifest_path: Path,
    output: Path,
    transport: SourceTransport,
    *,
    base_url: str = OFFICIAL_INSPIRE_BASE_URL,
    max_new_records: int | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[Path, dict[str, Any]]:
    """Acquire an exact resumable target prefix without provider search."""

    output_root = _validate_external_path(output)
    target = _content_addressed_document(
        target_manifest_path.resolve(), checksum_field="target_manifest_checksum"
    )
    targets = target.get("targets")
    if (
        target.get("manifest_version") != INSPIRE_INSTITUTION_TARGET_VERSION
        or target.get("acquisition_scope") != EXPECTED_SCOPE
        or target.get("registry_search") is not False
        or target.get("name_matching") is not False
        or not isinstance(targets, list)
        or target.get("target_count") != len(targets)
    ):
        raise HistoricalRorSafetyError(
            "INSPIRE institution target manifest is not approved"
        )
    if max_new_records is not None and max_new_records < 1:
        raise ValueError("max_new_records must be positive")
    target_ids: list[str] = []
    for item in targets:
        record_id = (
            item.get("inspire_institution_id") if isinstance(item, Mapping) else None
        )
        if not isinstance(record_id, str) or not record_id.isdigit():
            raise HistoricalRorSafetyError("INSPIRE institution targets are malformed")
        target_ids.append(record_id)
    if len(set(target_ids)) != len(target_ids):
        raise HistoricalRorSafetyError("INSPIRE institution targets are duplicated")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HistoricalRorSafetyError("INSPIRE institution endpoint is malformed")

    previous = _load_resume_state(
        output_root,
        target_manifest_checksum=str(target["target_manifest_checksum"]),
        target_ids=target_ids,
        base_url=base_url,
    )
    records: list[Mapping[str, Any]] = (
        list(previous["records"]) if previous is not None else []
    )
    stop_index = len(target_ids)
    if max_new_records is not None:
        stop_index = min(stop_index, len(records) + max_new_records)
    terminal_status = "complete"
    error_message: str | None = None
    for record_id in target_ids[len(records) : stop_index]:
        assert isinstance(record_id, str)
        try:
            payload = transport.get_json(
                f"{base_url.rstrip('/')}/institutions/{record_id}"
            )
            metadata = payload.get("metadata")
            observed = payload.get("id")
            if not isinstance(metadata, Mapping):
                raise HistoricalRorSafetyError(
                    f"INSPIRE institution response {record_id} lacks metadata"
                )
            control_number = metadata.get("control_number")
            if str(observed) != record_id or str(control_number) != record_id:
                raise HistoricalRorSafetyError(
                    f"INSPIRE institution response did not match target {record_id}"
                )
            records.append(
                _store_record(
                    output_root,
                    record_id=record_id,
                    payload=payload,
                    target_manifest=target,
                    captured_at=now(),
                )
            )
            if len(records) % STATE_CHECKPOINT_INTERVAL == 0:
                _write_state(
                    output_root,
                    target_manifest=target,
                    base_url=base_url,
                    records=records,
                    status="in-progress",
                    error=None,
                )
        except Exception as error:  # noqa: BLE001 - checkpoint before safe resume
            terminal_status = "failed"
            error_message = f"{type(error).__name__}: {error}"[:1000]
            _write_state(
                output_root,
                target_manifest=target,
                base_url=base_url,
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
        target_manifest=target,
        base_url=base_url,
        records=records,
        status="complete" if complete else terminal_status,
        error=error_message,
    )
    return _write_content_addressed(
        output_root / "acquisition-manifests",
        {
            "manifest_version": INSPIRE_INSTITUTION_ACQUISITION_VERSION,
            "target_manifest_checksum": target["target_manifest_checksum"],
            "replay_bundle_manifest_checksum": target[
                "replay_bundle_manifest_checksum"
            ],
            "source_manifest_checksum": target["source_manifest_checksum"],
            "inspire_base_url": base_url,
            "target_count": len(target_ids),
            "records_completed": len(records),
            "records": list(records),
            "terminal_status": "complete" if complete else terminal_status,
            "acquisition_complete": complete,
            "error": error_message,
            "registry_search": False,
            "name_matching": False,
            "database_access": False,
            "canonical_materialization": False,
        },
        checksum_field="acquisition_manifest_checksum",
    )


def materialize_explicit_ror_crosswalk(
    acquisition_manifest_path: Path,
    output: Path,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    """Materialize exact recid-to-ROR evidence and a target-only ROR manifest."""

    acquisition_path = _validate_external_path(acquisition_manifest_path)
    acquisition = _content_addressed_document(
        acquisition_path, checksum_field="acquisition_manifest_checksum"
    )
    if (
        acquisition.get("manifest_version") != INSPIRE_INSTITUTION_ACQUISITION_VERSION
        or acquisition.get("terminal_status") != "complete"
        or acquisition.get("acquisition_complete") is not True
        or acquisition.get("registry_search") is not False
        or acquisition.get("name_matching") is not False
        or acquisition.get("database_access") is not False
    ):
        raise HistoricalRorSafetyError(
            "crosswalk requires a complete exact institution acquisition"
        )
    records = acquisition.get("records")
    if (
        not isinstance(records, list)
        or acquisition.get("records_completed") != len(records)
        or acquisition.get("target_count") != len(records)
    ):
        raise HistoricalRorSafetyError("crosswalk acquisition records are inconsistent")
    acquisition_root = acquisition_path.parent.parent.resolve()
    target_checksum = acquisition.get("target_manifest_checksum")
    if not isinstance(target_checksum, str):
        raise HistoricalRorSafetyError("institution acquisition lacks target lineage")
    target_path = acquisition_root / "target-manifests" / f"{target_checksum}.json"
    target = _content_addressed_document(
        target_path, checksum_field="target_manifest_checksum"
    )
    target_entries = target.get("targets")
    if (
        target.get("manifest_version") != INSPIRE_INSTITUTION_TARGET_VERSION
        or target.get("acquisition_scope") != EXPECTED_SCOPE
        or target.get("registry_search") is not False
        or target.get("name_matching") is not False
        or target.get("source_manifest_checksum")
        != acquisition.get("source_manifest_checksum")
        or target.get("replay_bundle_manifest_checksum")
        != acquisition.get("replay_bundle_manifest_checksum")
        or not isinstance(target_entries, list)
        or target.get("target_count") != len(target_entries)
        or acquisition.get("target_count") != len(target_entries)
    ):
        raise HistoricalRorSafetyError(
            "institution target and acquisition lineage is inconsistent"
        )
    target_ids: list[str] = []
    mass_by_id: dict[str, Fraction] = {}
    for item in target_entries:
        if not isinstance(item, Mapping):
            raise HistoricalRorSafetyError("institution target entry is malformed")
        record_id = item.get("inspire_institution_id")
        if (
            not isinstance(record_id, str)
            or not record_id.isdigit()
            or record_id in mass_by_id
        ):
            raise HistoricalRorSafetyError(
                "institution target identifiers are malformed or duplicated"
            )
        target_ids.append(record_id)
        mass_by_id[record_id] = _fraction_from_payload(
            item.get("candidate_attribution_mass")
        )

    observed_record_ids = [
        item.get("inspire_institution_id")
        for item in records
        if isinstance(item, Mapping)
    ]
    if len(observed_record_ids) != len(records) or observed_record_ids != target_ids:
        raise HistoricalRorSafetyError(
            "institution acquisition records are not the exact target sequence"
        )

    rows: list[dict[str, Any]] = []
    exact_mass = Fraction(0)
    unresolved_mass = Fraction(0)
    ambiguous_mass = Fraction(0)
    ror_targets: set[str] = set()
    for record_metadata in records:
        if not isinstance(record_metadata, Mapping):
            raise HistoricalRorSafetyError("institution record metadata is malformed")
        document = _verify_record(acquisition_root, record_metadata)
        record_id = str(document["source_record_id"])
        if record_id not in mass_by_id:
            raise HistoricalRorSafetyError("institution record is not an exact target")
        if document.get("target_manifest_checksum") != target_checksum or document.get(
            "source_manifest_checksum"
        ) != acquisition.get("source_manifest_checksum"):
            raise HistoricalRorSafetyError(
                "institution record lineage differs from its acquisition"
            )
        raw = document.get("raw")
        if not isinstance(raw, Mapping):
            raise HistoricalRorSafetyError("institution raw snapshot is malformed")
        ror_ids, status = _explicit_inspire_institution_ror_evidence(raw)
        mass = mass_by_id[record_id]
        if status == "resolved-exact-explicit-ror-cross-reference":
            exact_mass += mass
            ror_targets.add(ror_ids[0])
        elif status == "ambiguous-multiple-explicit-ror-cross-references":
            ambiguous_mass += mass
        else:
            unresolved_mass += mass
        rows.append(
            {
                "inspireInstitutionId": record_id,
                "rorIds": list(ror_ids),
                "resolutionStatus": status,
                "candidateAttributionMass": _fraction_payload(mass),
                "sourceRecordChecksum": record_metadata["checksum"],
                "sourceRecordPath": record_metadata["path"],
                "capturedAt": record_metadata["captured_at"],
                "targetManifestChecksum": target_checksum,
                "acquisitionManifestChecksum": acquisition[
                    "acquisition_manifest_checksum"
                ],
                "crosswalkVersion": INSPIRE_ROR_CROSSWALK_VERSION,
                "nameMatching": False,
                "eligibleForPublicMetrics": False,
            }
        )

    output_root = _validate_external_path(output)
    artifact = _write_jsonl_artifact(
        output_root,
        directory="crosswalks",
        rows=sorted(rows, key=lambda item: str(item["inspireInstitutionId"])),
    )
    crosswalk_path, crosswalk = _write_content_addressed(
        output_root / "crosswalk-manifests",
        {
            "manifest_version": INSPIRE_ROR_CROSSWALK_VERSION,
            "source_manifest_checksum": acquisition["source_manifest_checksum"],
            "replay_bundle_manifest_checksum": acquisition[
                "replay_bundle_manifest_checksum"
            ],
            "target_manifest_checksum": target_checksum,
            "acquisition_manifest_checksum": acquisition[
                "acquisition_manifest_checksum"
            ],
            "acquisition_complete": acquisition["acquisition_complete"],
            "target_count": acquisition["target_count"],
            "records_examined": len(rows),
            "exact_ror_crosswalk_count": sum(
                row["resolutionStatus"] == "resolved-exact-explicit-ror-cross-reference"
                for row in rows
            ),
            "unresolved_crosswalk_count": sum(
                row["resolutionStatus"] == "unresolved-no-explicit-ror-cross-reference"
                for row in rows
            ),
            "ambiguous_crosswalk_count": sum(
                row["resolutionStatus"]
                == "ambiguous-multiple-explicit-ror-cross-references"
                for row in rows
            ),
            "exact_ror_candidate_attribution_mass": _fraction_payload(exact_mass),
            "unresolved_candidate_attribution_mass": _fraction_payload(unresolved_mass),
            "ambiguous_candidate_attribution_mass": _fraction_payload(ambiguous_mass),
            "artifact": artifact,
            "resolution_method": "exact-explicit-provider-cross-reference-only",
            "registry_search": False,
            "name_matching": False,
            "database_access": False,
            "metric_observations_created": 0,
            "eligible_for_public_metrics": False,
        },
        checksum_field="crosswalk_manifest_checksum",
    )
    ror_target_path, ror_target = _write_content_addressed(
        output_root / "target-manifests",
        {
            "manifest_version": HISTORICAL_ROR_TARGET_VERSION,
            "acquisition_scope": EXPECTED_SCOPE,
            "source_manifest_checksum": acquisition["source_manifest_checksum"],
            "source_crosswalk_manifest_checksum": crosswalk[
                "crosswalk_manifest_checksum"
            ],
            "target_authority": "ROR",
            "target_method": "exact-explicit-ror-ids-from-inspire-institution-records",
            "registry_search": False,
            "database_access": False,
            "canonical_materialization": False,
            "target_count": len(ror_targets),
            "target_ids": sorted(ror_targets),
        },
        checksum_field="target_manifest_checksum",
    )
    return crosswalk_path, crosswalk, ror_target_path, ror_target


def _verified_crosswalk_rows(
    manifest_path: Path, manifest: Mapping[str, Any]
) -> list[dict[str, Any]]:
    artifact = manifest.get("artifact")
    if not isinstance(artifact, Mapping):
        raise HistoricalRorSafetyError("crosswalk artifact metadata is malformed")
    relative_value = artifact.get("path")
    checksum = artifact.get("checksum")
    row_count = artifact.get("row_count")
    if (
        not isinstance(relative_value, str)
        or not isinstance(checksum, str)
        or not isinstance(row_count, int)
        or isinstance(row_count, bool)
    ):
        raise HistoricalRorSafetyError("crosswalk artifact metadata is malformed")
    root = manifest_path.parent.parent.resolve()
    path = (root / relative_value).resolve()
    if Path(relative_value).is_absolute() or not _is_within(path, root):
        raise HistoricalRorSafetyError("crosswalk artifact leaves its root")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise HistoricalRorSafetyError("crosswalk artifact is missing") from error
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise HistoricalRorSafetyError("crosswalk artifact checksum failed")
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise HistoricalRorSafetyError("crosswalk artifact is malformed") from error
        if not isinstance(row, dict):
            raise HistoricalRorSafetyError("crosswalk artifact row is not an object")
        rows.append(row)
    if len(rows) != row_count:
        raise HistoricalRorSafetyError("crosswalk artifact row count failed")
    return rows


def _canonical_authorities(
    manifest_paths: Sequence[Path],
    *,
    source_manifest_checksum: str,
) -> tuple[dict[str, dict[str, Any]], tuple[str, ...]]:
    result: dict[str, dict[str, Any]] = {}
    manifests: dict[str, tuple[Path, dict[str, Any]]] = {}
    for manifest_path in manifest_paths:
        path = _validate_external_path(manifest_path)
        manifest = _content_addressed_document(
            path, checksum_field="canonical_manifest_checksum"
        )
        manifest_checksum = manifest.get("canonical_manifest_checksum")
        if not isinstance(manifest_checksum, str):
            raise HistoricalRorSafetyError(
                "canonical institution manifest checksum is malformed"
            )
        manifests.setdefault(manifest_checksum, (path, manifest))
    for manifest_checksum in sorted(manifests):
        path, manifest = manifests[manifest_checksum]
        if (
            manifest.get("manifest_version") != HISTORICAL_CANONICAL_INSTITUTION_VERSION
            or manifest.get("canonical_materialization_complete") is not True
            or manifest.get("offline_normalization") is not True
            or manifest.get("database_access") is not False
            or manifest.get("affiliation_join") is not False
            or manifest.get("source_manifest_checksum") != source_manifest_checksum
            or not isinstance(manifest.get("target_manifest_checksum"), str)
            or not isinstance(manifest.get("acquisition_manifest_checksum"), str)
        ):
            raise HistoricalRorSafetyError(
                "canonical institution manifest is not an approved lineage input"
            )
        relative_value = manifest.get("artifact_path")
        checksum = manifest.get("artifact_checksum")
        row_count = manifest.get("record_count")
        if (
            not isinstance(relative_value, str)
            or not isinstance(checksum, str)
            or not isinstance(row_count, int)
            or isinstance(row_count, bool)
        ):
            raise HistoricalRorSafetyError(
                "canonical institution artifact metadata is malformed"
            )
        root = path.parent.parent.resolve()
        artifact_path = (root / relative_value).resolve()
        if Path(relative_value).is_absolute() or not _is_within(artifact_path, root):
            raise HistoricalRorSafetyError(
                "canonical institution artifact leaves its root"
            )
        try:
            payload = artifact_path.read_bytes()
        except OSError as error:
            raise HistoricalRorSafetyError(
                "canonical institution artifact is missing"
            ) from error
        if hashlib.sha256(payload).hexdigest() != checksum:
            raise HistoricalRorSafetyError(
                "canonical institution artifact checksum failed"
            )
        rows = payload.splitlines()
        if len(rows) != row_count:
            raise HistoricalRorSafetyError(
                "canonical institution artifact row count failed"
            )
        for line in rows:
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise HistoricalRorSafetyError(
                    "canonical institution artifact is malformed"
                ) from error
            if not isinstance(row, dict) or not isinstance(row.get("rorId"), str):
                raise HistoricalRorSafetyError(
                    "canonical institution artifact row is malformed"
                )
            ror_id = row["rorId"]
            if (
                normalize_external_id("ror", ror_id) != ("ror", ror_id)
                or row.get("canonicalInstitutionId") != f"institution-ror-{ror_id}"
                or row.get("sourceManifestChecksum") != source_manifest_checksum
                or row.get("targetManifestChecksum")
                != manifest.get("target_manifest_checksum")
                or row.get("acquisitionManifestChecksum")
                != manifest.get("acquisition_manifest_checksum")
            ):
                raise HistoricalRorSafetyError(
                    "canonical institution row identity or lineage is inconsistent"
                )
            if ror_id in result:
                raise HistoricalRorSafetyError(
                    "canonical institution manifests duplicate one ROR"
                )
            result[ror_id] = row
    return result, tuple(sorted(manifests))


def _complete_authority(authority: Mapping[str, Any] | None, ror_id: str) -> bool:
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


def project_supplemental_institution_coverage(
    replay_manifest_path: Path,
    baseline_resolution_manifest_path: Path,
    crosswalk_manifest_path: Path,
    canonical_manifest_paths: Sequence[Path],
    output: Path,
) -> tuple[Path, dict[str, Any]]:
    """Apply strict PA-035 rollup to exact crosswalk evidence, offline only."""

    replay_path = _validate_external_path(replay_manifest_path)
    replay = _content_addressed_document(
        replay_path, checksum_field="bundle_manifest_checksum"
    )
    if (
        replay.get("bundle_version") != EXPECTED_REPLAY_BUNDLE_VERSION
        or replay.get("network_access") is not False
        or replay.get("database_access") is not False
        or replay.get("metric_observations_created") != 0
    ):
        raise HistoricalRorSafetyError("replay bundle is not an approved input")
    shares = _verified_jsonl_artifact(
        replay_path, replay, role="paper-time-affiliation-shares"
    )

    baseline_path = _validate_external_path(baseline_resolution_manifest_path)
    baseline = _content_addressed_document(
        baseline_path, checksum_field="institution_resolution_manifest_checksum"
    )
    if (
        baseline.get("manifest_version") != HISTORICAL_INSTITUTION_RESOLUTION_VERSION
        or baseline.get("replay_bundle_manifest_checksum")
        != replay.get("bundle_manifest_checksum")
        or baseline.get("source_manifest_checksum")
        != replay.get("source_manifest_checksum")
        or baseline.get("mass_conservation_passed") is not True
    ):
        raise HistoricalRorSafetyError(
            "baseline institution resolution is not an approved lineage input"
        )
    baseline_rows = _verified_jsonl_artifact(
        baseline_path,
        baseline,
        role="paper-time-affiliation-resolution-projections",
    )
    share_ids: set[str] = set()
    for share in shares:
        share_id = share.get("paper_time_affiliation_share_id")
        if not isinstance(share_id, str) or share_id in share_ids:
            raise HistoricalRorSafetyError(
                "replay affiliation share identities are malformed or duplicated"
            )
        share_ids.add(share_id)
    baseline_by_share: dict[str, dict[str, Any]] = {}
    for row in baseline_rows:
        share_id = row.get("paperTimeAffiliationShareId")
        if not isinstance(share_id, str) or share_id in baseline_by_share:
            raise HistoricalRorSafetyError(
                "baseline projection share identities are malformed or duplicated"
            )
        baseline_by_share[share_id] = row
    if set(baseline_by_share) != share_ids:
        raise HistoricalRorSafetyError(
            "baseline institution projection is not one-to-one with replay shares"
        )

    crosswalk_path = _validate_external_path(crosswalk_manifest_path)
    crosswalk = _content_addressed_document(
        crosswalk_path, checksum_field="crosswalk_manifest_checksum"
    )
    if (
        crosswalk.get("manifest_version") != INSPIRE_ROR_CROSSWALK_VERSION
        or crosswalk.get("replay_bundle_manifest_checksum")
        != replay.get("bundle_manifest_checksum")
        or crosswalk.get("source_manifest_checksum")
        != replay.get("source_manifest_checksum")
        or crosswalk.get("acquisition_complete") is not True
        or crosswalk.get("registry_search") is not False
        or crosswalk.get("name_matching") is not False
        or crosswalk.get("database_access") is not False
        or crosswalk.get("metric_observations_created") != 0
        or crosswalk.get("eligible_for_public_metrics") is not False
        or not isinstance(crosswalk.get("target_manifest_checksum"), str)
        or not isinstance(crosswalk.get("acquisition_manifest_checksum"), str)
    ):
        raise HistoricalRorSafetyError("crosswalk is not an approved lineage input")
    ror_by_recid: dict[str, str] = {}
    crosswalk_rows = _verified_crosswalk_rows(crosswalk_path, crosswalk)
    target_count = crosswalk.get("target_count")
    status_counts = [
        crosswalk.get(field)
        for field in (
            "exact_ror_crosswalk_count",
            "unresolved_crosswalk_count",
            "ambiguous_crosswalk_count",
        )
    ]
    status_count_total = 0
    for count in status_counts:
        if not isinstance(count, int) or isinstance(count, bool):
            raise HistoricalRorSafetyError("crosswalk status counts are malformed")
        status_count_total += count
    if (
        not isinstance(target_count, int)
        or isinstance(target_count, bool)
        or target_count != len(crosswalk_rows)
        or crosswalk.get("records_examined") != len(crosswalk_rows)
        or status_count_total != target_count
    ):
        raise HistoricalRorSafetyError("crosswalk target coverage is incomplete")
    seen_recids: set[str] = set()
    crosswalk_root = crosswalk_path.parent.parent.resolve()
    for row in crosswalk_rows:
        recid = row.get("inspireInstitutionId")
        ror_ids = row.get("rorIds")
        if (
            not isinstance(recid, str)
            or not recid.isdigit()
            or recid in seen_recids
            or not isinstance(ror_ids, list)
            or any(not isinstance(item, str) for item in ror_ids)
            or row.get("targetManifestChecksum")
            != crosswalk.get("target_manifest_checksum")
            or row.get("acquisitionManifestChecksum")
            != crosswalk.get("acquisition_manifest_checksum")
            or row.get("crosswalkVersion") != INSPIRE_ROR_CROSSWALK_VERSION
            or row.get("nameMatching") is not False
            or row.get("eligibleForPublicMetrics") is not False
        ):
            raise HistoricalRorSafetyError("crosswalk row is malformed")
        source_document = _verify_record(
            crosswalk_root,
            {
                "inspire_institution_id": recid,
                "checksum": row.get("sourceRecordChecksum"),
                "path": row.get("sourceRecordPath"),
            },
        )
        if (
            source_document.get("target_manifest_checksum")
            != crosswalk.get("target_manifest_checksum")
            or source_document.get("source_manifest_checksum")
            != crosswalk.get("source_manifest_checksum")
            or source_document.get("captured_at") != row.get("capturedAt")
        ):
            raise HistoricalRorSafetyError(
                "crosswalk source record lineage is inconsistent"
            )
        raw = source_document.get("raw")
        if not isinstance(raw, Mapping):
            raise HistoricalRorSafetyError(
                "crosswalk source record raw snapshot is malformed"
            )
        source_ror_ids, source_status = _explicit_inspire_institution_ror_evidence(raw)
        status = row.get("resolutionStatus")
        if tuple(ror_ids) != source_ror_ids or status != source_status:
            raise HistoricalRorSafetyError(
                "crosswalk ROR evidence differs from its source snapshot"
            )
        seen_recids.add(recid)
        if any(
            normalize_external_id("ror", ror_id) != ("ror", ror_id)
            for ror_id in ror_ids
        ):
            raise HistoricalRorSafetyError("crosswalk ROR identifier is malformed")
        if status == "resolved-exact-explicit-ror-cross-reference":
            if len(ror_ids) != 1:
                raise HistoricalRorSafetyError("resolved crosswalk row is malformed")
            ror_by_recid[recid] = ror_ids[0]
        elif status == "unresolved-no-explicit-ror-cross-reference":
            if ror_ids:
                raise HistoricalRorSafetyError(
                    "unresolved crosswalk row unexpectedly carries a ROR"
                )
        elif status == "ambiguous-multiple-explicit-ror-cross-references":
            if len(set(ror_ids)) < 2:
                raise HistoricalRorSafetyError("ambiguous crosswalk row is malformed")
        else:
            raise HistoricalRorSafetyError("crosswalk resolution status is unsupported")

    authorities, canonical_manifest_checksums = _canonical_authorities(
        canonical_manifest_paths,
        source_manifest_checksum=str(replay["source_manifest_checksum"]),
    )
    added_mass = Fraction(0)
    candidate_mass = Fraction(0)
    mass_by_status: dict[str, Fraction] = defaultdict(Fraction)
    count_by_status: dict[str, int] = defaultdict(int)
    supplemental_rows: list[dict[str, Any]] = []
    for share in shares:
        share_id = share.get("paper_time_affiliation_share_id")
        if not isinstance(share_id, str) or share_id not in baseline_by_share:
            raise HistoricalRorSafetyError("replay affiliation share identity failed")
        base_row = baseline_by_share[share_id]
        if str(base_row.get("statisticalRollupStatus", "")).startswith("eligible-"):
            continue
        if share.get("paper_identity_status") != "matched" or share.get(
            "institution_authority_anchor_ids"
        ):
            continue
        recids = _exact_inspire_institution_ids(share)
        if len(recids) != 1 or recids[0] not in ror_by_recid:
            continue
        recid = recids[0]
        ror_id = ror_by_recid[recid]
        weight = _fraction_from_payload(share.get("attribution_weight"))
        candidate_mass += weight
        authority = authorities.get(ror_id)
        rollup_authority: Mapping[str, Any] | None = None
        status = "withheld-child-ror-metadata-unavailable"
        if _complete_authority(authority, ror_id):
            assert authority is not None
            if str(authority.get("organizationStatus", "")).casefold() != "active":
                status = "withheld-child-lifecycle-status-not-active"
            else:
                parent_ids: set[str] = set()
                invalid_parent_count = 0
                relationships = authority.get("authorityRelationshipEvidence", [])
                if not isinstance(relationships, list):
                    raise HistoricalRorSafetyError(
                        "canonical authority relationships are malformed"
                    )
                for relationship in relationships:
                    if not isinstance(relationship, Mapping):
                        raise HistoricalRorSafetyError(
                            "canonical authority relationship is malformed"
                        )
                    if str(relationship.get("type", "")).casefold() != "parent":
                        continue
                    parent_id = relationship.get("rorId")
                    if isinstance(parent_id, str):
                        parent_ids.add(parent_id)
                    else:
                        invalid_parent_count += 1
                if invalid_parent_count:
                    status = "withheld-invalid-parent-ror-evidence"
                elif not parent_ids:
                    status = "eligible-self-rollup"
                    rollup_authority = authority
                elif len(parent_ids) > 1:
                    status = "withheld-multiple-parent-rors"
                else:
                    parent_id = next(iter(parent_ids))
                    parent = authorities.get(parent_id)
                    if not _complete_authority(parent, parent_id):
                        status = "withheld-parent-ror-metadata-unavailable"
                    else:
                        assert parent is not None
                        if (
                            str(parent.get("organizationStatus", "")).casefold()
                            != "active"
                        ):
                            status = "withheld-parent-lifecycle-status-not-active"
                        else:
                            status = "eligible-exact-ror-parent-rollup"
                            rollup_authority = parent
        mass_by_status[status] += weight
        count_by_status[status] += 1
        if status.startswith("eligible-"):
            added_mass += weight
        supplemental_rows.append(
            {
                "paperTimeAffiliationShareId": share_id,
                "candidateId": share.get("candidate_id"),
                "inspireInstitutionId": recid,
                "crosswalkRorId": ror_id,
                "statisticalRollupStatus": status,
                "statisticalRollupInstitutionId": (
                    rollup_authority.get("canonicalInstitutionId")
                    if rollup_authority is not None
                    else None
                ),
                "statisticalRollupCountryId": (
                    f"country-{str(rollup_authority['countryCode']).casefold()}"
                    if rollup_authority is not None
                    else None
                ),
                "attributionWeight": share["attribution_weight"],
                "baselineInstitutionResolutionManifestChecksum": baseline[
                    "institution_resolution_manifest_checksum"
                ],
                "crosswalkManifestChecksum": crosswalk["crosswalk_manifest_checksum"],
                "projectionVersion": INSPIRE_ROR_SUPPLEMENTAL_PROJECTION_VERSION,
                "eligibleForPublicMetrics": False,
            }
        )

    expected_mass = _fraction_from_payload(baseline.get("expected_paper_mass"))
    baseline_mass = _fraction_from_payload(
        baseline.get("activation_eligible_rollup_attribution_mass")
    )
    combined_mass = baseline_mass + added_mass
    if combined_mass > expected_mass:
        raise HistoricalRorSafetyError(
            "supplemental institution projection exceeds expected paper mass"
        )
    output_root = _validate_external_path(output)
    artifact = _write_jsonl_artifact(
        output_root,
        directory="supplemental-institution-projections",
        rows=sorted(
            supplemental_rows,
            key=lambda item: str(item["paperTimeAffiliationShareId"]),
        ),
    )
    return _write_content_addressed(
        output_root / "supplemental-institution-projection-manifests",
        {
            "manifest_version": INSPIRE_ROR_SUPPLEMENTAL_PROJECTION_VERSION,
            "replay_bundle_manifest_checksum": replay["bundle_manifest_checksum"],
            "source_manifest_checksum": replay["source_manifest_checksum"],
            "baseline_institution_resolution_manifest_checksum": baseline[
                "institution_resolution_manifest_checksum"
            ],
            "crosswalk_manifest_checksum": crosswalk["crosswalk_manifest_checksum"],
            "canonical_manifest_checksums": list(canonical_manifest_checksums),
            "artifact": artifact,
            "candidate_share_count": len(supplemental_rows),
            "candidate_attribution_mass": _fraction_payload(candidate_mass),
            "supplemental_rollup_status_counts": dict(sorted(count_by_status.items())),
            "supplemental_rollup_mass_by_status": {
                status: _fraction_payload(mass)
                for status, mass in sorted(mass_by_status.items())
            },
            "expected_paper_mass": _fraction_payload(expected_mass),
            "baseline_activation_eligible_mass": _fraction_payload(baseline_mass),
            "added_activation_eligible_mass": _fraction_payload(added_mass),
            "combined_activation_eligible_mass": _fraction_payload(combined_mass),
            "combined_canonical_institution_coverage": _fraction_payload(
                combined_mass / expected_mass
            ),
            "statistical_rollup_policy_version": PARENT_ROLLUP_POLICY_VERSION,
            "resolution_method": (
                "exact-inspire-recid-to-explicit-ror-cross-reference-only"
            ),
            "name_matching": False,
            "offline_projection": True,
            "database_access": False,
            "metric_observations_created": 0,
            "eligible_for_public_metrics": False,
            "mass_conservation_passed": True,
        },
        checksum_field="supplemental_projection_manifest_checksum",
    )


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-new-records", type=int)
    args = parser.parse_args(argv)

    target_path, target = write_inspire_institution_target_manifest(
        args.replay_manifest, args.output
    )
    result: dict[str, Any] = {
        "targetManifestPath": str(target_path),
        "targetManifest": target,
        "executed": args.execute,
    }
    exit_code = 0
    if args.execute:
        host = urlparse(OFFICIAL_INSPIRE_BASE_URL).hostname
        assert host is not None
        with ProviderHttpTransport(
            allowed_hosts={host},
            minimum_intervals={host: InspireConnector.min_interval_seconds},
        ) as transport:
            acquisition_path, acquisition = acquire_inspire_institution_records(
                target_path,
                args.output,
                transport,
                max_new_records=args.max_new_records,
            )
        result["acquisitionManifestPath"] = str(acquisition_path)
        result["acquisitionManifest"] = acquisition
        if acquisition["acquisition_complete"]:
            (
                crosswalk_path,
                crosswalk,
                ror_target_path,
                ror_target,
            ) = materialize_explicit_ror_crosswalk(acquisition_path, args.output)
            result.update(
                {
                    "crosswalkManifestPath": str(crosswalk_path),
                    "crosswalkManifest": crosswalk,
                    "rorTargetManifestPath": str(ror_target_path),
                    "rorTargetManifest": ror_target,
                }
            )
        exit_code = 1 if acquisition["terminal_status"] == "failed" else 0
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
