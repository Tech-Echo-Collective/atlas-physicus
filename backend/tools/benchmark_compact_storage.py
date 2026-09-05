"""Private PostgreSQL sample benchmark, not a production migration or replay.
Expanded JSONB is hypothetical; production has no certification-decision table.
Both representations expose the same current fields and semantic query indexes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from physics_atlas_api.storage import ArtifactRef, FilesystemArtifactStore, StorageTier
from physics_atlas_api.storage.audit import build_postgres_storage_audit_queries
from physics_atlas_api.storage.compact import (
    CompactDecisionBatch,
    CompactDecisionRow,
    compact_decisions,
    recover_decisions,
)

DATABASE = "physics_atlas_storage_benchmark"
SOURCE_SHA256 = "b21157332f997ad41bc251ff3a317faba6281892ec21d3e35d49905890ba63fb"
TEXT_FIELDS = (
    "canonical_paper_id",
    "subject_type",
    "subject_id",
    "evidence_kind",
    "state",
    "rule_version",
)
DDL = """
CREATE TABLE expanded_decisions (
 decision_id bytea PRIMARY KEY, decision_sha256 bytea NOT NULL,
 canonical_paper_id text, subject_type text NOT NULL, subject_id text NOT NULL,
 evidence_kind text NOT NULL, state text NOT NULL, rule_version text NOT NULL,
 audit_ordinal integer NOT NULL, payload jsonb NOT NULL);
CREATE INDEX expanded_paper ON expanded_decisions(canonical_paper_id);
CREATE INDEX expanded_subject_kind ON expanded_decisions(subject_id,evidence_kind);
CREATE TABLE compact_terms (id integer PRIMARY KEY,value text NOT NULL UNIQUE);
CREATE TABLE compact_reasons (code smallint PRIMARY KEY,reasons text[] NOT NULL);
CREATE TABLE compact_batch (id smallint PRIMARY KEY,version text NOT NULL,
 dataset_version text NOT NULL,acquisition_scope text NOT NULL,artifact jsonb NOT NULL);
CREATE TABLE compact_decisions (
 decision_id bytea PRIMARY KEY,decision_sha256 bytea NOT NULL,
 canonical_paper_id integer REFERENCES compact_terms(id),
 subject_type integer NOT NULL REFERENCES compact_terms(id),
 subject_id integer NOT NULL REFERENCES compact_terms(id),
 evidence_kind integer NOT NULL REFERENCES compact_terms(id),
 state integer NOT NULL REFERENCES compact_terms(id),
 rule_version integer NOT NULL REFERENCES compact_terms(id),
 reason_code smallint NOT NULL REFERENCES compact_reasons(code),
 audit_ordinal integer NOT NULL,
 batch_id smallint NOT NULL REFERENCES compact_batch(id));
CREATE INDEX compact_paper ON compact_decisions(canonical_paper_id);
CREATE INDEX compact_subject_kind ON compact_decisions(subject_id,evidence_kind);
"""


def measurements(connection, schema):
    queries = build_postgres_storage_audit_queries()
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            queries.relations.replace("n.nspname = 'public'", "n.nspname = %s"),
            (schema,),
        )
        relations = cursor.fetchall()
        for relation in relations:
            cursor.execute(
                sql.SQL("SELECT count(*) AS rows FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(relation["relation"])
                )
            )
            relation.update(cursor.fetchone())
            relation["bytes_per_row"] = (
                relation["total_bytes"] / relation["rows"] if relation["rows"] else None
            )
        cursor.execute(
            queries.indexes.replace("n.nspname = 'public'", "n.nspname = %s"),
            (schema,),
        )
        return {"relations": relations, "indexes": cursor.fetchall()}


def totals(measured, prefix, papers, decisions):
    rows = [row for row in measured["relations"] if row["relation"].startswith(prefix)]
    result = {
        key: sum(row[key] for row in rows)
        for key in (
            "heap_main_bytes",
            "heap_auxiliary_bytes",
            "toast_bytes",
            "table_bytes",
            "index_bytes",
            "total_bytes",
        )
    }
    result.update(
        bytes_per_paper=result["total_bytes"] / papers,
        bytes_per_decision=result["total_bytes"] / decisions,
        decimal_mb_per_10k_papers=result["total_bytes"] / papers / 100,
    )
    return result


def benchmark(source: Path, socket: Path, output: Path) -> dict:
    socket = socket.resolve(strict=True)
    if (
        socket.parent != Path("/private/tmp")
        or not socket.name.startswith("physics-atlas-storage.")
        or socket.stat().st_uid != os.getuid()
        or not (socket / ".s.PGSQL.55439").is_socket()
    ):
        raise ValueError("only the owned private benchmark Unix socket is allowed")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError(
            "source must be the existing content-addressed paired decisions"
        )
    originals = [json.loads(line) for line in data.splitlines()]
    if len(originals) != 9999:
        raise ValueError("benchmark is limited to the existing 9,999-decision sample")
    output.mkdir(parents=True, exist_ok=False)
    store = FilesystemArtifactStore(output / "artifacts")
    batch = compact_decisions(originals, store)
    payloads = {row["decision_id"]: row for row in originals}
    terms = sorted(
        {
            getattr(row, field)
            for row in batch.rows
            for field in TEXT_FIELDS
            if getattr(row, field) is not None
        }
    )
    term_ids = {value: index for index, value in enumerate(terms)}
    schema = "compact_bench_" + uuid.uuid4().hex[:12]
    with psycopg.connect(host=str(socket), port=55439, dbname=DATABASE) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(),version(),inet_server_addr()")
            database, server, address = cursor.fetchone()
            if database != DATABASE or address is not None:
                raise ValueError("benchmark cannot connect to a network database")
            cursor.execute("SELECT pg_database_size(current_database())")
            database_before = cursor.fetchone()[0]
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(
                sql.SQL("SET search_path TO {},pg_catalog").format(
                    sql.Identifier(schema)
                )
            )
            cursor.execute(DDL)
            empty = measurements(connection, schema)
            cursor.executemany(
                "INSERT INTO compact_terms VALUES(%s,%s)", enumerate(terms)
            )
            cursor.executemany(
                "INSERT INTO compact_reasons VALUES(%s,%s)",
                [(index, list(value)) for index, value in enumerate(batch.reasons)],
            )
            cursor.execute(
                "INSERT INTO compact_batch VALUES(1,%s,%s,%s,%s)",
                (
                    batch.version,
                    batch.dataset_version,
                    batch.acquisition_scope,
                    Jsonb(asdict(batch.artifact)),
                ),
            )
            expanded, compact = [], []
            for row in batch.rows:
                if (
                    not row.decision_id.startswith("cert-")
                    or len(row.decision_id) != 69
                ):
                    raise ValueError("sample decision IDs must contain exact SHA-256")
                identity = bytes.fromhex(row.decision_id[5:])
                digest = bytes.fromhex(row.decision_sha256)
                strings = [getattr(row, field) for field in TEXT_FIELDS]
                prefix = (identity, digest, *strings, row.audit_ordinal)
                expanded.append((*prefix, Jsonb(payloads[row.decision_id])))
                codes = [term_ids.get(value) for value in strings]
                suffix = (row.reason_code, row.audit_ordinal, 1)
                compact.append((identity, digest, *codes, *suffix))
            cursor.executemany(
                "INSERT INTO expanded_decisions VALUES(" + ",".join(["%s"] * 10) + ")",
                expanded,
            )
            cursor.executemany(
                "INSERT INTO compact_decisions VALUES(" + ",".join(["%s"] * 11) + ")",
                compact,
            )
        connection.commit()
        # Analyze only this isolated schema. No VACUUM/rewrite or production query.
        with connection.cursor() as cursor:
            for relation in empty["relations"]:
                cursor.execute(
                    sql.SQL("ANALYZE {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(relation["relation"])
                    )
                )
        measured = measurements(connection, schema)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT id,value FROM compact_terms")
            decoded_terms = {row["id"]: row["value"] for row in cursor.fetchall()}
            cursor.execute("SELECT reasons FROM compact_reasons ORDER BY code")
            reasons = tuple(tuple(row["reasons"]) for row in cursor.fetchall())
            cursor.execute("SELECT * FROM compact_batch WHERE id=1")
            saved_batch = cursor.fetchone()
            artifact = dict(saved_batch["artifact"])
            artifact["tier"] = StorageTier(artifact["tier"])
            cursor.execute("SELECT * FROM compact_decisions ORDER BY audit_ordinal")
            restored_rows = []
            for saved in cursor.fetchall():
                if saved.pop("batch_id") != 1:
                    raise ValueError("unexpected batch reference")
                saved["decision_id"] = "cert-" + bytes(saved["decision_id"]).hex()
                saved["decision_sha256"] = bytes(saved["decision_sha256"]).hex()
                for field in TEXT_FIELDS:
                    saved[field] = decoded_terms.get(saved[field])
                restored_rows.append(CompactDecisionRow(**saved))
            restored_batch = CompactDecisionBatch(
                saved_batch["version"],
                saved_batch["dataset_version"],
                saved_batch["acquisition_scope"],
                ArtifactRef(**artifact),
                reasons,
                tuple(restored_rows),
            )
            if restored_batch != batch:
                raise ValueError("SQL projection did not reconstruct exactly")
            recovered = recover_decisions(restored_batch, store)
            if recovered != tuple(
                sorted(originals, key=lambda row: row["decision_id"])
            ):
                raise ValueError(
                    "SQL plus cold audit did not preserve original decisions"
                )
            cursor.execute(
                "SELECT payload FROM expanded_decisions ORDER BY decision_id"
            )
            if tuple(row["payload"] for row in cursor.fetchall()) != recovered:
                raise ValueError("expanded PostgreSQL comparison lost source values")
            cursor.execute("SELECT pg_database_size(current_database()) AS bytes")
            database_after = cursor.fetchone()["bytes"]
    papers = len({row["canonical_paper_id"] for row in originals})
    result = {
        "version": "compact-storage-measurement-v1",
        "measured_at": datetime.now(UTC).isoformat(),
        "source_sha256": SOURCE_SHA256,
        "source_bytes": len(data),
        "papers": papers,
        "decisions": len(originals),
        "postgresql": server,
        "database": DATABASE,
        "schema": schema,
        "database_bytes_before": database_before,
        "database_bytes_after": database_after,
        "empty_schema": empty,
        "populated_schema": measured,
        "expanded": totals(measured, "expanded_", papers, len(originals)),
        "compact": totals(measured, "compact_", papers, len(originals)),
        "cold_artifact": asdict(batch.artifact),
        "reason_catalog_rows": len(batch.reasons),
        "text_dictionary_rows": len(terms),
        "states": dict(Counter(row.state for row in batch.rows)),
        "sql_roundtrip_exact": True,
        "complete_json_recovery": True,
        "production_writes": False,
        "scientific_policy_changes": False,
        "limitations": [
            "hypothetical expanded JSONB baseline, not deployed certification schema",
            "474-paper certification component only; not representative capacity",
            "provider artifact availability is not validated by decision recovery",
        ],
    }
    (output / "measurement.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--socket-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = benchmark(args.source, args.socket_dir, args.output)
    keys = ("expanded", "compact", "cold_artifact", "sql_roundtrip_exact")
    print(json.dumps({key: report[key] for key in keys}, indent=2))
