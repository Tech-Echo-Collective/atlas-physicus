from __future__ import annotations

import io
import json
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO

import pytest

from physics_atlas_api.certification import CertificationError
from physics_atlas_api.metrics import calculate_activity_raw
from physics_atlas_api.storage.contracts import ArtifactRef, StorageTier
from physics_atlas_api.storage.dual_read import (
    PayloadAccessError,
    PayloadFailureCode,
    PayloadMode,
    StagingPayloadState,
    new_inline_state,
    prepare_reference,
    read_payload,
    rollback_to_inline,
)
from physics_atlas_api.storage.filesystem import FilesystemArtifactStore
from physics_atlas_api.storage.payloads import MAX_PAYLOAD_BYTES, PayloadMetadata


@pytest.fixture
def inline() -> StagingPayloadState:
    return new_inline_state(
        b' {"count":0,"missing":null,"fields":["1/3","2/3"],'
        b'"attribution":["1/4","3/4"]} \r\n',
        PayloadMetadata(
            provider="fixture",
            provider_record_id="page-0",
            acquisition_id="fixture-manifest-v1",
            snapshot_id="fixture-snapshot-0",
            acquisition_scope="fixture-bounded-scope",
            dataset_version="fixture-bounded-v1",
            acquired_at="2026-09-05T00:00:00Z",
            status="200",
            media_type="application/json",
        ),
    )


def test_inline_reference_and_rollback_preserve_exact_bytes_metadata_and_semantics(
    tmp_path: Path, inline: StagingPayloadState
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = prepare_reference(inline, store)
    rollback = rollback_to_inline(reference)
    assert inline.mode is PayloadMode.INLINE and inline.reference is None
    assert reference.mode is PayloadMode.REFERENCE
    assert rollback.mode is PayloadMode.INLINE
    assert rollback.reference == reference.reference
    assert prepare_reference(inline, store) == reference
    assert reference.metadata == rollback.metadata == inline.metadata
    assert reference.source_digest == rollback.source_digest == inline.source_digest
    assert (
        read_payload(inline) == read_payload(reference, store) == read_payload(rollback)
    )
    for state in (inline, reference, rollback):
        payload = json.loads(read_payload(state, store))
        assert payload["count"] == 0 and payload["missing"] is None
        assert "absent" not in payload
        assert sum(Fraction(value) for value in payload["fields"]) == 1
        assert sum(Fraction(value) for value in payload["attribution"]) == 1
        with pytest.raises(CertificationError, match="certify evidence first"):
            calculate_activity_raw(state)  # type: ignore[arg-type]
        with pytest.raises(CertificationError, match="certify evidence first"):
            calculate_activity_raw(payload)
    with pytest.raises(FrozenInstanceError):
        inline.mode = PayloadMode.REFERENCE  # type: ignore[misc]


def test_empty_payload_is_not_a_missing_reference(
    tmp_path: Path, inline: StagingPayloadState
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    empty = new_inline_state(b"", inline.metadata)
    assert read_payload(prepare_reference(empty, store), store) == b""


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("missing", PayloadFailureCode.MISSING_ARTIFACT),
        ("invalid", PayloadFailureCode.INVALID_REFERENCE),
        ("checksum", PayloadFailureCode.INTEGRITY_FAILURE),
        ("truncated", PayloadFailureCode.INTEGRITY_FAILURE),
        ("corrupt_gzip", PayloadFailureCode.INTEGRITY_FAILURE),
        ("unavailable", PayloadFailureCode.ARCHIVE_UNAVAILABLE),
        ("no_store", PayloadFailureCode.ARCHIVE_UNAVAILABLE),
    ],
)
def test_reference_failures_block_before_parser_without_inline_fallback(
    tmp_path: Path,
    inline: StagingPayloadState,
    failure: str,
    expected: PayloadFailureCode,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    state = prepare_reference(inline, store)
    assert state.reference is not None
    reference = state.reference
    active_store: FilesystemArtifactStore | None = store
    if failure == "missing":
        store.local_path(reference.artifact).unlink()
    elif failure == "invalid":
        state = replace(state, reference=replace(reference, version="invalid"))
    elif failure == "checksum":
        state = replace(state, reference=replace(reference, payload_sha256="0" * 64))
    elif failure == "truncated":
        path = store.local_path(reference.artifact)
        path.write_bytes(path.read_bytes()[:16])
    elif failure == "corrupt_gzip":
        artifact = store.put_bytes(
            b"not a gzip archive",
            tier=StorageTier.COLD,
            media_type=reference.artifact.media_type,
            content_encoding="gzip",
        )
        state = replace(state, reference=replace(reference, artifact=artifact))
    elif failure == "unavailable":

        class UnavailableStore(FilesystemArtifactStore):
            def open(self, reference: ArtifactRef) -> BinaryIO:
                raise OSError("archive temporarily unavailable")

        active_store = UnavailableStore(tmp_path)
    elif failure == "no_store":
        active_store = None
    parser_called = False
    checkpoint = {"sequence": 7, "state": state}
    with pytest.raises(PayloadAccessError) as caught:
        payload = read_payload(state, active_store)
        parser_called = True
        json.loads(payload)
        checkpoint["sequence"] = 8
    assert caught.value.code is expected
    assert caught.value.status == "blocked" and caught.value.operation == "read"
    assert not parser_called and checkpoint == {"sequence": 7, "state": state}
    assert state.inline_payload == inline.inline_payload
    # Rollback is an explicit operator selection, not a hidden reader fallback.
    assert read_payload(rollback_to_inline(state)) == read_payload(inline)


@pytest.mark.parametrize("failure", ["interrupted", "partial", "unavailable"])
def test_failed_archive_never_returns_candidate_or_advances_state(
    tmp_path: Path, inline: StagingPayloadState, failure: str
) -> None:
    class FailedWriteStore(FilesystemArtifactStore):
        def put_bytes(
            self,
            payload: bytes,
            *,
            tier: StorageTier,
            media_type: str,
            content_encoding: str = "identity",
        ) -> ArtifactRef:
            if failure == "interrupted":
                raise InterruptedError("write interrupted before publication")
            if failure == "unavailable":
                raise OSError("archive unavailable")
            reference = super().put_bytes(
                payload,
                tier=tier,
                media_type=media_type,
                content_encoding=content_encoding,
            )
            self.local_path(reference).write_bytes(payload[:16])
            return reference

    state = inline
    checkpoint = 7
    with pytest.raises(PayloadAccessError) as caught:
        candidate = prepare_reference(state, FailedWriteStore(tmp_path))
        state, checkpoint = candidate, 8
    expected = {
        "interrupted": PayloadFailureCode.INTERRUPTED_WRITE,
        "partial": PayloadFailureCode.INTEGRITY_FAILURE,
        "unavailable": PayloadFailureCode.ARCHIVE_UNAVAILABLE,
    }
    assert caught.value.code is expected[failure]
    assert caught.value.operation == "prepare" and caught.value.status == "blocked"
    assert state is inline and checkpoint == 7 and inline.reference is None
    assert read_payload(state) == inline.inline_payload


def test_read_after_write_must_verify_bytes_not_only_object_existence(
    tmp_path: Path, inline: StagingPayloadState
) -> None:
    class WrongReadStore(FilesystemArtifactStore):
        def open(self, reference: ArtifactRef) -> BinaryIO:
            return io.BytesIO(b"different bytes")

    with pytest.raises(PayloadAccessError) as caught:
        prepare_reference(inline, WrongReadStore(tmp_path))
    assert caught.value.code is PayloadFailureCode.INTEGRITY_FAILURE
    assert inline.mode is PayloadMode.INLINE and inline.reference is None


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "provider_record_id",
        "acquisition_id",
        "snapshot_id",
        "acquisition_scope",
        "dataset_version",
        "status",
        "media_type",
        "acquired_at",
    ],
)
def test_changed_acquisition_binding_blocks_both_read_modes_and_rollback(
    tmp_path: Path, inline: StagingPayloadState, field: str
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    reference = prepare_reference(inline, store)
    value = "2026-09-05T00:01:00Z" if field == "acquired_at" else "altered"
    for original in (inline, reference):
        changed = replace(
            original, metadata=replace(original.metadata, **{field: value})
        )
        with pytest.raises(PayloadAccessError, match="binding differs"):
            read_payload(changed, store)
        with pytest.raises(PayloadAccessError, match="binding differs"):
            rollback_to_inline(changed)


@pytest.mark.parametrize("payload", [None, b"changed"])
def test_rollback_fails_when_retained_inline_is_missing_or_corrupted(
    tmp_path: Path, inline: StagingPayloadState, payload: bytes | None
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    state = replace(prepare_reference(inline, store), inline_payload=payload)
    assert read_payload(state, store) == inline.inline_payload
    with pytest.raises(
        PayloadAccessError, match="inline payload is missing or differs"
    ):
        rollback_to_inline(state)
    assert state.mode is PayloadMode.REFERENCE


def test_invalid_state_size_version_mode_and_reference_selection_fail_closed(
    tmp_path: Path, inline: StagingPayloadState
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    for changed in (
        replace(inline, version="unsupported"),
        replace(inline, mode="auto"),  # type: ignore[arg-type]
        replace(inline, payload_size_bytes=True),
        replace(inline, payload_size_bytes=MAX_PAYLOAD_BYTES + 1),
        replace(inline, payload_sha256="invalid"),
    ):
        with pytest.raises(PayloadAccessError) as caught:
            read_payload(changed, store)
        assert caught.value.code is PayloadFailureCode.INVALID_STATE
    with pytest.raises(PayloadAccessError) as caught:
        read_payload(replace(inline, mode=PayloadMode.REFERENCE), store)
    assert caught.value.code is PayloadFailureCode.INVALID_REFERENCE
    with pytest.raises(PayloadAccessError, match="explicit inline selection"):
        prepare_reference(prepare_reference(inline, store), store)
    with pytest.raises(PayloadAccessError, match="16 MiB"):
        new_inline_state(b"x" * (MAX_PAYLOAD_BYTES + 1), inline.metadata)
