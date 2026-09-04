import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pytest

from physics_atlas_api.historical_inspire_institutions import (
    acquire_inspire_institution_records,
    build_inspire_institution_target_manifest,
    materialize_explicit_ror_crosswalk,
    project_supplemental_institution_coverage,
    write_inspire_institution_target_manifest,
)
from physics_atlas_api.historical_ror import HistoricalRorSafetyError, _checksum

_CAPTURED = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)


def _weight(numerator: int, denominator: int = 1) -> dict[str, int | str]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "exact": f"{numerator}/{denominator}",
    }


def _share(
    share_id: str,
    record_id: str | None,
    *,
    weight: tuple[int, int] = (1, 1),
    direct_ror: str | None = None,
    paper_status: str = "matched",
) -> dict[str, Any]:
    provider_ids = (
        [{"scheme": "inspire-institution", "value": record_id}]
        if record_id is not None
        else []
    )
    return {
        "paper_time_affiliation_share_id": share_id,
        "candidate_id": f"paper-{share_id}",
        "paper_identity_status": paper_status,
        "attribution_weight": _weight(*weight),
        "institution_authority_anchor_ids": (
            [f"institution-authority-ror-{direct_ror}"] if direct_ror else []
        ),
        "resolution_evidence": [{"provider_institution_identifiers": provider_ids}],
    }


def _write_replay(root: Path, shares: list[dict[str, Any]]) -> Path:
    payload = b"".join(
        json.dumps(item, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        for item in shares
    )
    artifact_checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("relationships/affiliations") / f"{artifact_checksum}.jsonl"
    artifact = root / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(payload)
    manifest: dict[str, Any] = {
        "bundle_version": "hep-th-v1-historical-replay-bundle-v1",
        "source_manifest_checksum": "source-manifest-checksum",
        "network_access": False,
        "database_access": False,
        "metric_observations_created": 0,
        "artifacts": [
            {
                "role": "paper-time-affiliation-shares",
                "path": relative.as_posix(),
                "checksum": artifact_checksum,
                "row_count": len(shares),
                "byte_count": len(payload),
            }
        ],
    }
    manifest["bundle_manifest_checksum"] = _checksum(manifest)
    path = root / "manifests" / f"{manifest['bundle_manifest_checksum']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def _write_content_document(
    directory: Path, body: dict[str, Any], checksum_field: str
) -> Path:
    body[checksum_field] = _checksum(body)
    path = directory / f"{body[checksum_field]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, sort_keys=True), encoding="utf-8")
    return path


def _write_baseline_resolution(
    root: Path, replay: Path, shares: list[dict[str, Any]]
) -> Path:
    replay_manifest = json.loads(replay.read_text(encoding="utf-8"))
    rows = [
        {
            "paperTimeAffiliationShareId": share["paper_time_affiliation_share_id"],
            "statisticalRollupStatus": "withheld-no-resolved-child-ror",
        }
        for share in shares
    ]
    payload = b"".join(
        json.dumps(item, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        for item in rows
    )
    checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("affiliation-resolution-projections") / f"{checksum}.jsonl"
    artifact = root / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(payload)
    manifest = {
        "manifest_version": "hep-th-v1-historical-institution-resolutions-v2",
        "replay_bundle_manifest_checksum": replay_manifest["bundle_manifest_checksum"],
        "source_manifest_checksum": replay_manifest["source_manifest_checksum"],
        "mass_conservation_passed": True,
        "expected_paper_mass": _weight(1),
        "activation_eligible_rollup_attribution_mass": _weight(0),
        "artifacts": [
            {
                "role": "paper-time-affiliation-resolution-projections",
                "path": relative.as_posix(),
                "checksum": checksum,
                "row_count": len(rows),
                "byte_count": len(payload),
            }
        ],
    }
    return _write_content_document(
        root / "institution-resolution-manifests",
        manifest,
        "institution_resolution_manifest_checksum",
    )


def _write_canonical_authorities(root: Path, ror_ids: list[str]) -> Path:
    target_checksum = "canonical-target-checksum"
    acquisition_checksum = "canonical-acquisition-checksum"
    rows = [
        {
            "canonicalInstitutionId": f"institution-ror-{ror_id}",
            "rorId": ror_id,
            "canonicalName": f"Institution {ror_id}",
            "organizationStatus": "active",
            "countryCode": "US",
            "authorityRelationshipEvidence": [],
            "sourceManifestChecksum": "source-manifest-checksum",
            "targetManifestChecksum": target_checksum,
            "acquisitionManifestChecksum": acquisition_checksum,
        }
        for ror_id in ror_ids
    ]
    payload = b"".join(
        json.dumps(item, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        for item in rows
    )
    checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("canonical-institutions") / f"{checksum}.jsonl"
    artifact = root / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(payload)
    manifest = {
        "manifest_version": "hep-th-v1-historical-canonical-institutions-v2",
        "source_manifest_checksum": "source-manifest-checksum",
        "canonical_materialization_complete": True,
        "offline_normalization": True,
        "database_access": False,
        "affiliation_join": False,
        "target_manifest_checksum": target_checksum,
        "acquisition_manifest_checksum": acquisition_checksum,
        "record_count": len(rows),
        "artifact_path": relative.as_posix(),
        "artifact_checksum": checksum,
    }
    return _write_content_document(
        root / "canonical-manifests", manifest, "canonical_manifest_checksum"
    )


class ExactInstitutionTransport:
    def __init__(self, ror_by_record: dict[str, list[str]]):
        self.ror_by_record = ror_by_record
        self.calls: list[str] = []

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
        del params, headers
        record_id = url.rstrip("/").rsplit("/", 1)[-1]
        self.calls.append(record_id)
        return {
            "id": record_id,
            "metadata": {
                "control_number": int(record_id),
                "external_system_identifiers": [
                    {"schema": "ROR", "value": f"https://ror.org/{ror_id}"}
                    for ror_id in self.ror_by_record[record_id]
                ],
            },
            "updated": "2026-08-30T00:00:00+00:00",
        }

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        del url, params, headers
        raise AssertionError("institution records use JSON only")


def test_target_manifest_prioritizes_exact_unanchored_matched_mass(
    tmp_path: Path,
) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [
            _share("small", "100", weight=(1, 4)),
            _share("large", "200", weight=(3, 4)),
            _share("direct", "300", direct_ror="03vek6s52"),
            _share("review", "400", paper_status="needs_review"),
            _share("missing", None),
        ],
    )

    target = build_inspire_institution_target_manifest(replay)

    assert [item["inspire_institution_id"] for item in target["targets"]] == [
        "200",
        "100",
    ]
    assert target["target_candidate_attribution_mass"] == _weight(1)
    assert target["excluded_direct_ror_anchor_mass"] == _weight(1)
    assert target["excluded_paper_identity_review_mass"] == _weight(1)
    assert target["no_provider_institution_id_mass"] == _weight(1)
    assert target["multiple_provider_institution_id_mass"] == _weight(0)
    assert target["registry_search"] is False
    assert target["name_matching"] is False


def test_acquisition_resumes_exact_target_prefix_and_crosswalks_explicit_ror(
    tmp_path: Path,
) -> None:
    shares = [
        _share("first", "200", weight=(3, 4)),
        _share("second", "100", weight=(1, 4)),
    ]
    replay = _write_replay(
        tmp_path / "replay",
        shares,
    )
    output = tmp_path / "institution-evidence"
    target_path, _target = write_inspire_institution_target_manifest(replay, output)
    transport = ExactInstitutionTransport({"200": ["013m0ej23"], "100": []})

    first_path, first = acquire_inspire_institution_records(
        target_path,
        output,
        transport,
        max_new_records=1,
        now=lambda: _CAPTURED,
    )
    assert first["terminal_status"] == "paused-limit"
    assert first["records_completed"] == 1
    assert transport.calls == ["200"]
    with pytest.raises(HistoricalRorSafetyError, match="complete exact institution"):
        materialize_explicit_ror_crosswalk(first_path, output)

    second_path, second = acquire_inspire_institution_records(
        target_path,
        output,
        transport,
        max_new_records=1,
        now=lambda: _CAPTURED,
    )
    assert second["terminal_status"] == "complete"
    assert second["acquisition_complete"] is True
    assert second["records_completed"] == 2
    assert transport.calls == ["200", "100"]
    assert first_path != second_path

    crosswalk_path, crosswalk, ror_target_path, ror_target = (
        materialize_explicit_ror_crosswalk(second_path, output)
    )
    assert crosswalk_path.is_file()
    assert crosswalk["records_examined"] == 2
    assert crosswalk["exact_ror_crosswalk_count"] == 1
    assert crosswalk["unresolved_crosswalk_count"] == 1
    assert crosswalk["ambiguous_crosswalk_count"] == 0
    assert crosswalk["exact_ror_candidate_attribution_mass"] == _weight(3, 4)
    assert crosswalk["unresolved_candidate_attribution_mass"] == _weight(1, 4)
    assert crosswalk["resolution_method"] == (
        "exact-explicit-provider-cross-reference-only"
    )
    assert ror_target_path.is_file()
    assert ror_target["target_ids"] == ["013m0ej23"]
    assert ror_target["registry_search"] is False

    baseline = _write_baseline_resolution(tmp_path / "baseline", replay, shares)
    canonical = _write_canonical_authorities(tmp_path / "canonical", ["013m0ej23"])
    projection_path, projection = project_supplemental_institution_coverage(
        replay,
        baseline,
        crosswalk_path,
        [canonical],
        output,
    )
    assert projection_path.is_file()
    assert projection["candidate_attribution_mass"] == _weight(3, 4)
    assert projection["added_activation_eligible_mass"] == _weight(3, 4)
    assert projection["combined_canonical_institution_coverage"] == _weight(3, 4)
    assert projection["supplemental_rollup_status_counts"] == {
        "eligible-self-rollup": 1
    }
    assert projection["name_matching"] is False
    assert projection["eligible_for_public_metrics"] is False


def test_crosswalk_keeps_multiple_explicit_ror_ids_ambiguous(tmp_path: Path) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [_share("ambiguous", "500")],
    )
    output = tmp_path / "institution-evidence"
    target_path, _target = write_inspire_institution_target_manifest(replay, output)
    transport = ExactInstitutionTransport({"500": ["013m0ej23", "03vek6s52"]})
    acquisition_path, acquisition = acquire_inspire_institution_records(
        target_path,
        output,
        transport,
        now=lambda: _CAPTURED,
    )
    assert acquisition["acquisition_complete"] is True

    _path, crosswalk, _ror_path, ror_target = materialize_explicit_ror_crosswalk(
        acquisition_path, output
    )

    assert crosswalk["exact_ror_crosswalk_count"] == 0
    assert crosswalk["ambiguous_crosswalk_count"] == 1
    assert crosswalk["ambiguous_candidate_attribution_mass"] == _weight(1)
    assert ror_target["target_ids"] == []


def test_empty_target_completes_with_empty_crosswalk_and_no_provider_call(
    tmp_path: Path,
) -> None:
    replay = _write_replay(tmp_path / "replay", [])
    output = tmp_path / "institution-evidence"
    target_path, target = write_inspire_institution_target_manifest(replay, output)
    transport = ExactInstitutionTransport({})

    acquisition_path, acquisition = acquire_inspire_institution_records(
        target_path,
        output,
        transport,
        now=lambda: _CAPTURED,
    )
    crosswalk_path, crosswalk, ror_target_path, ror_target = (
        materialize_explicit_ror_crosswalk(acquisition_path, output)
    )

    assert target["target_count"] == 0
    assert transport.calls == []
    assert acquisition["acquisition_complete"] is True
    assert acquisition["records_completed"] == 0
    assert crosswalk_path.is_file()
    assert crosswalk["records_examined"] == 0
    assert crosswalk["exact_ror_crosswalk_count"] == 0
    assert ror_target_path.is_file()
    assert ror_target["target_ids"] == []


def test_crosswalk_rejects_reordered_records_and_source_lineage_tampering(
    tmp_path: Path,
) -> None:
    replay = _write_replay(
        tmp_path / "replay",
        [_share("first", "200"), _share("second", "100")],
    )
    output = tmp_path / "institution-evidence"
    target_path, _target = write_inspire_institution_target_manifest(replay, output)
    acquisition_path, acquisition = acquire_inspire_institution_records(
        target_path,
        output,
        ExactInstitutionTransport({"200": ["013m0ej23"], "100": ["03vek6s52"]}),
        now=lambda: _CAPTURED,
    )
    assert acquisition["acquisition_complete"] is True

    reordered = dict(acquisition)
    reordered.pop("acquisition_manifest_checksum")
    reordered["records"] = list(reversed(acquisition["records"]))
    reordered_path = _write_content_document(
        output / "acquisition-manifests",
        reordered,
        "acquisition_manifest_checksum",
    )
    with pytest.raises(HistoricalRorSafetyError, match="exact target sequence"):
        materialize_explicit_ror_crosswalk(reordered_path, output)

    wrong_lineage = dict(acquisition)
    wrong_lineage.pop("acquisition_manifest_checksum")
    wrong_lineage["source_manifest_checksum"] = "wrong-source"
    wrong_lineage_path = _write_content_document(
        output / "acquisition-manifests",
        wrong_lineage,
        "acquisition_manifest_checksum",
    )
    with pytest.raises(HistoricalRorSafetyError, match="lineage is inconsistent"):
        materialize_explicit_ror_crosswalk(wrong_lineage_path, output)


def test_projection_rejects_duplicate_crosswalk_recids(tmp_path: Path) -> None:
    shares = [_share("first", "200"), _share("second", "100")]
    replay = _write_replay(tmp_path / "replay", shares)
    baseline = _write_baseline_resolution(tmp_path / "baseline", replay, shares)
    output = tmp_path / "institution-evidence"
    target_path, _target = write_inspire_institution_target_manifest(replay, output)
    acquisition_path, _acquisition = acquire_inspire_institution_records(
        target_path,
        output,
        ExactInstitutionTransport({"200": ["013m0ej23"], "100": ["03vek6s52"]}),
        now=lambda: _CAPTURED,
    )
    crosswalk_path, crosswalk, _ror_path, _ror_target = (
        materialize_explicit_ror_crosswalk(acquisition_path, output)
    )
    artifact_path = output / crosswalk["artifact"]["path"]
    rows = [json.loads(line) for line in artifact_path.read_text().splitlines()]
    rows[1]["inspireInstitutionId"] = rows[0]["inspireInstitutionId"]
    payload = b"".join(
        json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        for row in rows
    )
    checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("crosswalks") / f"{checksum}.jsonl"
    (output / relative).write_bytes(payload)
    tampered_manifest = dict(crosswalk)
    tampered_manifest.pop("crosswalk_manifest_checksum")
    tampered_manifest["artifact"] = {
        "path": relative.as_posix(),
        "checksum": checksum,
        "row_count": len(rows),
        "byte_count": len(payload),
    }
    tampered_path = _write_content_document(
        output / "crosswalk-manifests",
        tampered_manifest,
        "crosswalk_manifest_checksum",
    )

    with pytest.raises(HistoricalRorSafetyError, match="crosswalk row is malformed"):
        project_supplemental_institution_coverage(
            replay,
            baseline,
            tampered_path,
            [],
            output,
        )
    assert crosswalk_path.is_file()


def test_projection_rejects_rehashed_ror_not_present_in_source_snapshot(
    tmp_path: Path,
) -> None:
    shares = [_share("first", "200")]
    replay = _write_replay(tmp_path / "replay", shares)
    baseline = _write_baseline_resolution(tmp_path / "baseline", replay, shares)
    output = tmp_path / "institution-evidence"
    target_path, _target = write_inspire_institution_target_manifest(replay, output)
    acquisition_path, _acquisition = acquire_inspire_institution_records(
        target_path,
        output,
        ExactInstitutionTransport({"200": ["013m0ej23"]}),
        now=lambda: _CAPTURED,
    )
    _crosswalk_path, crosswalk, _ror_path, _ror_target = (
        materialize_explicit_ror_crosswalk(acquisition_path, output)
    )
    artifact_path = output / crosswalk["artifact"]["path"]
    rows = [json.loads(line) for line in artifact_path.read_text().splitlines()]
    rows[0]["rorIds"] = ["03vek6s52"]
    payload = b"".join(
        json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        for row in rows
    )
    checksum = hashlib.sha256(payload).hexdigest()
    relative = Path("crosswalks") / f"{checksum}.jsonl"
    (output / relative).write_bytes(payload)
    tampered_manifest = dict(crosswalk)
    tampered_manifest.pop("crosswalk_manifest_checksum")
    tampered_manifest["artifact"] = {
        "path": relative.as_posix(),
        "checksum": checksum,
        "row_count": len(rows),
        "byte_count": len(payload),
    }
    tampered_path = _write_content_document(
        output / "crosswalk-manifests",
        tampered_manifest,
        "crosswalk_manifest_checksum",
    )

    with pytest.raises(
        HistoricalRorSafetyError,
        match="crosswalk ROR evidence differs from its source snapshot",
    ):
        project_supplemental_institution_coverage(
            replay,
            baseline,
            tampered_path,
            [],
            output,
        )
