"""One existing capture, isolated PostgreSQL only; no production migration.

The inline layout mirrors the current raw/snapshot columns and indexes, not a
copy of production rows. Required normalized attributes/IDs/provenance stay hot.
Only bodies are replaced by page references and exact record checksums. Original
response bytes are cold; provider parsers recover record/author JSON semantics.
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
from benchmark_compact_storage import measurements, totals
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from physics_atlas_api.connectors.base import compact_ids, external_id
from physics_atlas_api.paired_capture import (
    validate_staging_output,
    verify_paired_capture_manifest,
)
from physics_atlas_api.paired_trial_certification import _load_occurrences
from physics_atlas_api.storage import ArtifactRef, FilesystemArtifactStore, StorageTier
from physics_atlas_api.storage.payloads import (
    PayloadMetadata,
    PayloadReference,
    archive_payload,
    recover_payload,
)

DATABASE = "physics_atlas_storage_benchmark"
MANIFEST = "b715c6f2d81013c4ea1bea632edbfb75ab25fa8d3874df2d4326cc2b532e3322"
RAW_DIRECTORY = "paired-certification-2020w03-v2-raw-official"


def encoded(value, *, ascii=False):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=ascii
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def ddl(prefix):
    body = "raw_payload jsonb NOT NULL," if prefix == "inline" else ""
    snapshot_reference = "" if prefix == "inline" else "payload_pages jsonb NOT NULL,"
    record_reference = (
        ""
        if prefix == "inline"
        else "page_id bytea NOT NULL REFERENCES ref_pages(id), "
        "payload_sha256 bytea NOT NULL, payload_bytes bigint NOT NULL,"
    )
    # Fixed identifiers only. Columns/indexes match the deployed raw-state model;
    # no canonical tables or production DDL are touched.
    return f"""
CREATE TABLE {prefix}_snapshots (
 id varchar(240) PRIMARY KEY, source varchar(120) NOT NULL,
 source_version varchar(120) NOT NULL, captured_at timestamptz NOT NULL,
 update_mode varchar(40) NOT NULL, record_count integer NOT NULL,
 previous_snapshot_id varchar(240) REFERENCES {prefix}_snapshots(id),
 content_checksum varchar(128) NOT NULL, storage_reference text,
 {body} {snapshot_reference} provenance jsonb NOT NULL,
 UNIQUE(source,content_checksum));
CREATE INDEX {prefix}_snapshot_source ON {prefix}_snapshots(source);
CREATE TABLE {prefix}_records (
 id varchar(240) PRIMARY KEY, entity_type varchar(80) NOT NULL,
 source varchar(120) NOT NULL, source_record_id varchar(400) NOT NULL,
 source_snapshot_id varchar(240) NOT NULL REFERENCES {prefix}_snapshots(id),
 raw_name text NOT NULL, external_ids jsonb NOT NULL, attributes jsonb NOT NULL,
 {body} {record_reference} ingested_at timestamptz NOT NULL,
 provenance jsonb NOT NULL,
 UNIQUE(source,source_record_id,source_snapshot_id));
CREATE INDEX {prefix}_record_type ON {prefix}_records(entity_type);
CREATE INDEX {prefix}_record_source ON {prefix}_records(source);
CREATE INDEX {prefix}_record_snapshot ON {prefix}_records(source_snapshot_id);
"""


def rows_for_capture(raw_root, manifest):
    snapshots, records, pages = {}, {}, {}
    occurrence_rows = _load_occurrences(raw_root, manifest)
    if len(occurrence_rows) != 635:
        raise ValueError("only the existing 635-occurrence capture is allowed")
    for partition in manifest["partitions"]:
        page_list = partition["pages"]
        payload = []
        for page in page_list:
            body = (raw_root / page["path"]).read_bytes()
            if digest(body) != page["checksum"]:
                raise ValueError("source response checksum mismatch")
            is_json = partition["provider"] == "inspire"
            payload.append(
                {
                    "contentType": "application/json"
                    if is_json
                    else "application/atom+xml",
                    "body": json.loads(body) if is_json else body.decode(),
                }
            )
            pages[page["path"]] = (page, partition, body)
        checksum = digest(
            encoded(
                {"acquisitionScope": partition["query_version"], "payload": payload}
            )
        )
        snapshot_id = f"snapshot-{partition['provider']}-{checksum[:24]}"
        snapshots[partition["partition_id"]] = {
            "id": snapshot_id,
            "source": partition["provider"],
            "source_version": "INSPIRE REST API"
            if partition["provider"] == "inspire"
            else "arXiv Query API Atom 1.0 / submittedDate stream",
            "captured_at": datetime.fromisoformat(
                page_list[-1]["http_lineage"]["response_received_at"]
            ),
            "update_mode": "staging-pilot",
            "record_count": partition["unique_records_seen"],
            "previous_snapshot_id": None,
            "content_checksum": checksum,
            "storage_reference": f"database://source_snapshots/{snapshot_id}",
            "raw_payload": payload,
            "provenance": {
                "source": partition["provider"],
                "sourceType": "external-api",
                "acquisitionScope": partition["scope_id"],
                "queryVersion": partition["query_version"],
                "sourceManifest": MANIFEST,
                "stagingOnly": True,
            },
        }
    for occurrence in occurrence_rows:
        normalized = occurrence.normalized
        snapshot = snapshots[f"{occurrence.scope_id}:{occurrence.provider}"]
        # _apply_record derives raw identity from the source checksum+snapshot,
        # so equal author occurrences in the same snapshot remain deduplicated.
        candidates = [
            (
                "paper",
                normalized.source_record_id,
                normalized.canonical_name,
                normalized.external_ids,
                normalized.attributes,
                normalized.raw,
            )
        ]
        for position, author in enumerate(normalized.attributes.get("authors", []), 1):
            raw = author if isinstance(author, dict) else {"name": str(author)}
            name = str(
                raw.get("full_name")
                or " ".join(
                    str(raw.get(key, "")).strip()
                    for key in ("given", "family")
                    if raw.get(key)
                )
                or raw.get("name")
                or f"Unnamed author {position}"
            ).strip()
            ids = []
            if raw.get("recid") is not None:
                ids.append(("inspire-author", str(raw["recid"])))
            orcid = raw.get("ORCID") or raw.get("orcid")
            if orcid:
                ids.append(("orcid", str(orcid).rstrip("/").rsplit("/", 1)[-1]))
            for item in raw.get("ids", []):
                if not isinstance(item, dict) or not item.get("value"):
                    continue
                scheme = str(item.get("schema", "")).casefold()
                if scheme == "orcid":
                    ids.append(("orcid", str(item["value"])))
                elif scheme in {"inspire bai", "inspire"}:
                    ids.append(("inspire-author", str(item["value"])))
            candidates.append(
                (
                    "researcher",
                    f"{normalized.source_record_id}:author:{position}",
                    name,
                    tuple(dict.fromkeys(ids)),
                    {"aliases": [], "requires_authority": True},
                    raw,
                )
            )
        for kind, source_id, name, ids, attributes, raw in candidates:
            checksum = digest(encoded(raw, ascii=True))
            raw_digest = digest((checksum + snapshot["id"]).encode())[:24]
            raw_id = f"raw-{occurrence.provider}-{raw_digest}"
            records.setdefault(
                raw_id,
                {
                    "id": raw_id,
                    "entity_type": kind,
                    "source": occurrence.provider,
                    "source_record_id": source_id,
                    "source_snapshot_id": snapshot["id"],
                    "raw_name": name,
                    "external_ids": [
                        {"scheme": scheme, "value": value}
                        for scheme, value in compact_ids(
                            *(external_id(scheme, value) for scheme, value in ids)
                        )
                    ],
                    "attributes": attributes,
                    "raw_payload": raw,
                    "ingested_at": occurrence.page_response_received_at,
                    "provenance": {
                        **normalized.provenance,
                        "sourceSnapshotId": snapshot["id"],
                        "retainedPage": asdict(occurrence.page_reference),
                    },
                    "_page_path": occurrence.page_path,
                },
            )
    return snapshots, records, pages


def insert_rows(cursor, relation, rows):
    names = tuple(rows[0])
    cursor.executemany(
        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(relation),
            sql.SQL(",").join(map(sql.Identifier, names)),
            sql.SQL(",").join(sql.Placeholder() for _ in names),
        ),
        [
            tuple(
                Jsonb(row[name]) if isinstance(row[name], (dict, list)) else row[name]
                for name in names
            )
            for row in rows
        ],
    )


def benchmark(evidence, recovered_raw, socket, output):
    output = validate_staging_output(output)
    for source in (evidence.resolve() / RAW_DIRECTORY, recovered_raw.resolve()):
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError("benchmark output must not overlap either input")
    socket = socket.resolve(strict=True)
    if (
        socket.parent != Path("/private/tmp")
        or not socket.name.startswith("physics-atlas-storage.")
        or socket.stat().st_uid != os.getuid()
        or not (socket / ".s.PGSQL.55439").is_socket()
    ):
        raise ValueError("only the owned private benchmark Unix socket is allowed")
    raw_root = evidence / RAW_DIRECTORY
    manifest = verify_paired_capture_manifest(
        raw_root / "manifests" / f"{MANIFEST}.json", output=raw_root
    )
    if manifest["manifest_checksum"] != MANIFEST:
        raise ValueError("wrong bounded source manifest")
    before = rows_for_capture(raw_root, manifest)
    recovered = rows_for_capture(recovered_raw, manifest)
    if before != recovered:
        raise AssertionError("recovered pages change normalized hot/raw rows")
    snapshots, records, pages = before
    output.mkdir(parents=True, exist_ok=False)
    store = FilesystemArtifactStore(output / "cold-store")
    references = {}
    for path, (page, partition, body) in pages.items():
        references[path] = archive_payload(
            body,
            PayloadMetadata(
                provider=partition["provider"],
                provider_record_id=path,
                acquisition_id=manifest["pair_id"],
                snapshot_id=page["checksum"],
                acquisition_scope=partition["scope_id"],
                dataset_version=MANIFEST,
                acquired_at=page["http_lineage"]["response_received_at"],
                status="complete",
                media_type="application/json"
                if partition["provider"] == "inspire"
                else "application/atom+xml",
            ),
            store,
        )
    inline_snapshots = list(snapshots.values())
    ref_snapshots = []
    for partition in manifest["partitions"]:
        row = dict(snapshots[partition["partition_id"]])
        row.pop("raw_payload")
        row["payload_pages"] = [page["checksum"] for page in partition["pages"]]
        ref_snapshots.append(row)
    inline_records, ref_records = [], []
    for raw in records.values():
        row = dict(raw)
        path = row.pop("_page_path")
        inline_records.append(dict(row))
        payload = encoded(row.pop("raw_payload"), ascii=True)
        row.update(
            page_id=bytes.fromhex(references[path].payload_sha256),
            payload_sha256=hashlib.sha256(payload).digest(),
            payload_bytes=len(payload),
        )
        ref_records.append(row)
    schema = "payload_bench_" + uuid.uuid4().hex[:12]
    with psycopg.connect(host=str(socket), port=55439, dbname=DATABASE) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(),version(),inet_server_addr()")
            database, server, address = cursor.fetchone()
            if database != DATABASE or address is not None:
                raise ValueError("network/production database is not permitted")
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            cursor.execute(
                sql.SQL("SET search_path TO {},pg_catalog").format(
                    sql.Identifier(schema)
                )
            )
            cursor.execute(
                "CREATE TABLE ref_pages(id bytea PRIMARY KEY, reference jsonb NOT NULL)"
            )
            cursor.execute(ddl("inline") + ddl("ref"))
            empty = measurements(connection, schema)
            insert_rows(
                cursor,
                "ref_pages",
                [
                    {"id": bytes.fromhex(ref.payload_sha256), "reference": asdict(ref)}
                    for ref in references.values()
                ],
            )
            for table, rows in (
                ("inline_snapshots", inline_snapshots),
                ("ref_snapshots", ref_snapshots),
                ("inline_records", inline_records),
                ("ref_records", ref_records),
            ):
                insert_rows(cursor, table, rows)
        connection.commit()
        with connection.cursor(row_factory=dict_row) as cursor:
            for row in empty["relations"]:
                cursor.execute(
                    sql.SQL("ANALYZE {}").format(sql.Identifier(row["relation"]))
                )
            physical = measurements(connection, schema)
            cursor.execute("SELECT * FROM ref_pages ORDER BY id")
            sql_pages = {}
            sql_restored = output / "sql-restored-raw"
            for row in cursor.fetchall():
                value = row["reference"]
                value["metadata"] = PayloadMetadata(**value["metadata"])
                value["artifact"]["tier"] = StorageTier(value["artifact"]["tier"])
                value["artifact"] = ArtifactRef(**value["artifact"])
                ref = PayloadReference(**value)
                body = recover_payload(ref, store)
                assert digest(body) == bytes(row["id"]).hex()
                assert body == pages[ref.metadata.provider_record_id][2]
                sql_pages[bytes(row["id"])] = body
                target = sql_restored / ref.metadata.provider_record_id
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(body)
            sql_reparsed = rows_for_capture(sql_restored, manifest)
            assert sql_reparsed == before
            # Use SQL-recovered, re-parsed paper/author fragments below, not the
            # original inline JSON. Locator, content digest and metadata all agree.
            sql_records = sql_reparsed[1]
            cursor.execute("SELECT * FROM ref_records ORDER BY id")
            for row in cursor.fetchall():
                original = dict(sql_records[row["id"]])
                path = original.pop("_page_path")
                payload = original.pop("raw_payload")
                assert bytes(row.pop("page_id")) == bytes.fromhex(
                    references[path].payload_sha256
                )
                assert (
                    bytes(row.pop("payload_sha256"))
                    == hashlib.sha256(encoded(payload, ascii=True)).digest()
                )
                assert row.pop("payload_bytes") == len(encoded(payload, ascii=True))
                assert row == original
            for table, expected in (
                ("inline_records", inline_records),
                ("inline_snapshots", inline_snapshots),
            ):
                cursor.execute(
                    sql.SQL("SELECT * FROM {} ORDER BY id").format(
                        sql.Identifier(table)
                    )
                )
                assert cursor.fetchall() == sorted(
                    expected, key=lambda item: item["id"]
                )
            cursor.execute("SELECT * FROM ref_snapshots ORDER BY id")
            for row in cursor.fetchall():
                original = next(
                    dict(item) for item in inline_snapshots if item["id"] == row["id"]
                )
                payload = original.pop("raw_payload")
                rebuilt = [
                    {
                        "contentType": "application/json"
                        if row["source"] == "inspire"
                        else "application/atom+xml",
                        "body": json.loads(sql_pages[bytes.fromhex(key)])
                        if row["source"] == "inspire"
                        else sql_pages[bytes.fromhex(key)].decode(),
                    }
                    for key in row.pop("payload_pages")
                ]
                assert rebuilt == payload and row == original
            cursor.execute(
                "SELECT sum(pg_column_size(raw_payload))::bigint AS bytes "
                "FROM inline_records"
            )
            record_datums = cursor.fetchone()["bytes"]
            cursor.execute(
                "SELECT sum(pg_column_size(raw_payload))::bigint AS bytes "
                "FROM inline_snapshots"
            )
            snapshot_datums = cursor.fetchone()["bytes"]
        connection.commit()
    result = {
        "version": "bounded-payload-reference-postgres-pilot-v1",
        "measured_at": datetime.now(UTC).isoformat(),
        "server": server,
        "schema": schema,
        "source_manifest": MANIFEST,
        "papers": 474,
        "provider_occurrences": 635,
        "raw_records": len(records),
        "snapshots": len(snapshots),
        "record_counts": dict(
            Counter(f"{r['source']}:{r['entity_type']}" for r in records.values())
        ),
        "response_bytes": sum(len(page[2]) for page in pages.values()),
        "record_json_bytes": sum(
            len(encoded(r["raw_payload"], ascii=True)) for r in records.values()
        ),
        "snapshot_json_bytes": sum(
            len(encoded(r["raw_payload"])) for r in snapshots.values()
        ),
        "stored_payload_datums": {
            "records": record_datums,
            "snapshots": snapshot_datums,
        },
        "cold_raw_bytes": sum(ref.artifact.size_bytes for ref in references.values()),
        "inline": totals(physical, "inline_", 474, 635),
        "reference": totals(physical, "ref_", 474, 635),
        "physical": physical,
        "empty": empty,
        "all_normalized_rows_equal": True,
        "sql_record_metadata_equal": True,
        "sql_snapshot_semantics_equal": True,
        "sql_recovered_pages_byte_equal": True,
        "sql_reparsed_records_equal": True,
        "sql_verified_record_locators": len(records),
        "production_writes": False,
    }
    for key in ("inline", "reference"):
        result[key]["bytes_per_provider_occurrence"] = result[key].pop(
            "bytes_per_decision"
        )
    (output / "measurement.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    (output / "payload-references.json").write_text(
        json.dumps(
            {path: asdict(ref) for path, ref in references.items()},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--recovered-raw", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = benchmark(
        arguments.evidence, arguments.recovered_raw, arguments.socket, arguments.output
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("inline", "reference", "raw_records", "cold_raw_bytes")
            },
            indent=2,
        )
    )
