import hashlib
import json
from fractions import Fraction
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

from physics_atlas_api.historical_ror import (
    EXPECTED_YEARS,
    HistoricalRorSafetyError,
    _checksum,
    acquire_target_records,
    build_target_manifest,
    materialize_canonical_institutions,
    resolve_replay_institution_anchors,
    write_target_manifest,
)


class ExactRorTransport:
    def __init__(
        self,
        *,
        fail_once_id: str | None = None,
        relationships_by_id: dict[str, list[dict[str, Any]]] | None = None,
        status_by_id: dict[str, str] | None = None,
    ):
        self.fail_once_id = fail_once_id
        self.relationships_by_id = relationships_by_id
        self.status_by_id = status_by_id or {}
        self.failed = False
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def close(self) -> None:
        pass

    def __enter__(self) -> Self:
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
        del headers
        self.calls.append((url, params))
        ror_id = url.rstrip("/").rsplit("/", 1)[-1]
        if self.fail_once_id == ror_id and not self.failed:
            self.failed = True
            raise RuntimeError("deterministic ROR failure")
        return {
            "id": f"https://ror.org/{ror_id}",
            "status": self.status_by_id.get(ror_id, "active"),
            "names": [{"value": f"Institution {ror_id}", "types": ["ror_display"]}],
            "locations": [
                {
                    "geonames_details": {
                        "country_code": "US",
                        "name": "Test City",
                        "lat": 1.0,
                        "lng": 2.0,
                    }
                }
            ],
            "links": [],
            "relationships": (
                self.relationships_by_id.get(ror_id, [])
                if self.relationships_by_id is not None
                else (
                    [
                        {
                            "type": "parent",
                            "id": "https://ror.org/03vek6s52",
                            "label": "Parent institution",
                        }
                    ]
                    if ror_id == "00hx57361"
                    else []
                )
            ),
            "admin": {"last_modified": {"date": "2026-08-31"}},
        }

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        raise AssertionError("exact ROR records use JSON only")


def _write_source_manifest(
    root: Path,
    *,
    ror_ids: tuple[str, ...] = ("03vek6s52", "00hx57361"),
) -> Path:
    partitions: list[dict[str, Any]] = []
    for year in EXPECTED_YEARS:
        authors = [
            {
                "full_name": f"Author {index}",
                "affiliations": [{"value": f"Institution {index}"}],
                "affiliations_identifiers": [
                    {"schema": "ROR", "value": f"https://ror.org/{ror_id}"}
                ],
            }
            for index, ror_id in enumerate(ror_ids)
        ]
        page = {
            "hits": {
                "hits": [
                    {
                        "id": str(year),
                        "metadata": {"authors": authors},
                    }
                ]
            }
        }
        payload = json.dumps(page, separators=(",", ":"), sort_keys=True).encode()
        page_checksum = hashlib.sha256(payload).hexdigest()
        relative = Path("pages") / "inspire" / str(year) / f"{page_checksum}.json"
        page_path = root / relative
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_bytes(payload)
        partition: dict[str, Any] = {
            "provider": "inspire",
            "year": year,
            "complete": True,
            "pages": [
                {
                    "path": relative.as_posix(),
                    "checksum": page_checksum,
                    "record_count": 1,
                }
            ],
        }
        partition["partition_checksum"] = _checksum(partition)
        partitions.append(partition)
    manifest: dict[str, Any] = {
        "manifest_version": "hep-th-v1-historical-raw-acquisition-manifest-v1",
        "mode": "acquire",
        "executed": True,
        "acquisition_complete": True,
        "acquisition_scope": "hep-th-v1",
        "partitions": partitions,
    }
    manifest["manifest_checksum"] = _checksum(manifest)
    path = root / "manifests" / f"{manifest['manifest_checksum']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def _write_replay_manifest(
    root: Path,
    *,
    source_manifest_checksum: str,
    anchors: list[dict[str, Any]],
    shares: list[dict[str, Any]],
    unmaterialized_paper_count: int = 0,
) -> Path:
    share_mass_by_candidate: dict[str, Fraction] = {}
    for share in shares:
        weight = share["attribution_weight"]
        share_mass_by_candidate[share["candidate_id"]] = share_mass_by_candidate.get(
            share["candidate_id"], Fraction(0)
        ) + Fraction(weight["numerator"], weight["denominator"])
    ledgers = [
        {
            "candidate_id": candidate_id,
            "total_weight": {
                "numerator": weight.numerator,
                "denominator": weight.denominator,
                "exact": f"{weight.numerator}/{weight.denominator}",
            },
            "unmaterialized_paper_mass": {
                "numerator": 0,
                "denominator": 1,
                "exact": "0/1",
            },
        }
        for candidate_id, weight in sorted(share_mass_by_candidate.items())
    ]
    ledgers.extend(
        {
            "candidate_id": f"unmaterialized-paper-{index}",
            "total_weight": {
                "numerator": 0,
                "denominator": 1,
                "exact": "0/1",
            },
            "unmaterialized_paper_mass": {
                "numerator": 1,
                "denominator": 1,
                "exact": "1/1",
            },
        }
        for index in range(unmaterialized_paper_count)
    )
    artifacts: list[dict[str, Any]] = []
    for role, directory, rows in (
        ("institution-authority-anchors", "relationships/institutions", anchors),
        ("paper-time-affiliation-shares", "relationships/affiliations", shares),
        (
            "fractional-attribution-ledgers",
            "relationships/attribution",
            ledgers,
        ),
    ):
        payload = b"".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
            for row in rows
        )
        checksum = hashlib.sha256(payload).hexdigest()
        relative = Path(directory) / f"{checksum}.jsonl"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        artifacts.append(
            {
                "role": role,
                "path": relative.as_posix(),
                "checksum": checksum,
                "byte_count": len(payload),
                "row_count": len(rows),
            }
        )
    manifest: dict[str, Any] = {
        "bundle_version": "hep-th-v1-historical-replay-bundle-v1",
        "replay_version": "hep-th-v1-historical-replay-materialization-v1",
        "source_manifest_checksum": source_manifest_checksum,
        "artifacts": artifacts,
        "network_access": False,
        "database_access": False,
        "canonical_institutions_materialized": 0,
        "metric_observations_created": 0,
    }
    manifest["bundle_manifest_checksum"] = _checksum(manifest)
    path = root / "manifests" / f"{manifest['bundle_manifest_checksum']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def _direct_anchor(ror_id: str) -> dict[str, Any]:
    return {
        "institution_authority_anchor_id": f"institution-authority-ror-{ror_id}",
        "authority_identifier": {"scheme": "ror", "value": ror_id},
        "canonical_institution_id": None,
        "metadata_status": "metadata-pending",
        "required_authority_bundle_version": (
            "hep-th-v1-historical-canonical-institutions-v2"
        ),
        "source_assertion_ids": [f"assertion-{ror_id}"],
        "source_occurrence_ids": [f"occurrence-{ror_id}"],
    }


def _affiliation_share(
    share_id: str,
    *,
    anchor_ids: list[str],
    numerator: int,
    denominator: int,
    paper_identity_status: str = "matched",
    inspire_recid: str | None = None,
) -> dict[str, Any]:
    share = {
        "paper_time_affiliation_share_id": share_id,
        "candidate_id": "paper-candidate-test",
        "canonical_paper_id": None,
        "paper_identity_status": paper_identity_status,
        "authorship_appearance_id": f"appearance-{share_id}",
        "institution_authority_anchor_ids": anchor_ids,
        "resolution_status": "withheld-unresolved-affiliation",
        "attribution_weight": {
            "numerator": numerator,
            "denominator": denominator,
            "exact": f"{numerator}/{denominator}",
        },
    }
    if inspire_recid is not None:
        share["resolution_evidence"] = [
            {
                "provider_institution_identifiers": [
                    {"scheme": "inspire-institution", "value": inspire_recid}
                ]
            }
        ]
    return share


def _resolution_rows(
    root: Path, manifest: dict[str, Any], role: str
) -> list[dict[str, Any]]:
    entry = next(item for item in manifest["artifacts"] if item["role"] == role)
    return [
        json.loads(line) for line in (root / entry["path"]).read_text().splitlines()
    ]


def _write_manual_canonical_bundle(
    root: Path,
    *,
    source_manifest_checksum: str,
    ror_id: str,
) -> Path:
    target_checksum = f"target-{ror_id}"
    acquisition_checksum = f"acquisition-{ror_id}"
    row = {
        "canonicalInstitutionId": f"institution-ror-{ror_id}",
        "rorId": ror_id,
        "canonicalName": f"Institution {ror_id}",
        "organizationStatus": "active",
        "countryCode": "US",
        "authorityRelationshipEvidence": [],
        "sourceManifestChecksum": source_manifest_checksum,
        "targetManifestChecksum": target_checksum,
        "acquisitionManifestChecksum": acquisition_checksum,
    }
    payload = json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    artifact_checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("canonical-institutions") / f"{artifact_checksum}.jsonl"
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    manifest: dict[str, Any] = {
        "manifest_version": "hep-th-v1-historical-canonical-institutions-v2",
        "source_manifest_checksum": source_manifest_checksum,
        "target_manifest_checksum": target_checksum,
        "acquisition_manifest_checksum": acquisition_checksum,
        "canonical_materialization_complete": True,
        "offline_normalization": True,
        "database_access": False,
        "affiliation_join": False,
        "record_count": 1,
        "artifact_path": relative.as_posix(),
        "artifact_checksum": artifact_checksum,
    }
    manifest["canonical_manifest_checksum"] = _checksum(manifest)
    path = (
        root / "canonical-manifests" / f"{manifest['canonical_manifest_checksum']}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def _write_supplemental_crosswalk(
    root: Path,
    *,
    replay_path: Path,
    inspire_recid: str,
    ror_id: str,
) -> Path:
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    target_checksum = "inspire-institution-target-checksum"
    acquisition_checksum = "inspire-institution-acquisition-checksum"
    source_document = {
        "provider": "inspire",
        "source_record_kind": "institution",
        "source_record_id": inspire_recid,
        "target_manifest_checksum": target_checksum,
        "source_manifest_checksum": replay["source_manifest_checksum"],
        "captured_at": "2026-09-04T00:00:00+00:00",
        "raw": {
            "id": inspire_recid,
            "metadata": {
                "control_number": int(inspire_recid),
                "external_system_identifiers": [
                    {"schema": "ROR", "value": f"https://ror.org/{ror_id}"}
                ],
            },
        },
    }
    source_payload = (
        json.dumps(source_document, separators=(",", ":"), sort_keys=True).encode()
        + b"\n"
    )
    source_checksum = hashlib.sha256(source_payload).hexdigest()
    source_relative = Path("records") / inspire_recid / f"{source_checksum}.json"
    source_path = root / source_relative
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(source_payload)
    row = {
        "inspireInstitutionId": inspire_recid,
        "rorIds": [ror_id],
        "resolutionStatus": "resolved-exact-explicit-ror-cross-reference",
        "candidateAttributionMass": {
            "numerator": 1,
            "denominator": 1,
            "exact": "1/1",
        },
        "sourceRecordChecksum": source_checksum,
        "sourceRecordPath": source_relative.as_posix(),
        "capturedAt": source_document["captured_at"],
        "targetManifestChecksum": target_checksum,
        "acquisitionManifestChecksum": acquisition_checksum,
        "crosswalkVersion": "hep-th-v1-inspire-ror-crosswalk-v1",
        "nameMatching": False,
        "eligibleForPublicMetrics": False,
    }
    payload = json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    artifact_checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("crosswalks") / f"{artifact_checksum}.jsonl"
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    manifest: dict[str, Any] = {
        "manifest_version": "hep-th-v1-inspire-ror-crosswalk-v1",
        "source_manifest_checksum": replay["source_manifest_checksum"],
        "replay_bundle_manifest_checksum": replay["bundle_manifest_checksum"],
        "target_manifest_checksum": target_checksum,
        "acquisition_manifest_checksum": acquisition_checksum,
        "acquisition_complete": True,
        "target_count": 1,
        "records_examined": 1,
        "exact_ror_crosswalk_count": 1,
        "unresolved_crosswalk_count": 0,
        "ambiguous_crosswalk_count": 0,
        "artifact": {
            "path": relative.as_posix(),
            "checksum": artifact_checksum,
            "row_count": 1,
            "byte_count": len(payload),
        },
        "registry_search": False,
        "name_matching": False,
        "database_access": False,
        "metric_observations_created": 0,
        "eligible_for_public_metrics": False,
    }
    manifest["crosswalk_manifest_checksum"] = _checksum(manifest)
    path = (
        root / "crosswalk-manifests" / f"{manifest['crosswalk_manifest_checksum']}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def test_target_manifest_is_deterministic_and_uses_only_staged_exact_ids(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")

    first = build_target_manifest(source)
    second = build_target_manifest(source)
    first_path, written = write_target_manifest(source, tmp_path / "ror-output")

    assert first == second
    assert first["target_ids"] == ["00hx57361", "03vek6s52"]
    assert first["target_count"] == 2
    assert first["registry_search"] is False
    assert first["database_access"] is False
    assert written["target_manifest_checksum"] == first_path.stem


def test_target_extraction_fails_closed_on_source_page_tampering(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    manifest = json.loads(source.read_text(encoding="utf-8"))
    page = tmp_path / "staging" / manifest["partitions"][0]["pages"][0]["path"]
    page.write_text("{}", encoding="utf-8")

    with pytest.raises(HistoricalRorSafetyError, match="page checksum"):
        build_target_manifest(source)


def test_exact_ror_acquisition_resumes_and_is_idempotent_without_search(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, output)
    transport = ExactRorTransport(fail_once_id="03vek6s52")

    _failed_path, failed = acquire_target_records(
        target_path,
        output,
        transport,
        ror_base_url="https://ror.test/v2",
    )
    assert failed["acquisition_complete"] is False
    assert failed["records_completed"] == 1

    _complete_path, complete = acquire_target_records(
        target_path,
        output,
        transport,
        ror_base_url="https://ror.test/v2",
    )
    assert complete["acquisition_complete"] is True
    assert complete["records_completed"] == 2
    assert [url for url, _params in transport.calls] == [
        "https://ror.test/v2/organizations/00hx57361",
        "https://ror.test/v2/organizations/03vek6s52",
        "https://ror.test/v2/organizations/03vek6s52",
    ]
    assert all(params is None for _url, params in transport.calls)
    assert all("?" not in url for url, _params in transport.calls)

    replay_transport = ExactRorTransport()
    _replay_path, replay = acquire_target_records(
        target_path,
        output,
        replay_transport,
        ror_base_url="https://ror.test/v2",
    )
    assert replay["acquisition_complete"] is True
    assert replay["records"] == complete["records"]
    assert replay_transport.calls == []


def test_exact_ror_acquisition_resumes_from_bounded_prefix(tmp_path: Path) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, output)
    transport = ExactRorTransport()

    _first_path, first = acquire_target_records(
        target_path,
        output,
        transport,
        ror_base_url="https://ror.test/v2",
        max_new_records=1,
    )
    assert first["terminal_status"] == "paused-limit"
    assert first["records_completed"] == 1

    _second_path, second = acquire_target_records(
        target_path,
        output,
        transport,
        ror_base_url="https://ror.test/v2",
        max_new_records=1,
    )
    assert second["terminal_status"] == "complete"
    assert second["acquisition_complete"] is True
    assert len(transport.calls) == 2


def test_resume_fails_before_network_when_immutable_record_is_corrupted(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging", ror_ids=("03vek6s52",))
    output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, output)
    transport = ExactRorTransport()
    _path, complete = acquire_target_records(
        target_path,
        output,
        transport,
        ror_base_url="https://ror.test/v2",
    )
    record_path = output / complete["records"][0]["path"]
    record_path.write_text("{}", encoding="utf-8")
    replay_transport = ExactRorTransport()

    with pytest.raises(HistoricalRorSafetyError, match="record checksum"):
        acquire_target_records(
            target_path,
            output,
            replay_transport,
            ror_base_url="https://ror.test/v2",
        )
    assert replay_transport.calls == []


def test_offline_canonical_institution_materialization_preserves_lineage(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    raw_output = tmp_path / "ror-output"
    target_path, target = write_target_manifest(source, raw_output)
    _acquisition_path, acquisition = acquire_target_records(
        target_path,
        raw_output,
        ExactRorTransport(),
        ror_base_url="https://ror.test/v2",
    )
    acquisition_path = (
        raw_output
        / "acquisition-manifests"
        / f"{acquisition['acquisition_manifest_checksum']}.json"
    )

    manifest_path, manifest = materialize_canonical_institutions(
        acquisition_path, tmp_path / "canonical-output"
    )
    repeated_path, repeated = materialize_canonical_institutions(
        acquisition_path, tmp_path / "canonical-output"
    )

    assert repeated_path == manifest_path
    assert repeated == manifest
    assert manifest["canonical_materialization_complete"] is True
    assert manifest["record_count"] == 2
    assert manifest["database_access"] is False
    assert manifest["affiliation_join"] is False
    assert manifest["target_manifest_checksum"] == target["target_manifest_checksum"]
    assert manifest_path.stem == manifest["canonical_manifest_checksum"]
    artifact = tmp_path / "canonical-output" / manifest["artifact_path"]
    assert (
        hashlib.sha256(artifact.read_bytes()).hexdigest()
        == manifest["artifact_checksum"]
    )
    rows = [json.loads(line) for line in artifact.read_text().splitlines()]
    assert [row["rorId"] for row in rows] == ["00hx57361", "03vek6s52"]
    assert rows[0]["canonicalName"] == "Institution 00hx57361"
    assert rows[0]["countryCode"] == "US"
    assert rows[0]["targetManifestChecksum"] == target["target_manifest_checksum"]
    assert rows[0]["organizationStatus"] == "active"
    assert rows[0]["sourceRecordEvidenceType"] == "provider-content-snapshot"
    assert rows[0]["authorityRelationshipEvidence"][0]["rorId"] == "03vek6s52"


def test_offline_materialization_rejects_incomplete_acquisition(tmp_path: Path) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, output)
    acquisition_path, acquisition = acquire_target_records(
        target_path,
        output,
        ExactRorTransport(fail_once_id="00hx57361"),
        ror_base_url="https://ror.test/v2",
    )
    assert acquisition["acquisition_complete"] is False

    with pytest.raises(HistoricalRorSafetyError, match="complete exact-ROR"):
        materialize_canonical_institutions(
            acquisition_path, tmp_path / "canonical-output"
        )


def test_offline_materialization_rejects_tampered_authority_record(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging", ror_ids=("03vek6s52",))
    output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, output)
    acquisition_path, acquisition = acquire_target_records(
        target_path,
        output,
        ExactRorTransport(),
        ror_base_url="https://ror.test/v2",
    )
    record_path = output / acquisition["records"][0]["path"]
    record_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(HistoricalRorSafetyError, match="record checksum"):
        materialize_canonical_institutions(
            acquisition_path, tmp_path / "canonical-output"
        )


def test_invalid_staged_ror_identifier_fails_closed(tmp_path: Path) -> None:
    source = _write_source_manifest(tmp_path / "staging", ror_ids=("not-a-ror",))

    with pytest.raises(HistoricalRorSafetyError, match="invalid ROR identifier"):
        build_target_manifest(source)


def test_exact_ror_cross_bundle_resolution_is_idempotent_and_conserves_mass(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    source_manifest = json.loads(source.read_text(encoding="utf-8"))
    raw_output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, raw_output)
    acquisition_path, acquisition = acquire_target_records(
        target_path,
        raw_output,
        ExactRorTransport(),
        ror_base_url="https://ror.test/v2",
    )
    assert acquisition["acquisition_complete"] is True
    canonical_path, _canonical = materialize_canonical_institutions(
        acquisition_path, tmp_path / "canonical-output"
    )
    replay_path = _write_replay_manifest(
        tmp_path / "replay-output",
        source_manifest_checksum=source_manifest["manifest_checksum"],
        anchors=[_direct_anchor("00hx57361"), _direct_anchor("03vek6s52")],
        shares=[
            _affiliation_share(
                "share-a",
                anchor_ids=["institution-authority-ror-00hx57361"],
                numerator=1,
                denominator=2,
            ),
            _affiliation_share(
                "share-b",
                anchor_ids=[],
                numerator=1,
                denominator=4,
            ),
            _affiliation_share(
                "share-c",
                anchor_ids=["institution-authority-ror-03vek6s52"],
                numerator=1,
                denominator=4,
            ),
        ],
        unmaterialized_paper_count=1,
    )
    output = tmp_path / "resolution-output"

    first_path, first = resolve_replay_institution_anchors(
        replay_path, canonical_path, output
    )
    second_path, second = resolve_replay_institution_anchors(
        replay_path, canonical_path, output
    )

    assert first_path == second_path
    assert first == second
    assert first["institution_resolution_manifest_checksum"] == (
        "6c8a1592276b5c17de8f9f3372b47df3a006ea0dc361c8933c77c96f3ae82cc9"
    )
    artifact_checksums = {
        artifact["role"]: artifact["checksum"] for artifact in first["artifacts"]
    }
    assert artifact_checksums == {
        "institution-authority-resolutions": (
            "9472f1b9b816b00ac5b46e32a4c02123fc1e83ef49968c7d7ae630bbbd4fa6f9"
        ),
        "paper-time-affiliation-resolution-projections": (
            "75ceec10163e1fde60a377d3e4a64d92764815c463721203e1e9016f1cddd63e"
        ),
    }
    assert "canonical_manifest_checksums" not in first
    assert "supplemental_crosswalk_manifest_checksum" not in first
    assert "direct_anchor_count" not in first
    assert "supplemental_anchor_count" not in first
    assert first["resolved_anchor_count"] == 2
    assert first["unresolved_anchor_count"] == 0
    assert first["resolved_affiliation_share_count"] == 2
    assert first["unresolved_affiliation_share_count"] == 1
    assert first["expected_paper_mass"]["exact"] == "2/1"
    assert first["evaluated_attribution_mass"]["exact"] == "1/1"
    assert first["unmaterialized_paper_mass"]["exact"] == "1/1"
    assert first["resolved_attribution_mass"]["exact"] == "3/4"
    assert first["withheld_attribution_mass"]["exact"] == "5/4"
    assert first["activation_eligible_rollup_attribution_mass"]["exact"] == "3/4"
    assert first["activation_withheld_rollup_attribution_mass"]["exact"] == "5/4"
    assert first["canonical_institution_coverage"]["exact"] == "3/8"
    assert first["mass_conservation_passed"] is True
    assert first["database_access"] is False
    assert first["metric_observations_created"] == 0
    projections = _resolution_rows(
        output, first, "paper-time-affiliation-resolution-projections"
    )
    assert "canonicalManifestChecksums" not in projections[0]
    assert "supplementalInstitutionAuthorityAnchorIds" not in projections[0]
    assert projections[0]["canonicalInstitutionId"] == ("institution-ror-00hx57361")
    assert projections[0]["countryId"] == "country-us"
    assert projections[0]["statisticalRollupInstitutionId"] == (
        "institution-ror-03vek6s52"
    )
    assert projections[1]["resolutionStatus"] == "unresolved-no-direct-ror-anchor"
    assert projections[1]["canonicalInstitutionId"] is None
    assert projections[2]["statisticalRollupInstitutionId"] == (
        "institution-ror-03vek6s52"
    )


def test_crosswalk_and_direct_anchors_merge_distinct_canonical_bundles(
    tmp_path: Path,
) -> None:
    source_checksum = "shared-source-manifest-checksum"
    direct_ror = "03vek6s52"
    supplemental_ror = "013m0ej23"
    replay_path = _write_replay_manifest(
        tmp_path / "replay-output",
        source_manifest_checksum=source_checksum,
        anchors=[_direct_anchor(direct_ror)],
        shares=[
            _affiliation_share(
                "share-direct",
                anchor_ids=[f"institution-authority-ror-{direct_ror}"],
                numerator=1,
                denominator=2,
                inspire_recid="500",
            ),
            _affiliation_share(
                "share-supplemental",
                anchor_ids=[],
                numerator=1,
                denominator=2,
                inspire_recid="500",
            ),
        ],
    )
    direct_bundle = _write_manual_canonical_bundle(
        tmp_path / "canonical-direct",
        source_manifest_checksum=source_checksum,
        ror_id=direct_ror,
    )
    supplemental_bundle = _write_manual_canonical_bundle(
        tmp_path / "canonical-supplemental",
        source_manifest_checksum=source_checksum,
        ror_id=supplemental_ror,
    )
    crosswalk = _write_supplemental_crosswalk(
        tmp_path / "crosswalk",
        replay_path=replay_path,
        inspire_recid="500",
        ror_id=supplemental_ror,
    )
    output = tmp_path / "resolution-output"

    first_path, first = resolve_replay_institution_anchors(
        replay_path,
        [supplemental_bundle, direct_bundle],
        output,
        supplemental_crosswalk_manifest_path=crosswalk,
    )
    second_path, second = resolve_replay_institution_anchors(
        replay_path,
        [direct_bundle, supplemental_bundle],
        output,
        supplemental_crosswalk_manifest_path=crosswalk,
    )

    assert first_path == second_path
    assert first == second
    assert first["canonical_institution_coverage"]["exact"] == "1/1"
    assert first["activation_eligible_rollup_attribution_mass"]["exact"] == "1/1"
    assert first["direct_anchor_count"] == 1
    assert first["supplemental_anchor_count"] == 1
    assert first["canonical_manifest_checksums"] == sorted(
        [direct_bundle.stem, supplemental_bundle.stem]
    )
    projections = {
        row["paperTimeAffiliationShareId"]: row
        for row in _resolution_rows(
            output, first, "paper-time-affiliation-resolution-projections"
        )
    }
    assert projections["share-direct"]["canonicalInstitutionId"] == (
        f"institution-ror-{direct_ror}"
    )
    assert (
        projections["share-direct"]["supplementalInstitutionAuthorityAnchorIds"] == []
    )
    assert projections["share-supplemental"]["canonicalInstitutionId"] == (
        f"institution-ror-{supplemental_ror}"
    )
    assert projections["share-supplemental"][
        "supplementalInstitutionAuthorityAnchorIds"
    ]


def test_resolver_rejects_rehashed_ror_not_present_in_source_snapshot(
    tmp_path: Path,
) -> None:
    source_checksum = "shared-source-manifest-checksum"
    source_ror = "013m0ej23"
    replay_path = _write_replay_manifest(
        tmp_path / "replay-output",
        source_manifest_checksum=source_checksum,
        anchors=[],
        shares=[
            _affiliation_share(
                "share-supplemental",
                anchor_ids=[],
                numerator=1,
                denominator=1,
                inspire_recid="500",
            )
        ],
    )
    canonical_bundle = _write_manual_canonical_bundle(
        tmp_path / "canonical",
        source_manifest_checksum=source_checksum,
        ror_id=source_ror,
    )
    crosswalk_path = _write_supplemental_crosswalk(
        tmp_path / "crosswalk",
        replay_path=replay_path,
        inspire_recid="500",
        ror_id=source_ror,
    )
    crosswalk_root = crosswalk_path.parent.parent
    crosswalk = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    artifact_path = crosswalk_root / crosswalk["artifact"]["path"]
    rows = [json.loads(line) for line in artifact_path.read_text().splitlines()]
    rows[0]["rorIds"] = ["03vek6s52"]
    payload = b"".join(
        json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        for row in rows
    )
    checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("crosswalks") / f"{checksum}.jsonl"
    (crosswalk_root / relative).write_bytes(payload)
    crosswalk.pop("crosswalk_manifest_checksum")
    crosswalk["artifact"] = {
        "path": relative.as_posix(),
        "checksum": checksum,
        "row_count": len(rows),
        "byte_count": len(payload),
    }
    crosswalk["crosswalk_manifest_checksum"] = _checksum(crosswalk)
    tampered_path = (
        crosswalk_root
        / "crosswalk-manifests"
        / f"{crosswalk['crosswalk_manifest_checksum']}.json"
    )
    tampered_path.write_text(json.dumps(crosswalk, sort_keys=True), encoding="utf-8")

    with pytest.raises(
        HistoricalRorSafetyError,
        match="supplemental crosswalk ROR evidence differs from its source snapshot",
    ):
        resolve_replay_institution_anchors(
            replay_path,
            canonical_bundle,
            tmp_path / "resolution-output",
            supplemental_crosswalk_manifest_path=tampered_path,
        )


def test_exact_ror_cross_bundle_resolution_does_not_name_match_missing_anchor(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    source_manifest = json.loads(source.read_text(encoding="utf-8"))
    raw_output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, raw_output)
    acquisition_path, _acquisition = acquire_target_records(
        target_path,
        raw_output,
        ExactRorTransport(),
        ror_base_url="https://ror.test/v2",
    )
    canonical_path, _canonical = materialize_canonical_institutions(
        acquisition_path, tmp_path / "canonical-output"
    )
    unknown = "04ttjf776"
    replay_path = _write_replay_manifest(
        tmp_path / "replay-output",
        source_manifest_checksum=source_manifest["manifest_checksum"],
        anchors=[_direct_anchor(unknown)],
        shares=[
            _affiliation_share(
                "share-unknown",
                anchor_ids=[f"institution-authority-ror-{unknown}"],
                numerator=1,
                denominator=1,
            )
        ],
    )

    _path, manifest = resolve_replay_institution_anchors(
        replay_path, canonical_path, tmp_path / "resolution-output"
    )

    assert manifest["resolved_anchor_count"] == 0
    assert manifest["unresolved_anchor_count"] == 1
    assert manifest["resolved_attribution_mass"]["exact"] == "0/1"
    assert manifest["withheld_attribution_mass"]["exact"] == "1/1"
    assert manifest["name_matching"] is False


def test_exact_ror_cross_bundle_resolution_rejects_tampered_replay_artifact(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    source_manifest = json.loads(source.read_text(encoding="utf-8"))
    raw_output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, raw_output)
    acquisition_path, _acquisition = acquire_target_records(
        target_path,
        raw_output,
        ExactRorTransport(),
        ror_base_url="https://ror.test/v2",
    )
    canonical_path, _canonical = materialize_canonical_institutions(
        acquisition_path, tmp_path / "canonical-output"
    )
    replay_path = _write_replay_manifest(
        tmp_path / "replay-output",
        source_manifest_checksum=source_manifest["manifest_checksum"],
        anchors=[_direct_anchor("00hx57361")],
        shares=[
            _affiliation_share(
                "share-a",
                anchor_ids=["institution-authority-ror-00hx57361"],
                numerator=1,
                denominator=1,
            )
        ],
    )
    replay_manifest = json.loads(replay_path.read_text(encoding="utf-8"))
    share_entry = next(
        item
        for item in replay_manifest["artifacts"]
        if item["role"] == "paper-time-affiliation-shares"
    )
    share_path = tmp_path / "replay-output" / share_entry["path"]
    share_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(HistoricalRorSafetyError, match="artifact checksum"):
        resolve_replay_institution_anchors(
            replay_path, canonical_path, tmp_path / "resolution-output"
        )


def test_cross_bundle_resolution_withholds_unmatched_paper_identity_mass(
    tmp_path: Path,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    source_manifest = json.loads(source.read_text(encoding="utf-8"))
    raw_output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, raw_output)
    acquisition_path, _acquisition = acquire_target_records(
        target_path,
        raw_output,
        ExactRorTransport(),
        ror_base_url="https://ror.test/v2",
    )
    canonical_path, _canonical = materialize_canonical_institutions(
        acquisition_path, tmp_path / "canonical-output"
    )
    replay_path = _write_replay_manifest(
        tmp_path / "replay-output",
        source_manifest_checksum=source_manifest["manifest_checksum"],
        anchors=[_direct_anchor("03vek6s52")],
        shares=[
            _affiliation_share(
                "share-needs-review",
                anchor_ids=["institution-authority-ror-03vek6s52"],
                numerator=1,
                denominator=1,
                paper_identity_status="needs_review",
            )
        ],
    )
    output = tmp_path / "resolution-output"

    _path, manifest = resolve_replay_institution_anchors(
        replay_path, canonical_path, output
    )

    assert manifest["authority_linked_attribution_mass"]["exact"] == "1/1"
    assert manifest["resolved_attribution_mass"]["exact"] == "0/1"
    assert manifest["activation_eligible_rollup_attribution_mass"]["exact"] == "0/1"
    assert manifest["canonical_institution_coverage"]["exact"] == "0/1"
    projection = _resolution_rows(
        output, manifest, "paper-time-affiliation-resolution-projections"
    )[0]
    assert projection["authorityLinkedCanonicalInstitutionId"] == (
        "institution-ror-03vek6s52"
    )
    assert projection["canonicalInstitutionId"] is None
    assert projection["resolutionStatus"] == ("withheld-paper-identity-needs-review")
    assert projection["statisticalRollupInstitutionId"] is None


@pytest.mark.parametrize(
    ("relationships", "status", "expected_rollup_status", "expected_target"),
    [
        (
            [
                {
                    "type": "predecessor",
                    "id": "https://ror.org/03vek6s52",
                    "label": "Prior authority",
                },
                {
                    "type": "successor",
                    "id": "https://ror.org/03vek6s52",
                    "label": "Later authority",
                },
            ],
            "active",
            "eligible-self-rollup",
            "institution-ror-00hx57361",
        ),
        (
            [
                {
                    "type": "parent",
                    "id": "https://ror.org/04ttjf776",
                    "label": "Unavailable parent",
                }
            ],
            "active",
            "withheld-parent-ror-metadata-unavailable",
            None,
        ),
        (
            [
                {
                    "type": "parent",
                    "id": "https://ror.org/03vek6s52",
                    "label": "Known parent",
                },
                {
                    "type": "parent",
                    "id": "https://ror.org/04ttjf776",
                    "label": "Second parent",
                },
            ],
            "active",
            "withheld-multiple-parent-rors",
            None,
        ),
        (
            [],
            "inactive",
            "withheld-child-lifecycle-status-not-active",
            None,
        ),
    ],
)
def test_pa035_rollup_is_parent_only_and_fails_closed(
    tmp_path: Path,
    relationships: list[dict[str, Any]],
    status: str,
    expected_rollup_status: str,
    expected_target: str | None,
) -> None:
    source = _write_source_manifest(tmp_path / "staging")
    source_manifest = json.loads(source.read_text(encoding="utf-8"))
    raw_output = tmp_path / "ror-output"
    target_path, _target = write_target_manifest(source, raw_output)
    acquisition_path, _acquisition = acquire_target_records(
        target_path,
        raw_output,
        ExactRorTransport(
            relationships_by_id={"00hx57361": relationships},
            status_by_id={"00hx57361": status},
        ),
        ror_base_url="https://ror.test/v2",
    )
    canonical_path, _canonical = materialize_canonical_institutions(
        acquisition_path, tmp_path / "canonical-output"
    )
    replay_path = _write_replay_manifest(
        tmp_path / "replay-output",
        source_manifest_checksum=source_manifest["manifest_checksum"],
        anchors=[_direct_anchor("00hx57361")],
        shares=[
            _affiliation_share(
                "share-a",
                anchor_ids=["institution-authority-ror-00hx57361"],
                numerator=1,
                denominator=1,
            )
        ],
    )
    output = tmp_path / "resolution-output"

    _path, manifest = resolve_replay_institution_anchors(
        replay_path, canonical_path, output
    )

    resolution = _resolution_rows(
        output, manifest, "institution-authority-resolutions"
    )[0]
    projection = _resolution_rows(
        output, manifest, "paper-time-affiliation-resolution-projections"
    )[0]
    assert resolution["statisticalRollupStatus"] == expected_rollup_status
    assert resolution["statisticalRollupInstitutionId"] == expected_target
    assert projection["statisticalRollupStatus"] == expected_rollup_status
    assert projection["statisticalRollupInstitutionId"] == expected_target
    if expected_rollup_status.startswith("eligible-"):
        assert manifest["activation_eligible_rollup_attribution_mass"]["exact"] == (
            "1/1"
        )
    else:
        assert manifest["activation_eligible_rollup_attribution_mass"]["exact"] == (
            "0/1"
        )
    if relationships and relationships[0]["type"] == "predecessor":
        assert resolution["predecessorEvidenceCount"] == 1
        assert resolution["successorEvidenceCount"] == 1
        assert resolution["parentRorIds"] == []
