"""Fixed existing batch, private PostgreSQL only: dual read and rollback rehearsal.

This source-page catalog is an additive staging adapter, not production ORM DDL.
Inline original bytes are retained throughout. A verified transition changes only
storage mode; immutable source manifests and all scientific processing stay fixed.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import uuid
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from verify_payload_recovery import (
    CERTIFICATION_HASH,
    DIRECTORIES,
    ENRICHMENT_HASH,
    RAW_HASH,
    canonical_json,
    inventory,
    manifest_path,
    provenance_recovery,
    sha256,
    write_new,
)

from physics_atlas_api.certification.validation_artifacts import (
    require_validation_runtime,
)
from physics_atlas_api.paired_capture import (
    validate_staging_output,
    verify_paired_capture_manifest,
)
from physics_atlas_api.paired_enrichment import verify_paired_enrichment_manifest
from physics_atlas_api.paired_trial_certification import (
    _canonicalize,
    _load_occurrences,
    certify_paired_trial,
)
from physics_atlas_api.storage import ArtifactRef, FilesystemArtifactStore, StorageTier
from physics_atlas_api.storage.dual_read import (
    PayloadAccessError,
    PayloadMode,
    StagingPayloadState,
    new_inline_state,
    prepare_reference,
    read_payload,
    rollback_to_inline,
)
from physics_atlas_api.storage.historical_read import read_artifact
from physics_atlas_api.storage.payloads import PayloadMetadata, PayloadReference

DATABASE = "physics_atlas_storage_benchmark"


def pack_state(state):
    value = asdict(state)
    inline = value.pop("inline_payload")
    return inline, value


def unpack_state(row):
    value = dict(row["state"])
    value["metadata"] = PayloadMetadata(**value["metadata"])
    value["mode"] = PayloadMode(value["mode"])
    if value["reference"] is not None:
        reference = dict(value["reference"])
        reference["metadata"] = PayloadMetadata(**reference["metadata"])
        artifact = dict(reference["artifact"])
        artifact["tier"] = StorageTier(artifact["tier"])
        reference["artifact"] = ArtifactRef(**artifact)
        value["reference"] = PayloadReference(**reference)
    return StagingPayloadState(inline_payload=bytes(row["inline_payload"]), **value)


class StagingBatch:
    """Fresh-schema-only state; no deployment tables, DSN or acquisition cursor."""

    def __init__(self, connection, rows):
        self.connection = connection
        self.schema = "dual_read_" + uuid.uuid4().hex[:12]
        with connection.transaction(), connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema))
            )
            cursor.execute(
                sql.SQL("SET search_path TO {}, pg_catalog").format(
                    sql.Identifier(self.schema)
                )
            )
            cursor.execute("""
                CREATE TABLE payloads (
                    id text PRIMARY KEY, tree text NOT NULL, path text NOT NULL,
                    kind text NOT NULL, inline_payload bytea NOT NULL,
                    state jsonb NOT NULL, UNIQUE(tree,path));
                CREATE TABLE checkpoint (
                    id integer PRIMARY KEY CHECK (id=1), generation integer NOT NULL,
                    mode text NOT NULL, source_manifest text NOT NULL,
                    enrichment_manifest text NOT NULL);
            """)
            cursor.execute(
                "INSERT INTO checkpoint VALUES (1,0,'inline',%s,%s)",
                (RAW_HASH, ENRICHMENT_HASH),
            )
            for row in rows:
                inline, state = pack_state(row["payload_state"])
                cursor.execute(
                    "INSERT INTO payloads VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        row["id"],
                        row["tree"],
                        row["path"],
                        row["kind"],
                        inline,
                        Jsonb(state),
                    ),
                )

    def rows(self):
        return self.connection.execute("SELECT * FROM payloads ORDER BY id").fetchall()

    def checkpoint(self):
        return self.connection.execute("SELECT * FROM checkpoint").fetchone()

    def fingerprint(self):
        return sha256(
            canonical_json({"rows": self.rows(), "checkpoint": self.checkpoint()})
        )

    def transition(self, transform, target, *, interrupt_sql=False):
        checkpoint = self.checkpoint()
        rows = self.rows()
        # All external writes and read-after-write checks precede any SQL change.
        candidates = [(row, transform(unpack_state(row))) for row in rows]
        with self.connection.transaction(), self.connection.cursor() as cursor:
            for index, (row, candidate) in enumerate(candidates):
                inline, state = pack_state(candidate)
                if inline != bytes(row["inline_payload"]):
                    raise ValueError("staging must retain every original inline byte")
                cursor.execute(
                    "UPDATE payloads SET state=%s WHERE id=%s AND state=%s",
                    (Jsonb(state), row["id"], Jsonb(row["state"])),
                )
                if cursor.rowcount != 1:
                    raise ValueError("staging source state changed concurrently")
                if interrupt_sql and index == 0:
                    raise RuntimeError("injected interruption before checkpoint commit")
            cursor.execute(
                "UPDATE checkpoint SET generation=generation+1,mode=%s "
                "WHERE id=1 AND generation=%s",
                (target.value, checkpoint["generation"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("staging checkpoint changed concurrently")


def restore_files(rows, store, destination):
    """Read and verify the whole bounded batch before creating a parser input tree."""
    if destination.exists():
        raise ValueError("restore destination must be new")
    recovered = []
    for row in rows:
        relative = Path(row["tree"]) / row["path"]
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("restore path must remain inside its staging tree")
        recovered.append((relative, read_payload(unpack_state(row), store)))
    for relative, body in recovered:
        write_new(destination / relative, body)
    return len(recovered)


def scientific_result(rows, store, destination, roots, original_occurrences):
    require_validation_runtime()
    count = restore_files(rows, store, destination / "sources")
    raw_root = destination / "sources" / "raw"
    enrichment_root = destination / "sources" / "enrichment"
    raw_manifest = manifest_path(raw_root, RAW_HASH)
    raw = verify_paired_capture_manifest(raw_manifest, output=raw_root)
    occurrences = _load_occurrences(raw_root, raw)
    assert occurrences == original_occurrences
    assert _canonicalize(occurrences) == _canonicalize(original_occurrences)
    generated, manifest = certify_paired_trial(
        raw_root=raw_root,
        raw_manifest_path=raw_manifest,
        enrichment_root=enrichment_root,
        enrichment_manifest_path=manifest_path(enrichment_root, ENRICHMENT_HASH),
        output=destination / "certification",
    )
    assert (
        manifest.read_bytes()
        == manifest_path(roots["certification"], CERTIFICATION_HASH).read_bytes()
    )
    for entry in generated["artifacts"]:
        body = read_artifact(destination / "certification", entry)
        assert body == read_artifact(roots["certification"], entry)
        assert sha256(body) == entry["checksum"]
    decisions_entry = next(
        entry for entry in generated["artifacts"] if entry["role"] == "decisions"
    )
    decisions = [
        json.loads(line)
        for line in (destination / "certification" / decisions_entry["path"])
        .read_bytes()
        .splitlines()
    ]
    catalog = [
        {
            "path": row["path"],
            "kind": row["kind"],
            "checksum": row["state"]["payload_sha256"],
            "reference": {"metadata": row["state"]["metadata"]},
        }
        for row in rows
    ]
    return {
        "files_restored_exactly": count,
        "source_normalization_equal": True,
        "canonicalization_equal": True,
        "source_normalization_digest": sha256(
            canonical_json([asdict(item) for item in occurrences])
        ),
        "certification_manifest_sha256": sha256(manifest.read_bytes()),
        "artifacts": generated["artifacts"],
        "decision_count": len(decisions),
        "decision_states": dict(Counter(item["state"] for item in decisions)),
        "provenance": provenance_recovery(decisions, occurrences, catalog),
        "metric_observations_created": generated["metric_observations_created"],
        "certified_complete_year_count": generated["certified_complete_year_count"],
        "certified_metric_window_count": generated["certified_metric_window_count"],
    }


class UnavailableStore(FilesystemArtifactStore):
    def open(self, reference):
        raise OSError("injected unavailable archive")


class TruncatedStore(FilesystemArtifactStore):
    def open(self, reference):
        return io.BytesIO(self.local_path(reference).read_bytes()[:-1])


class InterruptedStore(FilesystemArtifactStore):
    calls = 0

    def put_bytes(self, payload, **options):
        self.calls += 1
        if self.calls == 2:
            write_new(
                self._root / "unpublished-partial.tmp", payload[: len(payload) // 2]
            )
            raise OSError("injected interrupted partial archive write")
        return super().put_bytes(payload, **options)


def blocked_attempt(batch, name, operation, destination=None):
    before = batch.fingerprint()
    try:
        operation()
    except (PayloadAccessError, RuntimeError) as error:
        if not isinstance(error, PayloadAccessError) and not (
            name == "interrupted_sql_transaction"
            and str(error) == "injected interruption before checkpoint commit"
        ):
            raise
        assert batch.fingerprint() == before
        assert destination is None or not destination.exists()
        return {
            "case": name,
            "status": getattr(error, "status", "blocked"),
            "code": str(getattr(error, "code", "transaction_interrupted")),
            "sql_rows_and_checkpoint_unchanged": True,
            "no_parser_or_certification_output": True,
        }
    raise AssertionError(f"failure injection did not block: {name}")


def fixed_inventory(roots, raw, enrichment):
    rows = inventory(raw, enrichment)
    for tree, manifest, checksum in (
        ("raw", raw, RAW_HASH),
        ("enrichment", enrichment, ENRICHMENT_HASH),
    ):
        path = manifest_path(roots[tree], checksum)
        rows.append(
            {
                "tree": tree,
                "path": path.relative_to(roots[tree]).as_posix(),
                "kind": "manifest",
                "checksum": sha256(path.read_bytes()),
                "metadata": PayloadMetadata(
                    provider="physics-atlas",
                    provider_record_id=checksum,
                    acquisition_id=checksum,
                    snapshot_id=checksum,
                    acquisition_scope=raw["pair_id"],
                    dataset_version=manifest["manifest_version"],
                    acquired_at=manifest["completed_at"],
                    status="retained-official-manifest",
                    media_type="application/json",
                ),
            }
        )
    for row in rows:
        payload = (roots[row["tree"]] / row["path"]).read_bytes()
        assert sha256(payload) == row["checksum"]
        row["id"] = row["tree"] + ":" + row["path"]
        row["payload_state"] = new_inline_state(payload, row["metadata"])
    assert len(rows) == 449
    return rows


def run(evidence, output, socket):
    require_validation_runtime()
    if not __debug__:
        raise RuntimeError(
            "proof checks require assertions; optimized Python is forbidden"
        )
    roots = {key: evidence.resolve() / value for key, value in DIRECTORIES.items()}
    output = validate_staging_output(output)
    if any(
        output.is_relative_to(root) or root.is_relative_to(output)
        for root in roots.values()
    ):
        raise ValueError("output must not overlap retained evidence")
    socket = socket.resolve(strict=True)
    if (
        socket.parent != Path("/private/tmp")
        or not socket.name.startswith("physics-atlas-storage.")
        or socket.stat().st_uid != os.getuid()
        or not (socket / ".s.PGSQL.55439").is_socket()
    ):
        raise ValueError("only the owned private benchmark Unix socket is permitted")
    raw_path = manifest_path(roots["raw"], RAW_HASH)
    raw = verify_paired_capture_manifest(raw_path, output=roots["raw"])
    enrichment = verify_paired_enrichment_manifest(
        manifest_path(roots["enrichment"], ENRICHMENT_HASH),
        output=roots["enrichment"],
        paired_manifest_path=raw_path,
    )
    assert (
        raw["manifest_checksum"] == RAW_HASH
        and enrichment["manifest_checksum"] == ENRICHMENT_HASH
    )
    occurrences = _load_occurrences(roots["raw"], raw)
    assert len(occurrences) == 635 and len(_canonicalize(occurrences)) == 474
    source_rows = fixed_inventory(roots, raw, enrichment)
    output.mkdir(parents=True, exist_ok=False)
    store = FilesystemArtifactStore(output / "cold-artifacts")
    with psycopg.connect(
        host=str(socket),
        port=55439,
        dbname=DATABASE,
        autocommit=True,
        row_factory=dict_row,
    ) as connection:
        server = connection.execute(
            "SELECT current_database() AS database,version() AS version,"
            "inet_server_addr() AS address"
        ).fetchone()
        if server["database"] != DATABASE or server["address"] is not None:
            raise ValueError("network/production PostgreSQL is forbidden")
        batch = StagingBatch(connection, source_rows)
        initial_rows, initial_checkpoint = batch.rows(), batch.checkpoint()
        inline = scientific_result(
            initial_rows, None, output / "inline", roots, occurrences
        )
        interrupted_store = InterruptedStore(output / "partial-archive")
        failures = [
            blocked_attempt(
                batch,
                "interrupted_partial_archive_write",
                lambda: batch.transition(
                    lambda state: prepare_reference(state, interrupted_store),
                    PayloadMode.REFERENCE,
                ),
            )
        ]
        failures.append(
            blocked_attempt(
                batch,
                "interrupted_sql_transaction",
                lambda: batch.transition(
                    lambda state: prepare_reference(state, store),
                    PayloadMode.REFERENCE,
                    interrupt_sql=True,
                ),
            )
        )
        batch.transition(
            lambda state: prepare_reference(state, store), PayloadMode.REFERENCE
        )
        referenced_rows = batch.rows()
        reference_checkpoint = batch.checkpoint()
        reference = scientific_result(
            referenced_rows, store, output / "reference", roots, occurrences
        )
        assert inline == reference
        for name, fault_store in (
            ("missing_artifact", FilesystemArtifactStore(output / "missing")),
            ("truncated_artifact", TruncatedStore(output / "cold-artifacts")),
            ("unavailable_archive", UnavailableStore(output / "cold-artifacts")),
        ):
            destination = output / ("blocked-" + name)
            failures.append(
                blocked_attempt(
                    batch,
                    name,
                    partial(restore_files, referenced_rows, fault_store, destination),
                    destination,
                )
            )
        for name, field, value in (
            ("invalid_reference", "version", "invalid-version"),
            ("checksum_mismatch", "payload_sha256", "0" * 64),
        ):
            fault_rows = [dict(row) for row in referenced_rows]
            state = unpack_state(fault_rows[0])
            state = replace(state, reference=replace(state.reference, **{field: value}))
            fault_rows[0]["inline_payload"], fault_rows[0]["state"] = pack_state(state)
            destination = output / ("blocked-" + name)
            failures.append(
                blocked_attempt(
                    batch,
                    name,
                    partial(restore_files, fault_rows, store, destination),
                    destination,
                )
            )
        # Rollback has no archive dependency, even when every cold read is unavailable.
        batch.transition(rollback_to_inline, PayloadMode.INLINE)
        rollback_rows = batch.rows()
        rollback = scientific_result(
            rollback_rows,
            UnavailableStore(output / "cold-artifacts"),
            output / "rollback",
            roots,
            occurrences,
        )
        assert inline == rollback
        final_checkpoint = batch.checkpoint()
        assert all(
            bytes(before["inline_payload"]) == bytes(after["inline_payload"])
            for before, after in zip(initial_rows, rollback_rows, strict=True)
        )
        assert all(row["state"]["reference"] is not None for row in rollback_rows)
        result = {
            "version": "bounded-staging-dual-read-pilot-v1",
            "measured_at": datetime.now(UTC).isoformat(),
            "server": server,
            "schema": batch.schema,
            "source_manifest": RAW_HASH,
            "enrichment_manifest": ENRICHMENT_HASH,
            "source_occurrences": 635,
            "canonical_papers": 474,
            "source_files": 449,
            "inline": inline,
            "reference": reference,
            "rollback": rollback,
            "failure_cases": failures,
            "checkpoints": {
                "initial": initial_checkpoint,
                "reference": reference_checkpoint,
                "rollback": final_checkpoint,
            },
            "inline_bytes_retained": True,
            "source_manifests_unchanged": True,
            "reference_read_does_not_fallback": True,
            "rollback_requires_archive": False,
            "network_acquisition": False,
            "production_mutations": False,
        }
    write_new(output / "staging-report.json", canonical_json(result) + b"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    arguments = parser.parse_args()
    result = run(arguments.evidence, arguments.output, arguments.socket)
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("schema", "source_files", "failure_cases", "checkpoints")
            },
            indent=2,
        )
    )
