"""One archive-only resolver proof under externally enforced OS read denial.

No acquisition, replay, certification calculation or original-ledger read. The
caller supplies an isolated kit and pinned metadata. Resolver-owned expanded
output is temporary; the only persistent output of this runner is a small receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path

import compact_historical_artifact as archive
from resolve_historical_artifact import resolve_historical_artifact


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned_json(path, checksum):
    body = archive.read_manifest(path)
    require(
        hashlib.sha256(body).hexdigest() == checksum, "proof metadata hash mismatch"
    )
    return json.loads(body)


def denied_controls(paths):
    """Only attempt opening; never read original bytes, even on guard failure."""
    result = {}
    for name, path in paths.items():
        try:
            handle = os.open(path, os.O_RDONLY)
        except PermissionError:
            result[name] = "OS_permission_denied"
        else:
            os.close(handle)
            raise RuntimeError(f"required OS read denial did not hold: {name}")
    with socket.socket() as connection:
        try:
            connection.connect(("127.0.0.1", 9))
        except PermissionError:
            result["network_connect"] = "OS_permission_denied"
        else:
            raise RuntimeError("required OS network denial did not hold")
    return result


def run(args):
    require(not args.output.exists(), "receipt path must be new")
    prior = pinned_json(args.prior_proof, args.prior_proof_sha256)
    expected = prior["recovery"]["scientific_summary"]
    require(
        expected == prior["compression"]["scientific_summary"],
        "prior original/restore scientific summaries disagree",
    )
    require(
        prior["recovery"]["byte_for_byte_compared"] is True, "prior proof incomplete"
    )
    controls = denied_controls(
        {
            "original_ledger": args.denied_original,
            "original_archive": args.denied_archive,
            "private_database": args.denied_database,
        }
    )
    print(json.dumps({"stage": "OS_denial_verified", "controls": controls}), flush=True)
    manifest_before = hashlib.sha256(
        args.certification_manifest.read_bytes()
    ).hexdigest()
    require(
        manifest_before == args.certification_manifest_sha256,
        "historical certification manifest changed",
    )
    with resolve_historical_artifact(
        args.descriptor,
        expected_descriptor_sha256=args.descriptor_sha256,
        storage_root=args.storage_root,
        certification_manifest=args.certification_manifest,
        expected_certification_manifest_sha256=args.certification_manifest_sha256,
        temp_parent=args.temp_parent,
    ) as resolved:
        require(resolved.representation_type == "archive", "proof selected non-archive")
        require(resolved.scientific_summary == expected, "scientific summaries differ")
        recovered_path = resolved.path
        checksum, byte_count = archive.digest_file(recovered_path)
        require(
            checksum == expected["sha256"] and byte_count == expected["bytes"],
            "independent restored-file digest mismatch",
        )
        receipt = {
            "version": "archive-artifact-resolution-proof-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "controls": controls,
            "descriptor_sha256": args.descriptor_sha256,
            "logical_artifact_id": resolved.logical_artifact_id,
            "representation_id": resolved.representation_id,
            "representation_type": resolved.representation_type,
            "historical_manifest_sha256": manifest_before,
            "prior_proof_sha256": args.prior_proof_sha256,
            "scientific_summary": resolved.scientific_summary,
            "restored_sha256": checksum,
            "restored_bytes": byte_count,
            "temporary_restored_path": str(recovered_path),
            "exact_expected_byte_hash_equal": True,
            "byte_comparison_to_real_original": False,
            "scientific_summary_equal": True,
            "provenance_reference_summary_equal": True,
            "conservation_missing_zero_and_eligibility": (
                "unchanged stored bytes; no recalculation or new eligibility"
            ),
            "referenced_provider_payloads_revalidated": False,
            "scientific_replay_run": False,
            "metric_observations_created": 0,
            "production_accessed": False,
            "original_retired": False,
            "independent_host_durability_proven": False,
        }
    require(not recovered_path.exists(), "temporary expanded file was not cleaned")
    require(
        hashlib.sha256(args.certification_manifest.read_bytes()).hexdigest()
        == manifest_before,
        "historical manifest modified during resolution",
    )
    receipt["temporary_expanded_file_removed"] = True
    archive._publish_json(args.output, receipt)
    print(json.dumps(receipt, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "descriptor",
        "storage-root",
        "certification-manifest",
        "prior-proof",
        "denied-original",
        "denied-archive",
        "denied-database",
        "temp-parent",
        "output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("descriptor", "certification-manifest", "prior-proof"):
        parser.add_argument(f"--{name}-sha256", required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
