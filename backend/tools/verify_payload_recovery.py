"""One retained paired batch: cold payload recovery through scientific certification.

This offline pilot cannot acquire data, use a database, or select a larger
corpus. Original source trees remain read-only. Recovered relative paths and
source identities are unchanged; all derived bytes must match the retained
official certification, not a newly chosen scientific policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

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
from physics_atlas_api.storage import FilesystemArtifactStore
from physics_atlas_api.storage.historical_read import read_artifact
from physics_atlas_api.storage.payloads import (
    PayloadMetadata,
    archive_payload,
    recover_payload,
)

RAW_HASH = "b715c6f2d81013c4ea1bea632edbfb75ab25fa8d3874df2d4326cc2b532e3322"
ENRICHMENT_HASH = "8880eaf2afd3c6c32fc46f923d56bb6b6626318af8415653d5756d9c15ee539d"
CERTIFICATION_HASH = "e7b99d22e632a30e5b949f4a0165873ecd665b06411984ba3d8a478875bb2729"
DIRECTORIES = {
    "raw": "paired-certification-2020w03-v2-raw-official",
    "enrichment": "paired-certification-2020w03-v2-enrichment-official",
    "certification": "paired-certification-2020w03-v2-certified-official-final",
}


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def write_new(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def manifest_path(root, checksum):
    return root / "manifests" / f"{checksum}.json"


def inventory(raw, enrichment):
    result = []
    for partition in raw["partitions"]:
        for page in partition["pages"]:
            result.append(
                {
                    "tree": "raw",
                    "kind": "provider-page",
                    "path": page["path"],
                    "checksum": page["checksum"],
                    "record_count": page["record_count"],
                    "metadata": PayloadMetadata(
                        provider=partition["provider"],
                        provider_record_id=partition["partition_id"]
                        + ":"
                        + page["checksum"],
                        acquisition_id=RAW_HASH,
                        snapshot_id=page["checksum"],
                        acquisition_scope=partition["scope_id"],
                        dataset_version=raw["manifest_version"],
                        acquired_at=page["http_lineage"]["response_received_at"],
                        status=partition["terminal_status"],
                        media_type="application/json"
                        if partition["provider"] == "inspire"
                        else "application/atom+xml",
                    ),
                }
            )
    seen = set()
    for records in enrichment["records"].values():
        for record in records:
            if record["path"] in seen:
                continue
            seen.add(record["path"])
            result.append(
                {
                    "tree": "enrichment",
                    "kind": "authority-response",
                    "path": record["path"],
                    "checksum": record["checksum"],
                    "record_count": 1,
                    "metadata": PayloadMetadata(
                        provider=record["provider"],
                        provider_record_id=record["source_record_id"],
                        acquisition_id=ENRICHMENT_HASH,
                        snapshot_id=record["checksum"],
                        acquisition_scope=raw["pair_id"],
                        dataset_version=enrichment["manifest_version"],
                        acquired_at=record["http_lineage"]["response_received_at"],
                        status="retained-exact-authority-response",
                        media_type="application/json",
                    ),
                }
            )
    return result


def provenance_recovery(decisions, occurrences, artifact_rows):
    references = {
        canonical_json(reference): reference
        for decision in decisions
        for reference in decision["evidence"]
    }
    artifacts = {row["path"]: row for row in artifact_rows if row["kind"] != "manifest"}
    paper_references = {
        canonical_json(asdict(item.page_reference)) for item in occurrences
    }
    authority_count = 0
    for encoded, reference in references.items():
        path, separator, _fragment = reference["storage_reference"].partition("#")
        artifact = artifacts[path]
        if not (
            reference["checksum"] == artifact["checksum"]
            and reference["source_snapshot_id"] == artifact["checksum"]
        ):
            raise ValueError("provenance snapshot/checksum changed")
        if separator:
            if encoded not in paper_references:
                raise ValueError("paper reference does not recover its parsed record")
        else:
            metadata = artifact["reference"]["metadata"]
            if not (
                reference["provider"] == metadata["provider"]
                and reference["source_record_id"] == metadata["provider_record_id"]
            ):
                raise ValueError("authority source identity differs")
            authority_count += 1
    return {
        "reference_occurrences": sum(len(row["evidence"]) for row in decisions),
        "unique_references": len(references),
        "parsed_paper_references": len(paper_references),
        "authority_references": authority_count,
        "unresolved_references": 0,
    }


def run_pilot(evidence: Path, output: Path):
    require_validation_runtime()
    roots = {key: evidence.resolve() / value for key, value in DIRECTORIES.items()}
    output = validate_staging_output(output)
    if any(
        output.is_relative_to(root) or root.is_relative_to(output)
        for root in roots.values()
    ):
        raise ValueError("pilot output cannot overlap retained inputs")
    raw_path = manifest_path(roots["raw"], RAW_HASH)
    enrichment_path = manifest_path(roots["enrichment"], ENRICHMENT_HASH)
    original_manifest_path = manifest_path(roots["certification"], CERTIFICATION_HASH)
    raw = verify_paired_capture_manifest(raw_path, output=roots["raw"])
    enrichment = verify_paired_enrichment_manifest(
        enrichment_path, output=roots["enrichment"], paired_manifest_path=raw_path
    )
    if (
        raw["manifest_checksum"] != RAW_HASH
        or enrichment["manifest_checksum"] != ENRICHMENT_HASH
    ):
        raise ValueError("pilot accepts only the fixed existing official paired batch")
    original_occurrences = _load_occurrences(roots["raw"], raw)
    original_papers = _canonicalize(original_occurrences)
    if len(original_occurrences) != 635 or len(original_papers) != 474:
        raise ValueError("pilot is restricted to 635 occurrences and 474 components")
    output.mkdir(parents=True, exist_ok=False)
    store = FilesystemArtifactStore(output / "cold-artifacts")
    rows = inventory(raw, enrichment)
    for tree, manifest, checksum in (
        ("raw", raw, RAW_HASH),
        ("enrichment", enrichment, ENRICHMENT_HASH),
    ):
        path = manifest_path(roots[tree], checksum)
        rows.append(
            {
                "tree": tree,
                "kind": "manifest",
                "path": path.relative_to(roots[tree]).as_posix(),
                "checksum": sha256(path.read_bytes()),
                "record_count": None,
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
    catalog = []
    for row in rows:
        source = roots[row["tree"]] / row["path"]
        payload = source.read_bytes()
        if sha256(payload) != row["checksum"]:
            raise ValueError("retained payload integrity failed")
        reference = archive_payload(payload, row["metadata"], store)
        recovered = recover_payload(reference, store)
        if recovered != payload:
            raise ValueError("payload recovery is not byte-identical")
        write_new(output / "restored" / row["tree"] / row["path"], recovered)
        catalog.append(
            {key: value for key, value in row.items() if key != "metadata"}
            | {"reference": asdict(reference)}
        )
    write_new(output / "payload-catalog.json", canonical_json(catalog) + b"\n")
    restored_raw = output / "restored" / "raw"
    restored_enrichment = output / "restored" / "enrichment"
    restored_manifest = verify_paired_capture_manifest(
        manifest_path(restored_raw, RAW_HASH), output=restored_raw
    )
    recovered_occurrences = _load_occurrences(restored_raw, restored_manifest)
    if original_occurrences != recovered_occurrences:
        raise ValueError("source parsing/normalization/source identity changed")
    if original_papers != _canonicalize(recovered_occurrences):
        raise ValueError("canonical paper identity changed")
    generated, generated_path = certify_paired_trial(
        raw_root=restored_raw,
        raw_manifest_path=manifest_path(restored_raw, RAW_HASH),
        enrichment_root=restored_enrichment,
        enrichment_manifest_path=manifest_path(restored_enrichment, ENRICHMENT_HASH),
        output=output / "recovered-certification",
    )
    if generated_path.read_bytes() != original_manifest_path.read_bytes():
        raise ValueError("recovered certification manifest differs")
    artifact_results = []
    for entry in generated["artifacts"]:
        before = read_artifact(roots["certification"], entry)
        after = read_artifact(output / "recovered-certification", entry)
        if before != after or sha256(after) != entry["checksum"]:
            raise ValueError("scientific output differs from retained certification")
        artifact_results.append(entry | {"byte_identical": True})
    decision_entry = next(row for row in artifact_results if row["role"] == "decisions")
    decisions = [
        json.loads(line)
        for line in (output / "recovered-certification" / decision_entry["path"])
        .read_bytes()
        .splitlines()
    ]
    summary = {
        "pilot_version": "payload-reference-recovery-pilot-v1",
        "measured_at": datetime.now(UTC).isoformat(),
        "raw_manifest_checksum": RAW_HASH,
        "enrichment_manifest_checksum": ENRICHMENT_HASH,
        "certification_manifest_checksum": CERTIFICATION_HASH,
        "source_occurrences": len(original_occurrences),
        "canonical_papers": len(original_papers),
        "provider_occurrences": dict(
            Counter(row.provider for row in original_occurrences)
        ),
        "source_normalization_digest": sha256(
            canonical_json([asdict(row) for row in original_occurrences])
        ),
        "source_normalization_equal": True,
        "canonicalization_equal": True,
        "decision_count": len(decisions),
        "decision_states": dict(Counter(row["state"] for row in decisions)),
        "all_ten_artifacts_byte_identical": len(artifact_results) == 10,
        "artifacts": artifact_results,
        "provenance": provenance_recovery(decisions, recovered_occurrences, catalog),
        "payload_classes": {
            kind: {
                "objects": len(
                    selected := [row for row in catalog if row["kind"] == kind]
                ),
                "original_bytes": sum(
                    row["reference"]["payload_size_bytes"] for row in selected
                ),
                "cold_bytes": sum(
                    row["reference"]["artifact"]["size_bytes"] for row in selected
                ),
            }
            for kind in ("provider-page", "authority-response", "manifest")
        },
        "network_access": False,
        "database_access": False,
        "production_mutations": False,
        "metric_observations_created": generated["metric_observations_created"],
        "certified_complete_year_count": generated["certified_complete_year_count"],
        "certified_metric_window_count": generated["certified_metric_window_count"],
    }
    write_new(output / "recovery-report.json", canonical_json(summary) + b"\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run_pilot(arguments.evidence, arguments.output), indent=2))


if __name__ == "__main__":
    main()
