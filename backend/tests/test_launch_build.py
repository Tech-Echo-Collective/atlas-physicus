"""Offline launch owner guards; no providers, production or scientific replay."""

import gzip
import pickle
from pathlib import Path

import pytest

from physics_atlas_api import launch_build


def test_checkpoint_roundtrip_and_refuses_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "checkpoint.pickle.gz"
    value = {"synthetic-test-only": tuple(range(100))}
    size = launch_build._write_checkpoint(tmp_path, destination, value)
    assert size == destination.stat().st_size
    with gzip.open(destination, "rb") as stream:
        assert pickle.load(stream) == value  # noqa: S301 -- own test output only
    with pytest.raises(ValueError, match="must be new"):
        launch_build._write_checkpoint(tmp_path, destination, value)


def test_checkpoint_budget_is_checked_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "checkpoint.pickle.gz"
    monkeypatch.setattr(launch_build, "MAX_EPHEMERAL_BYTES", 100_000_001)
    with pytest.raises(RuntimeError, match="not written"):
        launch_build._write_checkpoint(tmp_path, destination, {"fixture": "value"})
    assert not destination.exists()


def test_checkpoint_cannot_escape_explicit_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inside"):
        launch_build._write_checkpoint(tmp_path, tmp_path.parent / "escaped", {})


def test_network_origin_guard_rejects_unapproved_or_cleartext() -> None:
    transport = launch_build.LaunchTransport()
    try:
        for url in ("http://inspirehep.net/api", "https://example.invalid/api"):
            with pytest.raises(ValueError, match="unapproved"):
                transport.fetch(url)
    finally:
        transport.client.close()


def test_collection_cannot_use_arbitrary_workspace(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit isolated"):
        launch_build.collect(root=tmp_path, years=(2018,), dataset_version="test")
