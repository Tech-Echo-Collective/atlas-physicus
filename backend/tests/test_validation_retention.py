"""Tiny local fixtures: cumulative accounting is not scientific processing."""

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from physics_atlas_api.certification.contracts import CertificationError
from physics_atlas_api.storage.validation_retention import (
    MAX_PERSISTENT_VALIDATION_BYTES,
    RetainedValidationFile,
    RetentionClass,
    ValidationRetentionError,
    ValidationRetentionInventory,
    ValidationRetentionReservation,
    check_validation_reservation_output,
    preflight_validation_retention,
    require_validation_retention_budget,
    verify_validation_retention_files,
)

SHA = hashlib.sha256(b"fixture manifest").hexdigest()


def entry(path: Path, content: bytes = b"prior proof") -> RetainedValidationFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return RetainedValidationFile(
        storage_reference=str(path.resolve()),
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        classification=RetentionClass.KEEP,
        pipeline_version="previous-pipeline-v1",
        sample_id="previous-sample-v1",
    )


def inventory(
    tmp_path: Path, files: tuple[RetainedValidationFile, ...] = ()
) -> ValidationRetentionInventory:
    return ValidationRetentionInventory(
        scope_id="all-retained-validation-v1",
        measured_at="2026-09-05T00:00:00+00:00",
        managed_root=str(tmp_path.resolve() / "managed-validation"),
        files=files,
        metadata_bytes=10,
        total_bytes=10 + sum(item.size_bytes for item in files),
        complete=True,
    )


def reserve(
    value: ValidationRetentionInventory | None, **overrides: Any
) -> ValidationRetentionReservation:
    arguments = {
        "expected_inventory_sha256": value.sha256 if value else SHA,
        "sample_id": "bounded-cross-field-v1",
        "expected_sample_id": "bounded-cross-field-v1",
        "sample_manifest_sha256": SHA,
        "expected_sample_manifest_sha256": SHA,
        "paper_count": 1000,
        "pipeline_version": "fixture-pipeline-v2",
        "proof_manifest_sha256": SHA,
        "reserved_new_bytes": 50,
    }
    arguments.update(overrides)
    return require_validation_retention_budget(value, **arguments)


def test_bounded_admission_binds_exact_sample_version_and_inventory(
    tmp_path: Path,
) -> None:
    value = inventory(tmp_path, (entry(tmp_path / "legacy.jsonl"),))
    result = reserve(value)
    assert result.policy_version == "validation-retention-budget-v1"
    assert result.inventory_sha256 == value.sha256
    assert result.sample_manifest_sha256 == SHA
    assert result.output_reference == str(
        tmp_path.resolve()
        / "managed-validation/bounded-cross-field-v1/fixture-pipeline-v2"
        / SHA
    )
    assert result.retained_bytes == 21
    assert result.projected_bytes == 71
    assert result.limit_bytes == 1_073_741_824
    preflight_validation_retention(value, result, verify_hashes=True)
    check_validation_reservation_output(result, bytes_to_retain=50)
    assert not Path(result.output_reference).exists()  # admission writes nothing


def test_old_versions_duplicate_copies_and_archive_plus_expanded_all_count(
    tmp_path: Path,
) -> None:
    files = (
        entry(tmp_path / "old-version/inline.jsonl", b"same"),
        entry(tmp_path / "new-version/reference.jsonl", b"same"),
        entry(tmp_path / "rollback.jsonl", b"same"),
        entry(tmp_path / "expanded.jsonl", b"expanded source"),
        entry(tmp_path / "archive.jsonl.gz", b"small"),
    )
    value = inventory(tmp_path, files)
    assert files[0].sha256 == files[1].sha256 == files[2].sha256
    assert value.total_bytes == 42
    result = reserve(value, reserved_new_bytes=8, limit_bytes=50)
    assert result.projected_bytes == 50  # equality is permitted, not rounded
    with pytest.raises(ValidationRetentionError, match="budget exceeded"):
        reserve(value, reserved_new_bytes=9, limit_bytes=50)


@pytest.mark.parametrize("classification", list(RetentionClass))
def test_retention_class_never_subtracts_physical_bytes(
    classification: RetentionClass, tmp_path: Path
) -> None:
    item = replace(entry(tmp_path / "proof.json"), classification=classification)
    value = inventory(tmp_path, (item,))
    assert reserve(value).retained_bytes == 21
    with pytest.raises(ValidationRetentionError, match="budget exceeded"):
        reserve(value, limit_bytes=70)
    assert Path(item.storage_reference).exists()


def test_cumulative_cap_counts_old_versions_even_when_each_trace_is_small(
    tmp_path: Path,
) -> None:
    files = tuple(
        RetainedValidationFile(
            storage_reference=str(tmp_path.resolve() / f"v{number}/proof.jsonl"),
            size_bytes=100 * 1024 * 1024,
            sha256=SHA,
            classification=RetentionClass.REVIEW,
            pipeline_version=f"pipeline-v{number}",
            sample_id="prior-sample-v1",
        )
        for number in range(11)
    )
    with pytest.raises(ValidationRetentionError, match="budget exceeded"):
        reserve(inventory(tmp_path, files))


@pytest.mark.parametrize("size", [None, True, -1, 2.5])
def test_missing_or_unknown_size_fails_closed(size: Any, tmp_path: Path) -> None:
    with pytest.raises(ValidationRetentionError, match="size_bytes"):
        replace(entry(tmp_path / "file"), size_bytes=size)


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"complete": False}, "completeness"),
        ({"complete": 1}, "completeness"),
        ({"total_bytes": 11}, "total"),
        ({"metadata_bytes": -1}, "metadata_bytes"),
        ({"measured_at": "2026-09-05"}, "measurement time"),
        ({"version": "unreviewed-v2"}, "version"),
        ({"managed_root": "relative"}, "canonical path"),
    ],
)
def test_incomplete_or_inconsistent_inventory_rejected(
    changes: dict[str, Any], message: str, tmp_path: Path
) -> None:
    with pytest.raises(ValidationRetentionError, match=message):
        replace(inventory(tmp_path), **changes)


def test_duplicate_physical_paths_rejected(tmp_path: Path) -> None:
    item = entry(tmp_path / "file")
    with pytest.raises(ValidationRetentionError, match="duplicate physical path"):
        inventory(tmp_path, (item, item))


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"expected_inventory_sha256": "0" * 64}, "inventory checksum"),
        ({"expected_inventory_sha256": "invalid"}, "SHA-256"),
        ({"sample_id": "another-sample"}, "sample identity"),
        ({"sample_manifest_sha256": "0" * 64}, "sample identity"),
        ({"proof_manifest_sha256": "unknown"}, "SHA-256"),
        ({"reserved_new_bytes": 0}, "reserved_new_bytes"),
        ({"reserved_new_bytes": None}, "reserved_new_bytes"),
        ({"limit_bytes": MAX_PERSISTENT_VALIDATION_BYTES + 1}, "cannot be raised"),
        ({"limit_bytes": True}, "limit_bytes"),
        ({"pipeline_version": "../escape"}, "identifier"),
    ],
)
def test_invalid_or_mismatched_admission_rejected(
    changes: dict[str, Any], message: str, tmp_path: Path
) -> None:
    with pytest.raises(ValidationRetentionError, match=message):
        reserve(inventory(tmp_path), **changes)


def test_missing_inventory_fails_closed() -> None:
    with pytest.raises(ValidationRetentionError, match="inventory is required"):
        reserve(None)


@pytest.mark.parametrize("paper_count", [None, 0, True, 2501])
def test_existing_paper_limit_is_not_weakened(paper_count: Any, tmp_path: Path) -> None:
    with pytest.raises(CertificationError, match="explicit validation_max_papers"):
        reserve(inventory(tmp_path), paper_count=paper_count)


def test_inventory_checksum_is_order_stable_and_covers_classification(
    tmp_path: Path,
) -> None:
    first, second = entry(tmp_path / "a"), entry(tmp_path / "b")
    value = inventory(tmp_path, (first, second))
    assert value.sha256 == inventory(tmp_path, (second, first)).sha256
    assert (
        value.sha256
        != inventory(
            tmp_path, (replace(first, classification=RetentionClass.REVIEW), second)
        ).sha256
    )


def test_metadata_only_preflight_never_reads_scientific_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = entry(tmp_path / "proof.jsonl")
    value = inventory(tmp_path, (item,))
    result = reserve(value)

    def no_read(*_: object, **__: object) -> None:
        pytest.fail("metadata accounting must not read scientific payloads")

    monkeypatch.setattr(Path, "open", no_read)
    preflight_validation_retention(value, result)


@pytest.mark.parametrize("condition", ["missing", "resized", "bad-hash"])
def test_file_preflight_failures_do_not_become_free_space(
    condition: str, tmp_path: Path
) -> None:
    item = entry(tmp_path / "proof.jsonl")
    value = inventory(tmp_path, (item,))
    if condition == "missing":
        Path(item.storage_reference).unlink()
    elif condition == "resized":
        Path(item.storage_reference).write_bytes(b"changed length")
    else:
        Path(item.storage_reference).write_bytes(b"other proof")
    with pytest.raises(ValidationRetentionError):
        preflight_validation_retention(value, reserve(value), verify_hashes=True)


def test_unlisted_old_version_file_under_managed_root_refuses_new_run(
    tmp_path: Path,
) -> None:
    value = inventory(tmp_path)
    old = Path(value.managed_root) / "old-sample/old-version/unknown.jsonl"
    entry(old)
    with pytest.raises(ValidationRetentionError, match="unlisted"):
        preflight_validation_retention(value, reserve(value))
    assert old.exists()


def test_symlink_is_not_a_deduplicated_or_safe_representation(tmp_path: Path) -> None:
    item = entry(tmp_path / "original")
    alias = tmp_path / "alias"
    alias.symlink_to(item.storage_reference)
    with pytest.raises(ValidationRetentionError, match="unsafe"):
        verify_validation_retention_files(
            inventory(tmp_path, (replace(item, storage_reference=str(alias)),))
        )


def test_not_yet_created_root_cannot_hide_behind_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real-root"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    value = replace(inventory(tmp_path), managed_root=str(alias / "not-yet-created"))
    with pytest.raises(ValidationRetentionError, match="invalid managed"):
        preflight_validation_retention(value, reserve(value))
    assert not (target / "not-yet-created").exists()


def test_proof_is_versioned_immutable_and_cannot_exceed_reservation(
    tmp_path: Path,
) -> None:
    value = inventory(tmp_path)
    result = reserve(value)
    with pytest.raises(ValidationRetentionError, match="exceeds its reservation"):
        check_validation_reservation_output(result, bytes_to_retain=51)
    output = Path(result.output_reference)
    output.mkdir(parents=True)
    with pytest.raises(ValidationRetentionError, match="already exists"):
        check_validation_reservation_output(result, bytes_to_retain=50)
    assert output.is_dir()
    later = reserve(value, pipeline_version="fixture-pipeline-v3")
    assert later.output_reference != result.output_reference


def test_tampered_reservation_is_not_accepted(tmp_path: Path) -> None:
    value = inventory(tmp_path)
    result = reserve(value)
    with pytest.raises(ValidationRetentionError, match="inconsistent"):
        preflight_validation_retention(
            value, replace(result, projected_bytes=0, output_reference=str(tmp_path))
        )
    with pytest.raises(ValidationRetentionError, match="inventory checksum"):
        preflight_validation_retention(
            replace(value, metadata_bytes=11, total_bytes=11), result
        )


def test_accounting_never_changes_scientific_decisions_or_authority(
    tmp_path: Path,
) -> None:
    content = (
        b'{"status":"certified","value":0,"field_weights":[0.5,0.5]}\n'
        b'{"status":"needs_review","value":null,"reason":"unresolved"}\n'
        b'{"status":"withheld","provenance":"source-v1","eligible":false}\n'
        b'{"status":"conflicted","institution_id":null}\n'
    )
    item = entry(tmp_path / "authoritative-proof.jsonl", content)
    value = inventory(tmp_path, (item,))
    preflight_validation_retention(value, reserve(value), verify_hashes=True)
    assert Path(item.storage_reference).read_bytes() == content
    assert hashlib.sha256(content).hexdigest() == item.sha256


def test_production_refuses_before_inventory_or_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "production")
    monkeypatch.setenv("PHYSICS_ATLAS_FIXTURE_MODE", "false")
    with pytest.raises(CertificationError, match="forbidden in production"):
        reserve(None)
