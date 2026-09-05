"""Small offline fixture integration, never the retained scientific corpus."""

import json
from pathlib import Path

import pytest
from test_paired_trial_certification import _fixture_bundle

from physics_atlas_api.certification.contracts import CertificationError
from physics_atlas_api.metrics import calculate_activity_raw
from physics_atlas_api.paired_capture import verify_paired_capture_manifest
from physics_atlas_api.paired_trial_certification import (
    _canonicalize,
    _load_occurrences,
    certify_paired_trial,
)
from physics_atlas_api.storage import FilesystemArtifactStore
from physics_atlas_api.storage.payloads import (
    PayloadMetadata,
    archive_payload,
    recover_payload,
)


def test_recovered_payloads_reproduce_parser_and_all_certification_bytes(
    tmp_path: Path,
) -> None:
    raw, raw_manifest, enrichment, enrichment_manifest, baseline, manifest = (
        _fixture_bundle(tmp_path)
    )
    original_manifest = json.loads(manifest.read_bytes())
    store = FilesystemArtifactStore(tmp_path / "cold")
    restored_raw = tmp_path / "restored-raw"
    restored_enrichment = tmp_path / "restored-enrichment"
    for source_root, restored_root in (
        (raw, restored_raw),
        (enrichment, restored_enrichment),
    ):
        for source in sorted(source_root.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(source_root)
            payload = source.read_bytes()
            reference = archive_payload(
                payload,
                PayloadMetadata(
                    provider="offline-fixture",
                    provider_record_id=relative.as_posix(),
                    acquisition_id="fixture-acquisition",
                    snapshot_id=source.stem,
                    acquisition_scope="offline-test-only",
                    dataset_version="unchanged-fixture-v1",
                    acquired_at="2026-09-04T12:00:00+00:00",
                    status="fixture-not-live",
                    media_type="application/octet-stream",
                ),
                store,
            )
            recovered = recover_payload(reference, store)
            assert recovered == payload
            target = restored_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(recovered)
            # Recovery references and bytes are not scientific credentials.
            for candidate in (reference, recovered):
                with pytest.raises(CertificationError, match="certify evidence first"):
                    calculate_activity_raw(candidate)  # type: ignore[arg-type]
    recovered_raw_manifest = restored_raw / raw_manifest.relative_to(raw)
    recovered_enrichment_manifest = (
        restored_enrichment / enrichment_manifest.relative_to(enrichment)
    )
    original = _load_occurrences(
        raw, verify_paired_capture_manifest(raw_manifest, output=raw)
    )
    recovered = _load_occurrences(
        restored_raw,
        verify_paired_capture_manifest(recovered_raw_manifest, output=restored_raw),
    )
    assert original == recovered
    assert _canonicalize(original) == _canonicalize(recovered)
    output = tmp_path / "recovered-certification"
    recovered_manifest, recovered_path = certify_paired_trial(
        raw_root=restored_raw,
        raw_manifest_path=recovered_raw_manifest,
        enrichment_root=restored_enrichment,
        enrichment_manifest_path=recovered_enrichment_manifest,
        output=output,
    )
    assert recovered_path.read_bytes() == manifest.read_bytes()
    assert recovered_manifest == original_manifest
    assert len(recovered_manifest["artifacts"]) == 10
    for entry in recovered_manifest["artifacts"]:
        assert (output / entry["path"]).read_bytes() == (
            baseline / entry["path"]
        ).read_bytes()
    assert recovered_manifest["metric_observations_created"] == 0
    assert recovered_manifest["certified_complete_year_count"] == 0
    assert recovered_manifest["certified_metric_window_count"] == 0
