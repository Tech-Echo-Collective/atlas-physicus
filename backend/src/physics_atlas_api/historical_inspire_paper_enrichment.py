"""Staging-only exact-arXiv-ID INSPIRE paper-time affiliation enrichment.

Targets are existing matched arXiv-only paper components with missing
paper-time affiliation mass.  Exact INSPIRE searches may add provider-native
paper-time affiliation evidence to those existing components, but this module
never widens the canonical paper corpus, replaces existing affiliation
evidence, resolves researchers by name, writes the database, or creates metric
observations.  No-hit, multiple-hit, and author-list conflicts remain explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
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
from .historical_replay import _normalized_author
from .historical_ror import (
    EXPECTED_REPLAY_BUNDLE_VERSION,
    EXPECTED_SCOPE,
    HistoricalRorSafetyError,
    _canonical_json,
    _checksum,
    _content_addressed_document,
    _fraction_from_payload,
    _fraction_payload,
    _is_within,
    _validate_external_path,
    _verified_jsonl_artifact,
    _write_content_addressed,
    _write_jsonl_artifact,
)

INSPIRE_PAPER_TARGET_VERSION = "hep-th-v1-inspire-paper-affiliation-targets-v1"
INSPIRE_PAPER_STATE_VERSION = "hep-th-v1-inspire-paper-affiliation-state-v1"
INSPIRE_PAPER_ACQUISITION_VERSION = "hep-th-v1-inspire-paper-affiliation-acquisition-v1"
INSPIRE_PAPER_ENRICHMENT_VERSION = (
    "hep-th-v1-inspire-paper-time-affiliation-enrichment-v1"
)
OFFICIAL_INSPIRE_BASE_URL = "https://inspirehep.net/api"
STATE_CHECKPOINT_INTERVAL = 25


def _validated_replay(path: Path) -> tuple[Path, dict[str, Any]]:
    replay_path = _validate_external_path(path)
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
    return replay_path, replay


def _missing_share_details(
    shares: Sequence[Mapping[str, Any]],
) -> tuple[Fraction, list[dict[str, Any]]]:
    mass = Fraction(0)
    details: list[dict[str, Any]] = []
    shares_by_position = _validated_shares_by_position(shares)
    for position, position_shares in sorted(shares_by_position.items()):
        missing_shares = [
            share for share in position_shares if not share["affiliation_assertion_ids"]
        ]
        if not missing_shares:
            continue
        if len(missing_shares) != 1 or len(position_shares) != 1:
            raise HistoricalRorSafetyError(
                "one author position mixes or duplicates missing affiliation shares"
            )
        share = missing_shares[0]
        weight = _fraction_from_payload(share.get("attribution_weight"))
        mass += weight
        details.append(
            {
                "paper_time_affiliation_share_id": share.get(
                    "paper_time_affiliation_share_id"
                ),
                "author_position": position,
                "attribution_weight": share.get("attribution_weight"),
            }
        )
    return mass, details


def _validated_shares_by_position(
    shares: Sequence[Mapping[str, Any]],
) -> dict[int, list[Mapping[str, Any]]]:
    """Validate share identity while allowing multi-affiliation author slots."""

    result: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    seen_share_ids: set[str] = set()
    for share in shares:
        assertion_ids = share.get("affiliation_assertion_ids")
        position = share.get("author_position")
        share_id = share.get("paper_time_affiliation_share_id")
        if (
            not isinstance(assertion_ids, list)
            or any(not isinstance(item, str) for item in assertion_ids)
            or not isinstance(position, int)
            or isinstance(position, bool)
            or position < 1
            or not isinstance(share_id, str)
            or not share_id
            or share_id in seen_share_ids
        ):
            raise HistoricalRorSafetyError("affiliation share is malformed")
        seen_share_ids.add(share_id)
        result[position].append(share)
    return result


def _normalized_affiliation_text(value: str) -> str:
    """Normalize provider text for exact corroboration, never institution matching."""

    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _baseline_affiliation_texts(
    shares: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    values: set[str] = set()
    for share in shares:
        raw_affiliations = share.get("raw_affiliations", [])
        if not isinstance(raw_affiliations, list):
            raise HistoricalRorSafetyError(
                "baseline arXiv affiliation evidence is malformed"
            )
        for raw_value in raw_affiliations:
            if raw_value is None:
                continue
            if isinstance(raw_value, Mapping):
                text_value = raw_value.get("value") or raw_value.get("name")
            else:
                text_value = raw_value
            if text_value is None:
                continue
            if not isinstance(text_value, str):
                raise HistoricalRorSafetyError(
                    "baseline arXiv affiliation text is malformed"
                )
            normalized = _normalized_affiliation_text(text_value)
            if normalized:
                values.add(normalized)
    return tuple(sorted(values))


def _inspire_affiliation_texts(evidence: Mapping[str, Any]) -> tuple[str, ...]:
    selection = evidence.get("selection")
    key = "affiliations" if selection == "affiliations" else "rawAffiliations"
    selected = evidence.get(key)
    if not isinstance(selected, list) or not selected:
        raise HistoricalRorSafetyError(
            "selected INSPIRE affiliation evidence is malformed"
        )
    values: set[str] = set()
    for item in selected:
        if not isinstance(item, Mapping):
            raise HistoricalRorSafetyError("INSPIRE affiliation evidence is malformed")
        raw_value = item.get("value") or item.get("name")
        if raw_value is None:
            continue
        if not isinstance(raw_value, str):
            raise HistoricalRorSafetyError("INSPIRE affiliation text is malformed")
        normalized = _normalized_affiliation_text(raw_value)
        if normalized:
            values.add(normalized)
    return tuple(sorted(values))


def build_inspire_paper_target_manifest(replay_manifest_path: Path) -> dict[str, Any]:
    """Derive deterministic exact arXiv targets from the immutable replay."""

    replay_path, replay = _validated_replay(replay_manifest_path)
    components = _verified_jsonl_artifact(replay_path, replay, role="paper-components")
    shares = _verified_jsonl_artifact(
        replay_path, replay, role="paper-time-affiliation-shares"
    )
    shares_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_share_ids: set[str] = set()
    for share in shares:
        candidate_id = share.get("candidate_id")
        share_id = share.get("paper_time_affiliation_share_id")
        if (
            not isinstance(candidate_id, str)
            or not isinstance(share_id, str)
            or share_id in seen_share_ids
        ):
            raise HistoricalRorSafetyError("replay affiliation share identity failed")
        seen_share_ids.add(share_id)
        shares_by_candidate[candidate_id].append(share)

    targets: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    seen_arxiv_ids: set[str] = set()
    for component in components:
        candidate_id = component.get("candidate_id")
        occurrences = component.get("occurrences")
        if (
            not isinstance(candidate_id, str)
            or candidate_id in seen_candidates
            or not isinstance(occurrences, list)
        ):
            raise HistoricalRorSafetyError("paper component identity is malformed")
        seen_candidates.add(candidate_id)
        if component.get("status") != "matched" or len(occurrences) != 1:
            continue
        occurrence = occurrences[0]
        if not isinstance(occurrence, Mapping) or occurrence.get("provider") != "arxiv":
            continue
        normalized = normalize_external_id("arxiv", occurrence.get("source_record_id"))
        authors = occurrence.get("authors")
        if (
            normalized is None
            or normalized[1] != occurrence.get("source_record_id")
            or not isinstance(authors, list)
            or not authors
            or any(
                not isinstance(author, str) or not author.strip() for author in authors
            )
        ):
            raise HistoricalRorSafetyError("arXiv-only occurrence is malformed")
        candidate_shares = shares_by_candidate.get(candidate_id, [])
        if any(
            share.get("paper_identity_status") != "matched"
            or share.get("source_occurrence_id") != occurrence.get("occurrence_id")
            for share in candidate_shares
        ):
            raise HistoricalRorSafetyError(
                "arXiv-only affiliation share lineage is inconsistent"
            )
        position_shares = _validated_shares_by_position(candidate_shares)
        if set(position_shares) != set(range(1, len(authors) + 1)):
            raise HistoricalRorSafetyError(
                "arXiv-only affiliation shares do not cover the author list"
            )
        missing_mass, missing_shares = _missing_share_details(candidate_shares)
        if missing_mass == 0:
            continue
        if any(int(item["author_position"]) > len(authors) for item in missing_shares):
            raise HistoricalRorSafetyError(
                "affiliation share author position exceeds component author list"
            )
        arxiv_id = normalized[1]
        if arxiv_id in seen_arxiv_ids:
            raise HistoricalRorSafetyError(
                "one exact arXiv identifier belongs to multiple replay components"
            )
        seen_arxiv_ids.add(arxiv_id)
        targets.append(
            {
                "arxiv_id": arxiv_id,
                "candidate_id": candidate_id,
                "source_occurrence_id": occurrence.get("occurrence_id"),
                "authors": list(authors),
                "missing_attribution_mass": _fraction_payload(missing_mass),
                "missing_shares": missing_shares,
            }
        )
    targets.sort(
        key=lambda item: (
            -_fraction_from_payload(item["missing_attribution_mass"]),
            str(item["arxiv_id"]),
        )
    )
    target_mass = sum(
        (_fraction_from_payload(item["missing_attribution_mass"]) for item in targets),
        start=Fraction(0),
    )
    return {
        "manifest_version": INSPIRE_PAPER_TARGET_VERSION,
        "acquisition_scope": EXPECTED_SCOPE,
        "replay_bundle_manifest_checksum": replay["bundle_manifest_checksum"],
        "source_manifest_checksum": replay["source_manifest_checksum"],
        "target_provider": "INSPIRE literature",
        "target_method": "exact-arxiv-id-for-existing-arxiv-only-replay-components",
        "target_priority": "descending-missing-attribution-mass-then-arxiv-id",
        "canonical_corpus_widening": False,
        "name_resolution": False,
        "database_access": False,
        "target_count": len(targets),
        "target_missing_attribution_mass": _fraction_payload(target_mass),
        "targets": targets,
    }


def write_inspire_paper_target_manifest(
    replay_manifest_path: Path, output: Path
) -> tuple[Path, dict[str, Any]]:
    output_root = _validate_external_path(output)
    return _write_content_addressed(
        output_root / "paper-target-manifests",
        build_inspire_paper_target_manifest(replay_manifest_path),
        checksum_field="target_manifest_checksum",
    )


def _record_relative_path(arxiv_id: str, checksum: str) -> Path:
    token = hashlib.sha256(arxiv_id.encode()).hexdigest()[:24]
    return Path("paper-records") / token / f"{checksum}.json"


def _verify_record(output: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    arxiv_id = value.get("arxiv_id")
    checksum = value.get("checksum")
    path_value = value.get("path")
    if not all(isinstance(item, str) for item in (arxiv_id, checksum, path_value)):
        raise HistoricalRorSafetyError("INSPIRE paper record metadata is malformed")
    assert isinstance(arxiv_id, str)
    assert isinstance(checksum, str)
    assert isinstance(path_value, str)
    if Path(path_value) != _record_relative_path(arxiv_id, checksum):
        raise HistoricalRorSafetyError("INSPIRE paper record path is noncanonical")
    path = (output / path_value).resolve()
    if not _is_within(path, output.resolve()):
        raise HistoricalRorSafetyError("INSPIRE paper record leaves output")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise HistoricalRorSafetyError("INSPIRE paper record is missing") from error
    if hashlib.sha256(payload).hexdigest() != checksum:
        raise HistoricalRorSafetyError("INSPIRE paper record checksum failed")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as error:
        raise HistoricalRorSafetyError("INSPIRE paper record is malformed") from error
    if (
        not isinstance(document, dict)
        or document.get("provider") != "inspire"
        or document.get("source_record_kind") != "exact-arxiv-literature-query"
        or document.get("source_record_id") != arxiv_id
    ):
        raise HistoricalRorSafetyError("INSPIRE paper record identity failed")
    return document


def _hit_arxiv_ids(hit: Mapping[str, Any]) -> tuple[str, ...]:
    metadata = hit.get("metadata")
    if not isinstance(metadata, Mapping):
        return ()
    values = metadata.get("arxiv_eprints", [])
    if not isinstance(values, list):
        raise HistoricalRorSafetyError("INSPIRE arXiv identifiers are malformed")
    result: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping):
            raise HistoricalRorSafetyError("INSPIRE arXiv identifier is malformed")
        normalized = normalize_external_id("arxiv", value.get("value"))
        if normalized is not None:
            result.add(normalized[1])
    return tuple(sorted(result))


def _query_result(
    payload: Mapping[str, Any], arxiv_id: str
) -> tuple[str, list[Mapping[str, Any]], int]:
    hits_value = payload.get("hits")
    if not isinstance(hits_value, Mapping):
        raise HistoricalRorSafetyError("INSPIRE exact query lacks hits")
    hits = hits_value.get("hits")
    total_value = hits_value.get("total")
    if isinstance(total_value, Mapping):
        total_value = total_value.get("value")
    if (
        not isinstance(hits, list)
        or any(not isinstance(hit, Mapping) for hit in hits)
        or not isinstance(total_value, int)
        or isinstance(total_value, bool)
        or total_value < len(hits)
        or len(hits) > 2
        or (total_value == 0 and hits)
        or (total_value > 0 and not hits)
    ):
        raise HistoricalRorSafetyError("INSPIRE exact query result is malformed")
    typed_hits = [hit for hit in hits if isinstance(hit, Mapping)]
    exact_flags = [arxiv_id in _hit_arxiv_ids(hit) for hit in typed_hits]
    if total_value == 0:
        status = "no-hit"
    elif total_value != 1 or len(typed_hits) != 1:
        status = "conflict-multiple-hits"
    elif exact_flags[0]:
        status = "exact-single-hit"
    else:
        status = "conflict-nonexact-hit"
    return status, typed_hits, total_value


def _store_record(
    output: Path,
    *,
    arxiv_id: str,
    payload: Mapping[str, Any],
    target: Mapping[str, Any],
    captured_at: datetime,
) -> dict[str, Any]:
    query_status, _hits, total = _query_result(payload, arxiv_id)
    document = {
        "provider": "inspire",
        "source_version": "INSPIRE REST API literature exact-arXiv query",
        "source_record_kind": "exact-arxiv-literature-query",
        "source_record_id": arxiv_id,
        "evidence_type": "provider-content-snapshot",
        "captured_at": captured_at.astimezone(UTC).isoformat(),
        "query": {"q": f"arxiv:{arxiv_id}", "size": 2},
        "query_status": query_status,
        "query_total": total,
        "target_manifest_checksum": target["target_manifest_checksum"],
        "source_manifest_checksum": target["source_manifest_checksum"],
        "raw": dict(payload),
    }
    payload_bytes = _canonical_json(document) + b"\n"
    checksum = hashlib.sha256(payload_bytes).hexdigest()
    relative = _record_relative_path(arxiv_id, checksum)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(payload_bytes)
    except FileExistsError as error:
        if destination.read_bytes() != payload_bytes:
            raise HistoricalRorSafetyError(
                "content-addressed INSPIRE paper record differs"
            ) from error
    return {
        "arxiv_id": arxiv_id,
        "path": relative.as_posix(),
        "checksum": checksum,
        "captured_at": document["captured_at"],
        "query_status": query_status,
        "query_total": total,
    }


def _load_resume_state(
    output: Path,
    *,
    target_checksum: str,
    target_ids: Sequence[str],
    base_url: str,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for path in sorted((output / "paper-states").glob("*.json")):
        state = _content_addressed_document(path, checksum_field="state_checksum")
        if state.get("target_manifest_checksum") != target_checksum:
            continue
        records = state.get("records")
        next_index = state.get("next_index")
        if (
            state.get("state_version") != INSPIRE_PAPER_STATE_VERSION
            or state.get("inspire_base_url") != base_url
            or not isinstance(records, list)
            or not isinstance(next_index, int)
            or isinstance(next_index, bool)
            or next_index != len(records)
            or next_index > len(target_ids)
            or any(not isinstance(item, Mapping) for item in records)
            or [item.get("arxiv_id") for item in records]
            != list(target_ids[:next_index])
        ):
            raise HistoricalRorSafetyError("INSPIRE paper resume state is malformed")
        candidates.append(state)
    if not candidates:
        return None
    maximum = max(int(item["next_index"]) for item in candidates)
    finalists = [item for item in candidates if item["next_index"] == maximum]
    if len({_checksum(item["records"]) for item in finalists}) != 1:
        raise HistoricalRorSafetyError(
            "INSPIRE paper resume states conflict at one checkpoint"
        )
    selected = sorted(finalists, key=lambda item: str(item["state_checksum"]))[-1]
    for record in selected["records"]:
        _verify_record(output, record)
    return selected


def _write_state(
    output: Path,
    *,
    target: Mapping[str, Any],
    base_url: str,
    records: Sequence[Mapping[str, Any]],
    status: str,
    error: str | None,
) -> None:
    _write_content_addressed(
        output / "paper-states",
        {
            "state_version": INSPIRE_PAPER_STATE_VERSION,
            "target_manifest_checksum": target["target_manifest_checksum"],
            "source_manifest_checksum": target["source_manifest_checksum"],
            "inspire_base_url": base_url,
            "next_index": len(records),
            "records": list(records),
            "status": status,
            "error": error,
        },
        checksum_field="state_checksum",
    )


def acquire_inspire_paper_records(
    target_manifest_path: Path,
    output: Path,
    transport: SourceTransport,
    *,
    base_url: str = OFFICIAL_INSPIRE_BASE_URL,
    max_new_records: int | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[Path, dict[str, Any]]:
    """Acquire a deterministic target prefix with exact arXiv-ID queries."""

    output_root = _validate_external_path(output)
    target = _content_addressed_document(
        target_manifest_path.resolve(), checksum_field="target_manifest_checksum"
    )
    targets = target.get("targets")
    if (
        target.get("manifest_version") != INSPIRE_PAPER_TARGET_VERSION
        or target.get("acquisition_scope") != EXPECTED_SCOPE
        or target.get("canonical_corpus_widening") is not False
        or target.get("name_resolution") is not False
        or not isinstance(targets, list)
        or target.get("target_count") != len(targets)
    ):
        raise HistoricalRorSafetyError("INSPIRE paper target manifest is not approved")
    if max_new_records is not None and max_new_records < 1:
        raise ValueError("max_new_records must be positive")
    target_ids: list[str] = []
    for item in targets:
        arxiv_id = item.get("arxiv_id") if isinstance(item, Mapping) else None
        if not isinstance(arxiv_id, str) or normalize_external_id(
            "arxiv", arxiv_id
        ) != ("arxiv", arxiv_id):
            raise HistoricalRorSafetyError("INSPIRE paper target is malformed")
        target_ids.append(arxiv_id)
    if len(set(target_ids)) != len(target_ids):
        raise HistoricalRorSafetyError("INSPIRE paper targets are duplicated")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HistoricalRorSafetyError("INSPIRE paper endpoint is malformed")

    previous = _load_resume_state(
        output_root,
        target_checksum=str(target["target_manifest_checksum"]),
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
    for arxiv_id in target_ids[len(records) : stop_index]:
        try:
            payload = transport.get_json(
                f"{base_url.rstrip('/')}/literature",
                params={"q": f"arxiv:{arxiv_id}", "size": 2},
            )
            records.append(
                _store_record(
                    output_root,
                    arxiv_id=arxiv_id,
                    payload=payload,
                    target=target,
                    captured_at=now(),
                )
            )
            if len(records) % STATE_CHECKPOINT_INTERVAL == 0:
                _write_state(
                    output_root,
                    target=target,
                    base_url=base_url,
                    records=records,
                    status="in-progress",
                    error=None,
                )
        except Exception as error:  # noqa: BLE001 - preserve safe resume point
            terminal_status = "failed"
            error_message = f"{type(error).__name__}: {error}"[:1000]
            _write_state(
                output_root,
                target=target,
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
        target=target,
        base_url=base_url,
        records=records,
        status="complete" if complete else terminal_status,
        error=error_message,
    )
    return _write_content_addressed(
        output_root / "paper-acquisition-manifests",
        {
            "manifest_version": INSPIRE_PAPER_ACQUISITION_VERSION,
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
            "exact_arxiv_query": True,
            "canonical_corpus_widening": False,
            "database_access": False,
            "metric_observations_created": 0,
        },
        checksum_field="acquisition_manifest_checksum",
    )


def _author_affiliations(author: Mapping[str, Any]) -> dict[str, Any] | None:
    affiliations = author.get("affiliations", [])
    raw_affiliations = author.get("raw_affiliations", [])
    if not isinstance(affiliations, list) or not isinstance(raw_affiliations, list):
        raise HistoricalRorSafetyError(
            "INSPIRE author affiliation evidence is malformed"
        )
    if any(not isinstance(item, Mapping) for item in affiliations + raw_affiliations):
        raise HistoricalRorSafetyError("INSPIRE author affiliation row is malformed")
    selected = affiliations or raw_affiliations
    if not selected:
        return None
    return {
        "affiliations": [dict(item) for item in affiliations],
        "rawAffiliations": [dict(item) for item in raw_affiliations],
        "selection": "affiliations" if affiliations else "raw-affiliations-fallback",
    }


def materialize_paper_time_affiliation_enrichment(
    replay_manifest_path: Path,
    acquisition_manifest_path: Path,
    output: Path,
) -> tuple[Path, dict[str, Any]]:
    """Project only new paper-native affiliation evidence onto existing shares."""

    replay_path, replay = _validated_replay(replay_manifest_path)
    acquisition_path = _validate_external_path(acquisition_manifest_path)
    acquisition = _content_addressed_document(
        acquisition_path, checksum_field="acquisition_manifest_checksum"
    )
    records = acquisition.get("records")
    if (
        acquisition.get("manifest_version") != INSPIRE_PAPER_ACQUISITION_VERSION
        or acquisition.get("terminal_status") == "failed"
        or acquisition.get("exact_arxiv_query") is not True
        or acquisition.get("canonical_corpus_widening") is not False
        or acquisition.get("database_access") is not False
        or acquisition.get("metric_observations_created") != 0
        or acquisition.get("replay_bundle_manifest_checksum")
        != replay.get("bundle_manifest_checksum")
        or acquisition.get("source_manifest_checksum")
        != replay.get("source_manifest_checksum")
        or not isinstance(records, list)
        or not records
        or acquisition.get("records_completed") != len(records)
    ):
        raise HistoricalRorSafetyError("paper enrichment acquisition is not approved")
    acquisition_root = acquisition_path.parent.parent.resolve()
    target_checksum = acquisition.get("target_manifest_checksum")
    if not isinstance(target_checksum, str):
        raise HistoricalRorSafetyError("paper enrichment lacks target lineage")
    target_path = (
        acquisition_root / "paper-target-manifests" / f"{target_checksum}.json"
    )
    target = _content_addressed_document(
        target_path, checksum_field="target_manifest_checksum"
    )
    targets = target.get("targets")
    if (
        target.get("manifest_version") != INSPIRE_PAPER_TARGET_VERSION
        or target.get("replay_bundle_manifest_checksum")
        != replay.get("bundle_manifest_checksum")
        or target.get("source_manifest_checksum")
        != replay.get("source_manifest_checksum")
        or target.get("canonical_corpus_widening") is not False
        or not isinstance(targets, list)
        or target.get("target_count") != len(targets)
    ):
        raise HistoricalRorSafetyError("paper enrichment target lineage failed")
    expected_target = build_inspire_paper_target_manifest(replay_path)
    unsigned_target = dict(target)
    unsigned_target.pop("target_manifest_checksum", None)
    if unsigned_target != expected_target:
        raise HistoricalRorSafetyError(
            "paper enrichment targets differ from the verified replay"
        )
    target_by_id: dict[str, Mapping[str, Any]] = {}
    target_ids: list[str] = []
    for target_row in targets:
        arxiv_id = (
            target_row.get("arxiv_id") if isinstance(target_row, Mapping) else None
        )
        if not isinstance(arxiv_id, str) or arxiv_id in target_by_id:
            raise HistoricalRorSafetyError("paper enrichment target identity failed")
        target_by_id[arxiv_id] = target_row
        target_ids.append(arxiv_id)
    observed_ids = [
        item.get("arxiv_id") for item in records if isinstance(item, Mapping)
    ]
    if len(observed_ids) != len(records) or observed_ids != target_ids[: len(records)]:
        raise HistoricalRorSafetyError(
            "paper enrichment records are not the exact target prefix"
        )

    components = _verified_jsonl_artifact(replay_path, replay, role="paper-components")
    shares = _verified_jsonl_artifact(
        replay_path, replay, role="paper-time-affiliation-shares"
    )
    ledgers = _verified_jsonl_artifact(
        replay_path, replay, role="fractional-attribution-ledgers"
    )
    component_by_candidate: dict[str, dict[str, Any]] = {}
    for component in components:
        candidate_id = component.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in component_by_candidate:
            raise HistoricalRorSafetyError("paper component identity is duplicated")
        component_by_candidate[candidate_id] = component
    shares_by_candidate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    baseline_evidence_mass = Fraction(0)
    baseline_missing_mass = Fraction(0)
    share_mass_by_candidate: dict[str, Fraction] = defaultdict(Fraction)
    seen_share_ids: set[str] = set()
    for share in shares:
        candidate_id = share.get("candidate_id")
        share_id = share.get("paper_time_affiliation_share_id")
        assertion_ids = share.get("affiliation_assertion_ids")
        if (
            not isinstance(candidate_id, str)
            or not isinstance(share_id, str)
            or share_id in seen_share_ids
            or not isinstance(assertion_ids, list)
            or any(not isinstance(item, str) for item in assertion_ids)
        ):
            raise HistoricalRorSafetyError("replay affiliation share is malformed")
        seen_share_ids.add(share_id)
        weight = _fraction_from_payload(share.get("attribution_weight"))
        shares_by_candidate[candidate_id].append(share)
        share_mass_by_candidate[candidate_id] += weight
        if assertion_ids:
            baseline_evidence_mass += weight
        else:
            baseline_missing_mass += weight

    expected_mass = Fraction(0)
    ledger_evaluated_mass = Fraction(0)
    unmaterialized_mass = Fraction(0)
    seen_ledger_candidates: set[str] = set()
    for ledger in ledgers:
        candidate_id = ledger.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in seen_ledger_candidates:
            raise HistoricalRorSafetyError("attribution ledger identity is malformed")
        seen_ledger_candidates.add(candidate_id)
        evaluated = _fraction_from_payload(ledger.get("total_weight"))
        unmaterialized = _fraction_from_payload(ledger.get("unmaterialized_paper_mass"))
        if evaluated + unmaterialized != 1:
            raise HistoricalRorSafetyError(
                "attribution ledger does not conserve a paper"
            )
        if share_mass_by_candidate.get(candidate_id, Fraction(0)) != evaluated:
            raise HistoricalRorSafetyError(
                "affiliation shares differ from their attribution ledger"
            )
        expected_mass += 1
        ledger_evaluated_mass += evaluated
        unmaterialized_mass += unmaterialized
    if set(share_mass_by_candidate) - seen_ledger_candidates:
        raise HistoricalRorSafetyError("affiliation share has no attribution ledger")
    if baseline_evidence_mass + baseline_missing_mass != ledger_evaluated_mass:
        raise HistoricalRorSafetyError("baseline affiliation mass is not conserved")

    outcomes: list[dict[str, Any]] = []
    recovered_mass = Fraction(0)
    recovered_share_ids: set[str] = set()
    status_counts: dict[str, int] = defaultdict(int)
    cross_provider_status_counts: dict[str, int] = defaultdict(int)
    precedence_disposition_counts: dict[str, int] = defaultdict(int)
    corroborated_mass = Fraction(0)
    superseded_mass = Fraction(0)
    unresolved_conflict_mass = Fraction(0)
    for metadata in records:
        if not isinstance(metadata, Mapping):
            raise HistoricalRorSafetyError("paper record metadata is malformed")
        document = _verify_record(acquisition_root, metadata)
        arxiv_id = str(document["source_record_id"])
        if document.get("target_manifest_checksum") != target_checksum or document.get(
            "source_manifest_checksum"
        ) != replay.get("source_manifest_checksum"):
            raise HistoricalRorSafetyError("paper record lineage failed")
        target_row = target_by_id[arxiv_id]
        candidate_id = target_row.get("candidate_id")
        target_component = component_by_candidate.get(str(candidate_id))
        if target_component is None:
            raise HistoricalRorSafetyError("paper target left the replay corpus")
        raw = document.get("raw")
        if not isinstance(raw, Mapping):
            raise HistoricalRorSafetyError("paper query snapshot is malformed")
        query_status, hits, total = _query_result(raw, arxiv_id)
        recovered: list[dict[str, Any]] = []
        positional_evidence: list[dict[str, Any]] = []
        outcome_status = query_status
        inspire_record_id: str | None = None
        if query_status == "exact-single-hit":
            hit = hits[0]
            hit_id = hit.get("id")
            if hit_id is None or not str(hit_id).isdigit():
                raise HistoricalRorSafetyError(
                    "exact INSPIRE paper hit lacks a canonical record identifier"
                )
            inspire_record_id = str(hit_id)
            hit_metadata = hit.get("metadata")
            inspire_authors = (
                hit_metadata.get("authors")
                if isinstance(hit_metadata, Mapping)
                else None
            )
            source_authors = target_row.get("authors")
            if (
                not isinstance(inspire_authors, list)
                or any(not isinstance(author, Mapping) for author in inspire_authors)
                or not isinstance(source_authors, list)
                or any(not isinstance(author, str) for author in source_authors)
            ):
                raise HistoricalRorSafetyError("paper author evidence is malformed")
            inspire_names = [author.get("full_name") for author in inspire_authors]
            if len(inspire_names) != len(source_authors) or any(
                not isinstance(name, str) for name in inspire_names
            ):
                outcome_status = "conflict-author-count"
            elif any(
                _normalized_author(source_name) != _normalized_author(inspire_name)
                for source_name, inspire_name in zip(
                    source_authors, inspire_names, strict=True
                )
                if isinstance(inspire_name, str)
            ):
                outcome_status = "conflict-author-order-or-name"
            else:
                candidate_shares = shares_by_candidate.get(str(candidate_id), [])
                shares_by_position = _validated_shares_by_position(candidate_shares)
                if set(shares_by_position) != set(range(1, len(inspire_authors) + 1)):
                    raise HistoricalRorSafetyError(
                        "affiliation shares do not cover the matched author list"
                    )
                slot_has_conflict = False
                slot_has_corroboration = False
                for position, position_shares in sorted(shares_by_position.items()):
                    author = inspire_authors[position - 1]
                    assert isinstance(author, Mapping)
                    evidence = _author_affiliations(author)
                    baseline_rows: list[dict[str, Any]] = []
                    baseline_has_evidence = False
                    slot_mass = Fraction(0)
                    missing_position_shares: list[Mapping[str, Any]] = []
                    for position_share in position_shares:
                        assertion_ids = position_share["affiliation_assertion_ids"]
                        assert isinstance(assertion_ids, list)
                        raw_affiliations = position_share.get("raw_affiliations", [])
                        resolution_evidence = position_share.get(
                            "resolution_evidence", []
                        )
                        if not isinstance(raw_affiliations, list) or not isinstance(
                            resolution_evidence, list
                        ):
                            raise HistoricalRorSafetyError(
                                "baseline affiliation evidence is malformed"
                            )
                        weight = _fraction_from_payload(
                            position_share.get("attribution_weight")
                        )
                        slot_mass += weight
                        baseline_has_evidence = baseline_has_evidence or bool(
                            assertion_ids
                        )
                        if not assertion_ids:
                            missing_position_shares.append(position_share)
                        baseline_rows.append(
                            {
                                "paperTimeAffiliationShareId": position_share[
                                    "paper_time_affiliation_share_id"
                                ],
                                "affiliationAssertionIds": list(assertion_ids),
                                "rawAffiliations": list(raw_affiliations),
                                "resolutionEvidence": list(resolution_evidence),
                                "attributionWeight": position_share[
                                    "attribution_weight"
                                ],
                            }
                        )
                    if missing_position_shares and (
                        len(missing_position_shares) != 1 or len(position_shares) != 1
                    ):
                        raise HistoricalRorSafetyError(
                            "one author position mixes or duplicates missing "
                            "affiliation shares"
                        )

                    if evidence is None:
                        if baseline_has_evidence:
                            comparison_status = "inspire-missing-arxiv-only"
                            precedence_disposition = "arxiv-retained-as-next-precedence"
                            evidence_selection_status = "selected-arxiv-fallback"
                        else:
                            comparison_status = "both-sources-missing"
                            precedence_disposition = (
                                "unresolved-no-affiliation-evidence"
                            )
                            evidence_selection_status = "unresolved-missing"
                    elif not baseline_has_evidence:
                        comparison_status = "formerly-missing-recovered"
                        precedence_disposition = "inspire-fills-formerly-missing"
                        evidence_selection_status = "selected-inspire"
                        for missing_share in missing_position_shares:
                            share_id = str(
                                missing_share["paper_time_affiliation_share_id"]
                            )
                            if share_id in recovered_share_ids:
                                raise HistoricalRorSafetyError(
                                    "one affiliation share was recovered more than once"
                                )
                            recovered_share_ids.add(share_id)
                            weight = _fraction_from_payload(
                                missing_share.get("attribution_weight")
                            )
                            recovered_mass += weight
                            recovered.append(
                                {
                                    "paperTimeAffiliationShareId": share_id,
                                    "authorPosition": position,
                                    "attributionWeight": missing_share[
                                        "attribution_weight"
                                    ],
                                    "paperNativeAffiliationEvidence": evidence,
                                }
                            )
                    else:
                        baseline_texts = _baseline_affiliation_texts(position_shares)
                        inspire_texts = _inspire_affiliation_texts(evidence)
                        if (
                            baseline_texts
                            and inspire_texts
                            and baseline_texts == inspire_texts
                        ):
                            comparison_status = "corroborated"
                            precedence_disposition = (
                                "inspire-supersedes-corroborated-arxiv"
                            )
                            evidence_selection_status = "selected-inspire"
                            slot_has_corroboration = True
                            corroborated_mass += slot_mass
                            superseded_mass += slot_mass
                        else:
                            comparison_status = "conflict"
                            precedence_disposition = "unresolved-source-conflict"
                            evidence_selection_status = "unresolved-conflict"
                            slot_has_conflict = True
                            unresolved_conflict_mass += slot_mass

                    cross_provider_status_counts[comparison_status] += 1
                    precedence_disposition_counts[precedence_disposition] += 1
                    positional_evidence.append(
                        {
                            "authorPosition": position,
                            "baselineArxivShares": baseline_rows,
                            "inspirePaperNativeAffiliationEvidence": evidence,
                            "crossProviderClassification": comparison_status,
                            "precedenceDisposition": precedence_disposition,
                            "evidenceSelectionStatus": evidence_selection_status,
                            "eligibleForCanonicalResolution": comparison_status
                            not in {"both-sources-missing", "conflict"},
                            "authorSlotAttributionMass": _fraction_payload(slot_mass),
                            "comparisonMethod": (
                                "exact-normalized-provider-text-v1"
                                if evidence is not None and baseline_has_evidence
                                else "source-presence-v1"
                            ),
                        }
                    )
                if slot_has_conflict:
                    outcome_status = "unresolved-affiliation-conflict"
                elif recovered:
                    outcome_status = "recovered"
                elif slot_has_corroboration:
                    outcome_status = "corroborated-supersession"
                else:
                    outcome_status = "no-new-affiliation"
        status_counts[outcome_status] += 1
        outcomes.append(
            {
                "arxivId": arxiv_id,
                "candidateId": candidate_id,
                "queryStatus": query_status,
                "outcomeStatus": outcome_status,
                "queryTotal": total,
                "inspireRecordId": inspire_record_id,
                "recoveredShares": recovered,
                "positionalAffiliationEvidence": positional_evidence,
                "recoveredAttributionMass": _fraction_payload(
                    sum(
                        (
                            _fraction_from_payload(item["attributionWeight"])
                            for item in recovered
                        ),
                        start=Fraction(0),
                    )
                ),
                "sourceRecordPath": metadata["path"],
                "sourceRecordChecksum": metadata["checksum"],
                "capturedAt": metadata["captured_at"],
                "targetManifestChecksum": target_checksum,
                "acquisitionManifestChecksum": acquisition[
                    "acquisition_manifest_checksum"
                ],
                "enrichmentVersion": INSPIRE_PAPER_ENRICHMENT_VERSION,
                "canonicalCorpusWidening": False,
                "existingAffiliationEvidenceReplaced": False,
                "eligibleForPublicMetrics": False,
            }
        )
    if recovered_mass > baseline_missing_mass:
        raise HistoricalRorSafetyError(
            "recovered affiliation mass exceeds missing mass"
        )
    if unresolved_conflict_mass > baseline_evidence_mass:
        raise HistoricalRorSafetyError(
            "cross-provider conflict mass exceeds baseline evidence mass"
        )
    # Evidence coverage measures whether a paper-time assertion exists, not
    # whether it can be canonically resolved. A source conflict is therefore a
    # subset of evidence mass but is withheld in the separate resolution
    # partition below.
    combined_evidence_mass = baseline_evidence_mass + recovered_mass
    combined_missing_mass = baseline_missing_mass - recovered_mass
    combined_nonconflicting_evidence_mass = (
        combined_evidence_mass - unresolved_conflict_mass
    )
    combined_unresolved_mass = combined_missing_mass + unresolved_conflict_mass
    if (
        combined_evidence_mass + combined_missing_mass + unmaterialized_mass
        != expected_mass
    ):
        raise HistoricalRorSafetyError(
            "enriched affiliation evidence mass is not conserved"
        )
    if (
        combined_nonconflicting_evidence_mass
        + combined_unresolved_mass
        + unmaterialized_mass
        != expected_mass
    ):
        raise HistoricalRorSafetyError(
            "enriched affiliation resolution partition is not conserved"
        )

    output_root = _validate_external_path(output)
    artifact = _write_jsonl_artifact(
        output_root,
        directory="paper-affiliation-enrichments",
        rows=outcomes,
    )
    return _write_content_addressed(
        output_root / "paper-enrichment-manifests",
        {
            "manifest_version": INSPIRE_PAPER_ENRICHMENT_VERSION,
            "replay_bundle_manifest_checksum": replay["bundle_manifest_checksum"],
            "source_manifest_checksum": replay["source_manifest_checksum"],
            "target_manifest_checksum": target_checksum,
            "acquisition_manifest_checksum": acquisition[
                "acquisition_manifest_checksum"
            ],
            "acquisition_complete": acquisition["acquisition_complete"],
            "target_count": target["target_count"],
            "records_examined": len(records),
            "outcome_status_counts": dict(sorted(status_counts.items())),
            "cross_provider_classification_counts": dict(
                sorted(cross_provider_status_counts.items())
            ),
            "precedence_disposition_counts": dict(
                sorted(precedence_disposition_counts.items())
            ),
            "recovered_share_count": len(recovered_share_ids),
            "positional_evidence_slot_count": sum(
                len(outcome["positionalAffiliationEvidence"]) for outcome in outcomes
            ),
            "expected_paper_mass": _fraction_payload(expected_mass),
            "unmaterialized_paper_mass": _fraction_payload(unmaterialized_mass),
            "baseline_affiliation_evidence_mass": _fraction_payload(
                baseline_evidence_mass
            ),
            "baseline_missing_affiliation_mass": _fraction_payload(
                baseline_missing_mass
            ),
            "recovered_affiliation_evidence_mass": _fraction_payload(recovered_mass),
            "corroborated_existing_affiliation_mass": _fraction_payload(
                corroborated_mass
            ),
            "higher_precedence_superseded_affiliation_mass": _fraction_payload(
                superseded_mass
            ),
            "unresolved_cross_provider_conflict_mass": _fraction_payload(
                unresolved_conflict_mass
            ),
            "combined_affiliation_evidence_mass": _fraction_payload(
                combined_evidence_mass
            ),
            "combined_nonconflicting_affiliation_evidence_mass": _fraction_payload(
                combined_nonconflicting_evidence_mass
            ),
            "combined_missing_affiliation_mass": _fraction_payload(
                combined_missing_mass
            ),
            "combined_unresolved_affiliation_mass": _fraction_payload(
                combined_unresolved_mass
            ),
            "baseline_affiliation_coverage": _fraction_payload(
                baseline_evidence_mass / expected_mass
            ),
            "combined_affiliation_coverage": _fraction_payload(
                combined_evidence_mass / expected_mass
            ),
            "mass_conservation_passed": True,
            "affiliation_evidence_mass_conservation_passed": True,
            "affiliation_resolution_partition_conservation_passed": True,
            "artifact": artifact,
            "targeting": "exact-arxiv-id-existing-corpus-only",
            "canonical_corpus_widening": False,
            "name_resolution": False,
            "immutable_baseline_modified": False,
            "database_access": False,
            "metric_observations_created": 0,
            "eligible_for_public_metrics": False,
        },
        checksum_field="enrichment_manifest_checksum",
    )


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-new-records", type=int)
    args = parser.parse_args(argv)

    target_path, target = write_inspire_paper_target_manifest(
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
            acquisition_path, acquisition = acquire_inspire_paper_records(
                target_path,
                args.output,
                transport,
                max_new_records=args.max_new_records,
            )
        result["acquisitionManifestPath"] = str(acquisition_path)
        result["acquisitionManifest"] = acquisition
        if (
            acquisition["records_completed"]
            and acquisition["terminal_status"] != "failed"
        ):
            enrichment_path, enrichment = materialize_paper_time_affiliation_enrichment(
                args.replay_manifest,
                acquisition_path,
                args.output,
            )
            result["enrichmentManifestPath"] = str(enrichment_path)
            result["enrichmentManifest"] = enrichment
        exit_code = 1 if acquisition["terminal_status"] == "failed" else 0
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
