"""Tiny generated normalized fixtures; no provider/researcher evidence or replay."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from physics_atlas_api.certification import CertificationError

TOOLS = Path(__file__).resolve().parents[1] / "tools"
SPEC = importlib.util.spec_from_file_location(
    "sample_tool", TOOLS / "pin_validation_sample.py"
)
assert SPEC is not None and SPEC.loader is not None
sample = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sample)


def write_artifact(root, role, rows):
    body = b"".join(sample.encoded(row) + b"\n" for row in rows)
    sha = hashlib.sha256(body).hexdigest()
    path = root / "artifacts" / role / f"{sha}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {
        "role": role,
        "checksum": sha,
        "byte_count": len(body),
        "row_count": len(rows),
        "path": path.relative_to(root).as_posix(),
    }


def write_manifest(root, kind, artifacts):
    value = {"artifacts": artifacts, "metric_observations_created": 0}
    if kind == "paired":
        value.update(
            manifest_version="physics-paired-trial-certification-manifest-v2",
            projection_pipeline_version="fixture-paired-v2",
        )
        key = "manifest_checksum"
    else:
        value.update(
            acquisition_scope="cond-mat-validation-v1",
            replay_version="fixture-replay-v2",
        )
        key = "bundle_manifest_checksum"
    value[key] = sample.checksum(value)
    path = root / "manifests" / (value[key] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sample.encoded(value))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "test")
    paired = tmp_path / "paired"
    artifacts = [
        write_artifact(
            paired,
            "canonical-papers",
            [
                {
                    "canonical_paper_id": f"paired-{i}",
                    "strong_identifiers": [{"scheme": "doi", "value": f"10.test/{i}"}],
                    "source_scopes": ["hep-th" if i % 2 else "cond-mat"],
                    "eligible_for_metrics": False,
                }
                for i in range(474)
            ],
        )
    ]
    values = {
        "decisions": [
            {"state": state}
            for state in (
                "certified",
                "needs_review",
                "conflicted",
                "insufficient_evidence",
            )
        ],
        "affiliation-shares": [
            {
                "paper_time_affiliation_state": "certified",
                "institution_state": "needs_review",
            }
        ],
        "field-ledgers": [{"assignments": [1, 2], "provider_disagreement": True}],
        "citation-observations": [
            {"non_self_citation_count": value} for value in (0, None, 4)
        ],
    }
    artifacts.extend(
        write_artifact(paired, role, rows) for role, rows in values.items()
    )
    p, psha = write_manifest(paired, "paired", artifacts)
    rows = [
        {
            "candidate_id": f"replay-{i}",
            "occurrences": [
                {"identifiers": [{"scheme": "doi", "value": f"10.test/{i}"}]}
            ],
            "source_lineage": [
                {
                    "acquisition_year": 2020 + i % 6,
                    "provider": "inspire" if i % 3 else "arxiv",
                }
            ],
            "status": "needs_review" if i % 7 else "matched",
            "conflict_schemes": ["doi"] if i % 19 == 0 else [],
        }
        for i in range(1100)
    ]
    replay = tmp_path / "replay"
    r, rsha = write_manifest(
        replay, "replay", [write_artifact(replay, "paper-components", rows)]
    )
    return {
        "root": tmp_path,
        "paired_manifest": p.relative_to(tmp_path).as_posix(),
        "paired_sha256": psha,
        "replay_manifest": r.relative_to(tmp_path).as_posix(),
        "replay_sha256": rsha,
    }


def test_stable_identity_exact_reuse_and_source_separation(inputs, tmp_path):
    first = sample.build_sample(**inputs)
    second = sample.build_sample(**inputs)
    assert first == second
    assert first["paper_reference_count"] == 1000
    assert first["paired_count"] == 474
    assert first["corrected_replay_count"] == 526
    assert first["excluded_cross_source_strong_id_overlap_count"] == 474
    assert first["coverage"]["decisions"]["state:conflicted"] == 1
    assert first["coverage"]["citation-observations"] == {
        "non_self:missing": 1,
        "non_self:zero": 1,
        "non_self:positive": 1,
    }
    assert first["scientific_processing_performed"] is False
    assert first["metric_activation_authorized"] is False
    assert set(first["sources"]) == {"paired-v2", "cond-mat-corrected-v2"}
    output = tmp_path / "sample.json"
    assert sample.pin_sample(first, output) == "created"
    assert sample.pin_sample(second, output) == "verified-reuse"
    # Exact source row bytes remain independently recoverable by offset/hash.
    for member in first["members"]:
        path = (
            inputs["root"]
            / first["sources"][member["source"]]["artifacts"][member["role"]]["path"]
        )
        with path.open("rb") as stream:
            stream.seek(member["byte_offset"])
            body = stream.read(member["byte_count"])
        assert hashlib.sha256(body).hexdigest() == member["row_sha256"]


@pytest.mark.parametrize("target", [None, True, 0, 999, 2501, 1_000_000])
def test_unbounded_or_too_small_selection_refuses_before_reads(target, tmp_path):
    with pytest.raises(sample.SampleError, match="1000..2500"):
        sample.build_sample(
            root=tmp_path,
            paired_manifest="missing",
            paired_sha256="x",
            replay_manifest="missing",
            replay_sha256="x",
            target=target,
        )


def test_changed_source_and_manifest_refuse(inputs):
    changed = dict(inputs, paired_sha256="0" * 64)
    with pytest.raises(sample.SampleError, match="manifest checksum"):
        sample.build_sample(**changed)
    path = next((inputs["root"] / "replay/artifacts/paper-components").iterdir())
    body = path.read_bytes()
    path.write_bytes(body.replace(b"replay-0", b"replaz-0", 1))
    with pytest.raises(sample.SampleError, match="source integrity"):
        sample.build_sample(**inputs)


def test_replacement_is_not_silent(inputs, tmp_path):
    value = sample.build_sample(**inputs)
    output = tmp_path / "sample.json"
    sample.pin_sample(value, output)
    other = {**value, "metric_activation_authorized": True}
    with pytest.raises(sample.SampleError, match="identity mismatch"):
        sample.pin_sample(other, output)
    other = {**value, "selection_policy": "reviewed replacement still required"}
    other["sample_id"] = sample.checksum(
        {key: item for key, item in other.items() if key != "sample_id"}
    )
    with pytest.raises(sample.SampleError, match="replacement requires review"):
        sample.pin_sample(other, output)


def test_production_refuses_before_source_reads(inputs, monkeypatch):
    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "production")
    with pytest.raises(
        CertificationError, match="(forbidden in production|invalid runtime)"
    ):
        sample.build_sample(**inputs)


def test_symlink_and_traversal_refuse(inputs):
    with pytest.raises(sample.SampleError, match="relative and contained"):
        sample.build_sample(**dict(inputs, paired_manifest="../outside.json"))
    original = inputs["root"] / inputs["paired_manifest"]
    link = inputs["root"] / "linked.json"
    link.symlink_to(original)
    with pytest.raises(sample.SampleError, match="symlink"):
        sample.build_sample(**dict(inputs, paired_manifest="linked.json"))


def test_only_normalized_allowed_roles_are_opened(inputs, monkeypatch):
    original = Path.open
    forbidden = ("source-rows", "researcher-appearances", "/pages/", "authority-rows")

    def guarded(path, *args, **kwargs):
        assert not any(text in path.as_posix() for text in forbidden)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    sample.build_sample(**inputs)


def test_paired_decision_caps_cannot_be_bypassed(inputs):
    root = inputs["root"] / "paired"
    manifest = json.loads((inputs["root"] / inputs["paired_manifest"]).read_bytes())
    next(row for row in manifest["artifacts"] if row["role"] == "decisions")[
        "row_count"
    ] = 100_001
    path, sha = write_manifest(root, "paired", manifest["artifacts"])
    with pytest.raises(CertificationError, match="decision count exceeds"):
        sample.build_sample(
            **dict(
                inputs,
                paired_manifest=path.relative_to(inputs["root"]).as_posix(),
                paired_sha256=sha,
            )
        )


@pytest.mark.parametrize(
    "changed",
    [
        {"version": "unreviewed-v2"},
        {"paper_reference_count": 2501},
        {"paper_reference_count": True},
        {"paired_count": 473, "corrected_replay_count": 527},
        {"scientific_processing_performed": True},
        {"metric_activation_authorized": True},
    ],
)
def test_rehashed_invalid_sample_cannot_be_pinned(changed, inputs, tmp_path):
    value = {**sample.build_sample(**inputs), **changed}
    value["sample_id"] = sample.checksum(
        {key: item for key, item in value.items() if key != "sample_id"}
    )
    output = tmp_path / "refused" / "sample.json"
    with pytest.raises(sample.SampleError):
        sample.pin_sample(value, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "condition",
    [
        "missing-member",
        "duplicate-identity",
        "duplicate-locator",
        "unknown-source",
        "unknown-role",
        "outside-artifact",
        "invalid-hash",
        "invalid-source-version",
        "invalid-source-path",
    ],
)
def test_rehashed_invalid_references_fail_without_reading_sources(
    condition, inputs, tmp_path, monkeypatch
):
    value = deepcopy(sample.build_sample(**inputs))
    first, second = value["members"][:2]
    if condition == "missing-member":
        value["members"].pop()
    elif condition == "duplicate-identity":
        second["paper_id"] = first["paper_id"]
    elif condition == "duplicate-locator":
        second["row_number"] = first["row_number"]
    elif condition == "unknown-source":
        first["source"] = "another-track"
    elif condition == "unknown-role":
        first["role"] = "provider-captures"
    elif condition == "outside-artifact":
        first["byte_offset"] = sample.MAX_SOURCE_BYTES
    elif condition == "invalid-hash":
        first["row_sha256"] = "invalid"
    elif condition == "invalid-source-version":
        value["sources"]["paired-v2"]["version"] = None
    else:
        value["sources"]["paired-v2"]["manifest_path"] = "../outside.json"
    value["sample_id"] = sample.checksum(
        {key: item for key, item in value.items() if key != "sample_id"}
    )

    def no_read(*_, **__):
        pytest.fail("sample metadata admission must not reopen evidence")

    monkeypatch.setattr(Path, "open", no_read)
    with pytest.raises(sample.SampleError):
        sample.pin_sample(value, tmp_path / "sample.json")


def test_existing_oversized_output_is_not_read_or_replaced(
    inputs, tmp_path, monkeypatch
):
    value = sample.build_sample(**inputs)
    output = tmp_path / "existing-proof"
    output.write_bytes(b"different size")

    def no_read(*_, **__):
        pytest.fail("known different-sized existing output must not be read")

    monkeypatch.setattr(Path, "read_bytes", no_read)
    with pytest.raises(sample.SampleError, match="replacement requires review"):
        sample.pin_sample(value, output)
    assert output.stat().st_size == len(b"different size")
