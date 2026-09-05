"""One pinned affiliation authority proof under externally enforced OS denial.

This runner reads an isolated copied kit only. The existing compatibility reader
invokes the existing authority resolver; no second resolver, scientific replay or
certification calculation is introduced. Each binding is restored sequentially,
compared through aggregate byte/semantic hashes, and removed by resolver cleanup.
The sole persistent output is a bounded receipt, never another decision ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from physics_atlas_api.certification.validation_artifacts import (
    require_validation_runtime,
)
from physics_atlas_api.storage import affiliation_archive as codec
from physics_atlas_api.storage import historical_authority as authority
from physics_atlas_api.storage import historical_read as reader

VERSION = "affiliation-archive-isolated-proof-v1"
MAX_PLAN_BYTES = 1024**2
MAX_BINDINGS = 32
_PLAN_KEYS = {
    "version",
    "descriptor_path",
    "descriptor_sha256",
    "storage_root",
    "bindings",
    "expected_scientific_summary",
    "denied_paths",
}
_BINDING_KEYS = {
    "bundle_root",
    "manifest_path",
    "manifest_sha256",
    "historical_recorded_path",
    "original_path",
    "entry",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _inside(kit: Path, reference: object) -> Path:
    require(
        isinstance(reference, str)
        and bool(reference)
        and reference.strip() == reference
        and not Path(reference).is_absolute()
        and ".." not in reference.split("/")
        and "\\" not in reference
        and ":" not in reference,
        "proof kit reference must be a contained relative path",
    )
    path = kit / cast(str, reference)
    reader._no_symlinks(path)
    resolved = Path(os.path.abspath(path))
    require(resolved.is_relative_to(kit), "proof reference escapes kit")
    return resolved


def _absolute(value: object) -> str:
    require(
        isinstance(value, str)
        and bool(value)
        and Path(value).is_absolute()
        and str(Path(os.path.abspath(value))) == value,
        "historical control path must be exact and absolute",
    )
    return cast(str, value)


def denied_controls(paths: dict[str, str]) -> dict[str, str]:
    """Attempt open only: never read original bytes, including guard failure."""
    result: dict[str, str] = {}
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


class _Discard:
    def write(self, body: bytes) -> int:
        return len(body)


def _prepare(
    plan: dict[str, Any], kit: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    require(
        set(plan) == _PLAN_KEYS and plan["version"] == VERSION, "invalid proof plan"
    )
    require(
        isinstance(plan["bindings"], list)
        and 1 <= len(plan["bindings"]) <= MAX_BINDINGS,
        "proof requires explicit bounded historical bindings",
    )
    descriptor = _inside(kit, plan["descriptor_path"])
    storage_root = _inside(kit, plan["storage_root"])
    require(storage_root.is_dir(), "proof storage root is absent")
    artifact, selected = authority._descriptor(descriptor, plan["descriptor_sha256"])
    require(
        artifact["type"] in codec.ROLES and selected["type"] == "archive",
        "proof requires authoritative affiliation archive",
    )
    require(
        isinstance(plan["expected_scientific_summary"], dict),
        "proof requires recorded expected summary",
    )
    expected = plan["expected_scientific_summary"]
    require(
        all(expected.get(key) == artifact[key] for key in ("sha256", "bytes", "rows")),
        "expected summary differs from logical artifact",
    )
    # Reject NaN and preserve exact missing/null/zero and Boolean distinctions.
    codec.encoded(expected)
    deny = plan["denied_paths"]
    require(
        isinstance(deny, dict)
        and 1 <= len(deny) <= 64
        and all(isinstance(name, str) and bool(name) for name in deny),
        "proof requires explicit read-denial controls",
    )
    controls = {name: _absolute(path) for name, path in deny.items()}
    seen: set[tuple[str, str]] = set()
    prepared = []
    for number, binding in enumerate(plan["bindings"]):
        require(
            isinstance(binding, dict) and set(binding) == _BINDING_KEYS,
            "invalid proof binding",
        )
        historical_path = _absolute(binding["historical_recorded_path"])
        original_path = _absolute(binding["original_path"])
        manifest_path = _inside(kit, binding["manifest_path"])
        record = authority.affiliation_binding_record(
            manifest_path,
            binding["manifest_sha256"],
            artifact,
            historical_recorded_path=Path(historical_path),
        )
        require(
            codec.encoded(record["entry"]) == codec.encoded(binding["entry"])
            and record["original_path"] == original_path,
            "plan differs from exact immutable historical binding",
        )
        key = (binding["manifest_sha256"], historical_path)
        require(key not in seen, "duplicate proof binding")
        seen.add(key)
        name = f"original_{number:02d}"
        require(name not in controls, "reserved denial-control name")
        controls[name] = original_path
        root = _inside(kit, binding["bundle_root"])
        require(root.is_dir(), "isolated bundle root is absent")
        relative = binding["entry"]["path"]
        entry = reader._entry(root, relative)
        require(entry is not None, "isolated bridge authority index is required")
        assert entry is not None
        required_values = {
            "relative_path": relative,
            "role": artifact["type"],
            "checksum": artifact["sha256"],
            "byte_count": artifact["bytes"],
            "row_count": artifact["rows"],
            "descriptor_sha256": plan["descriptor_sha256"],
            "historical_manifest_sha256": binding["manifest_sha256"],
            "historical_recorded_path": historical_path,
        }
        require(
            all(
                codec.encoded(entry[name]) == codec.encoded(value)
                for name, value in required_values.items()
            ),
            "bridge index differs from pinned proof plan",
        )
        require(
            reader._reference(root, entry["descriptor_path"]) == descriptor
            and reader._reference(root, entry["storage_root"]) == storage_root
            and reader._reference(root, entry["historical_manifest_path"])
            == manifest_path,
            "bridge references differ from isolated proof kit",
        )
        prepared.append(
            {
                "binding": binding,
                "root": root,
                "manifest": manifest_path,
                "index_path": root / "artifact-authority.json",
                "index_sha256": codec.digest_file(root / "artifact-authority.json")[0],
            }
        )
    return artifact, prepared, controls


def run(
    *, plan_path: Path, plan_sha256: str, kit: Path, output: Path
) -> dict[str, Any]:
    require_validation_runtime()
    require(not os.path.lexists(output), "receipt path must be new")
    reader._no_symlinks(kit)
    kit = Path(os.path.abspath(kit))
    require(kit.is_dir(), "isolated kit must exist")
    plan = authority._read_pinned(plan_path, plan_sha256, MAX_PLAN_BYTES)
    artifact, prepared, control_paths = _prepare(plan, kit)
    controls = denied_controls(control_paths)
    print(json.dumps({"stage": "OS_denial_verified", "controls": controls}), flush=True)
    expected = plan["expected_scientific_summary"]
    proofs = []
    for item in prepared:
        binding, root = item["binding"], item["root"]
        entry = binding["entry"]
        with reader.open_artifact(
            root / entry["path"],
            role=entry["role"],
            checksum=entry["checksum"],
            byte_count=entry["byte_count"],
            row_count=entry["row_count"],
            bundle_root=root,
        ) as stream:
            restored_path = Path(stream.name)
            summary = codec.copy_summarized(
                stream,
                cast(BinaryIO, _Discard()),
                byte_limit=artifact["bytes"],
                role=artifact["type"],
            )
            require(
                codec.encoded(summary) == codec.encoded(expected),
                "exact restored byte/scientific summary differs",
            )
        require(not restored_path.exists(), "temporary expanded file was not cleaned")
        require(
            codec.digest_file(item["manifest"], MAX_PLAN_BYTES)[0]
            == binding["manifest_sha256"]
            and codec.digest_file(item["index_path"], MAX_PLAN_BYTES)[0]
            == item["index_sha256"],
            "historical/authority metadata changed during proof",
        )
        proofs.append(
            {
                "historical_manifest_sha256": binding["manifest_sha256"],
                "historical_recorded_path": binding["historical_recorded_path"],
                "original_path": binding["original_path"],
                "bridge_index_sha256": item["index_sha256"],
                "restored_sha256": summary["sha256"],
                "restored_bytes": summary["bytes"],
                "restored_rows": summary["rows"],
                "exact_expected_byte_hash_equal": True,
                "full_scientific_summary_equal": True,
                "temporary_expanded_file_removed": True,
            }
        )
    receipt = {
        "version": VERSION,
        "result": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "plan_sha256": plan_sha256,
        "descriptor_sha256": plan["descriptor_sha256"],
        "logical_artifact_id": artifact["logical_id"],
        "controls": controls,
        "bindings": proofs,
        "scientific_summary": expected,
        "comparison_method": (
            "exact stored byte SHA-256 and ordered aggregate equivalence"
        ),
        "existing_reader": (
            "historical_read.open_artifact -> existing authority resolver"
        ),
        "scientific_parser_input_byte_identical": True,
        "scientific_policy_changed": False,
        "certification_decisions_regenerated": False,
        "referenced_provider_payloads_revalidated": False,
        "scientific_replay_run": False,
        "metric_observations_created": 0,
        "production_accessed": False,
        "originals_retired": False,
        "independent_host_durability_proven": False,
    }
    body = codec.encoded(receipt) + b"\n"
    require(len(body) <= MAX_PLAN_BYTES, "proof receipt exceeds bounded metadata size")
    with output.open("xb") as stream:
        require(stream.write(body) == len(body), "proof receipt write incomplete")
        stream.flush()
        os.fsync(stream.fileno())
    output.chmod(0o400)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "kit", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    arguments = parser.parse_args()
    result = run(
        plan_path=arguments.plan,
        plan_sha256=arguments.plan_sha256,
        kit=arguments.kit,
        output=arguments.output,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
