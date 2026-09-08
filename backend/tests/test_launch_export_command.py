"""Command packaging only: mocks are explicitly NOT positive scientific evidence."""

import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from physics_atlas_api import launch_build, launch_export, launch_pipeline
from physics_atlas_api.certification import CertificationError
from physics_atlas_api.certification.launch_inputs import LaunchCanonicalInputs

NAMES = (
    "manifest.json",
    "atlas-dataset.json",
    "scientific-evidence.json.gz",
    "launch-export-summary.json",
)
GEOGRAPHIC_REFERENCE = (
    Path(__file__).resolve().parents[2] / "src/data/reference/geographic-views.json"
)


@pytest.fixture
def command(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Permit only the pytest scratch root; never open a real checkpoint."""
    prepared = launch_pipeline.PreparedLaunch(
        (), (), LaunchCanonicalInputs((), 0, 0, "explicit-transport-fixture"), (), ()
    )
    calculated = launch_pipeline.CalculatedLaunch(prepared, (), (), (), ())
    result = launch_export.LaunchExport(
        b'{"fixture":"not scientific release evidence"}',
        b'{"fixture":"not scientific dataset"}',
        b"explicit non-scientific transport fixture",
        {
            "fixtureOnly": True,
            "scientificActivationClaim": False,
            "coLocatedFiveMetricGroups": {"country": 1},
            "countryHeatmapPeriods": ["2022", "2023"],
        },
    )
    load = Mock(return_value=calculated)
    build = Mock(return_value=result)
    progress = Mock()
    monkeypatch.setattr(launch_pipeline, "_private_root", lambda root: root)
    monkeypatch.setattr(launch_pipeline, "_load", load)
    monkeypatch.setattr(launch_pipeline, "_progress", progress)
    monkeypatch.setattr(launch_export, "build_launch_export", build)
    return calculated, result, load, build, progress


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("symlink", [False, True])
def test_export_refuses_existing_or_symlink_before_loading(
    tmp_path: Path, command, name: str, symlink: bool
) -> None:  # type: ignore[no-untyped-def]
    _, _, load, build, progress = command
    target = tmp_path / name
    if symlink:
        target.symlink_to(tmp_path / "missing-test-target")
    else:
        target.write_bytes(b"existing-test-artifact-must-not-change")
    with pytest.raises(ValueError, match="already exist; never overwrite"):
        launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    load.assert_not_called()
    build.assert_not_called()
    progress.assert_not_called()
    assert list(tmp_path.iterdir()) == [target]
    if not symlink:
        assert target.read_bytes() == b"existing-test-artifact-must-not-change"


def test_export_rejects_wrong_checkpoint_type(tmp_path: Path, command) -> None:  # type: ignore[no-untyped-def]
    _, _, load, build, _ = command
    load.return_value = {"fixture": "not a typed calculated launch"}
    with pytest.raises(CertificationError, match="actual calculated launch"):
        launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    load.assert_called_once_with(tmp_path, "calculated-launch.pickle.gz")
    build.assert_not_called()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"coLocatedFiveMetricGroups": {}}, "five-metric country"),
        ({"coLocatedFiveMetricGroups": {"country": 0}}, "five-metric country"),
        ({"countryHeatmapPeriods": []}, "historical periods"),
        ({"countryHeatmapPeriods": ["2023"]}, "historical periods"),
    ],
)
def test_export_requires_country_composite_and_real_timeline(
    tmp_path: Path, command, change: dict, reason: str
) -> None:  # type: ignore[no-untyped-def]
    _, result, _, build, progress = command
    build.return_value = replace(result, summary={**result.summary, **change})
    with pytest.raises(CertificationError, match=reason):
        launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    build.assert_called_once()
    progress.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_export_checks_total_budget_before_any_asset_write(
    tmp_path: Path, command, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    _, result, _, _, progress = command
    summary = json.dumps(result.summary, sort_keys=True, separators=(",", ":")).encode()
    required = sum(len(data) for _, _, data in result.assets) + len(summary)
    monkeypatch.setattr(launch_pipeline, "MAX_EPHEMERAL_BYTES", 100_000_000 + required)
    monkeypatch.setattr(launch_pipeline, "_storage_bytes", lambda root: 1)
    write = Mock(side_effect=AssertionError("budget must be checked before writes"))
    monkeypatch.setattr(launch_pipeline, "_publish_checkpoint", write)
    with pytest.raises(RuntimeError, match="budget; not written"):
        launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    write.assert_not_called()
    progress.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_export_rejects_unexpected_asset_inventory(tmp_path: Path, command) -> None:  # type: ignore[no-untyped-def]
    _, result, _, build, _ = command
    build.return_value = SimpleNamespace(
        summary=result.summary,
        assets=(("dataset", "unexpected.json", b"test-only-bytes"),),
    )
    with pytest.raises(CertificationError, match="unexpected final asset inventory"):
        launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    assert not list(tmp_path.iterdir())


def test_export_rejects_unknown_geographic_policy_before_building(
    tmp_path: Path, command, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    _, _, _, build, _ = command
    read = Path.read_text

    def policy(path: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if path.name == "geographic-views.json":
            return '{"version":"explicit-invalid-test-policy"}'
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", policy)
    with pytest.raises(CertificationError, match="unsupported display-only"):
        launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    build.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_export_publishes_exact_three_assets_and_summary_atomically(
    tmp_path: Path, command, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    calculated, result, load, build, progress = command
    link = os.link
    linked: list[str] = []

    def checked_link(source: Path, destination: Path) -> None:
        assert source.parent == destination.parent == tmp_path
        assert source.name.startswith(".page-write-")
        assert source.name.endswith(".tmp")
        assert source.is_file() and not destination.exists()
        linked.append(destination.name)
        link(source, destination)

    monkeypatch.setattr(launch_build.os, "link", checked_link)
    # Reproduce installed-wheel module layout without depending on that layout.
    monkeypatch.setattr(
        launch_pipeline,
        "__file__",
        "/opt/venv/lib/python3.12/site-packages/physics_atlas_api/launch_pipeline.py",
    )
    launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    assert linked == list(NAMES)
    assert {path.name for path in tmp_path.iterdir()} == set(NAMES)
    load.assert_called_once_with(tmp_path, "calculated-launch.pickle.gz")
    build.assert_called_once()
    assert build.call_args.args == (calculated,)
    parameters = build.call_args.kwargs
    assert parameters["generated_at"].utcoffset() is not None
    policy = json.loads(GEOGRAPHIC_REFERENCE.read_text())
    views = parameters["geographic_views"]
    assert [view.id for view in views] == [view["id"] for view in policy["views"]]
    for view, expected in zip(views, policy["views"], strict=True):
        assert view.geometry_iso_numerics == expected["geometryIsoNumerics"]
        assert view.location_country_ids == expected["locationCountryIds"]
        assert view.provenance.version == policy["version"]
        assert view.provenance.source_type == "derived"
    for _, path, content in result.assets:
        assert (tmp_path / path).read_bytes() == content
    assert json.loads((tmp_path / NAMES[3]).read_bytes()) == result.summary
    assert result.summary["scientificActivationClaim"] is False
    progress.assert_called_once_with("final-assets-validated", **result.summary)


def test_main_dispatches_export_only_to_explicit_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = Mock()
    monkeypatch.setattr(launch_pipeline, "export", command)
    monkeypatch.setattr(
        "sys.argv",
        [
            "launch-pipeline",
            "--ephemeral-root",
            str(tmp_path),
            "export",
            "--geographic-reference",
            str(GEOGRAPHIC_REFERENCE),
        ],
    )
    launch_pipeline.main()
    command.assert_called_once_with(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)


def test_export_publishes_only_manifest_declared_shards(tmp_path: Path, command):  # type: ignore[no-untyped-def]
    _, result, _, build, _ = command
    manifest = json.loads(result.manifest_bytes)
    manifest["uiShards"] = {
        "index": {"path": "ui-index.json.gz"},
        "shards": [{"path": "ui-authorships-0000.json.gz"}],
    }
    # Packaging-only fixture; scientific transport integrity is tested separately.
    sharded = replace(
        result,
        manifest_bytes=json.dumps(manifest).encode(),
        ui_assets=(
            ("ui-shard", "ui-authorships-0000.json.gz", b"fixture-relation"),
            ("ui-index", "ui-index.json.gz", b"fixture-index"),
        ),
    )
    build.return_value = sharded
    launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    assert {path.name for path in tmp_path.iterdir()} == {
        *NAMES,
        "ui-index.json.gz",
        "ui-authorships-0000.json.gz",
    }
    for _, path, content in sharded.assets:
        assert (tmp_path / path).read_bytes() == content


@pytest.mark.parametrize("failure", ["unlisted", "existing", "escape"])
def test_extra_shard_guard_precedes_all_writes(tmp_path: Path, command, failure):  # type: ignore[no-untyped-def]
    _, result, _, build, _ = command
    path = "../ui-escape.json.gz" if failure == "escape" else "ui-index.json.gz"
    manifest = json.loads(result.manifest_bytes)
    if failure != "unlisted":
        manifest["uiShards"] = {"index": {"path": path}, "shards": []}
    build.return_value = replace(
        result,
        manifest_bytes=json.dumps(manifest).encode(),
        ui_assets=(("ui-index", path, b"fixture-index"),),
    )
    if failure == "existing":
        (tmp_path / path).write_bytes(b"retained-existing-fixture")
    with pytest.raises((CertificationError, ValueError)):
        launch_pipeline.export(tmp_path, geographic_reference=GEOGRAPHIC_REFERENCE)
    assert {item.name for item in tmp_path.iterdir()} == (
        {path} if failure == "existing" else set()
    )


def test_export_cli_requires_explicit_reference_before_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    command = Mock()
    monkeypatch.setattr(launch_pipeline, "export", command)
    monkeypatch.setattr(
        "sys.argv", ["launch-pipeline", "--ephemeral-root", str(tmp_path), "export"]
    )
    with pytest.raises(SystemExit) as error:
        launch_pipeline.main()
    assert error.value.code == 2
    assert "requires --geographic-reference" in capsys.readouterr().err
    command.assert_not_called()
