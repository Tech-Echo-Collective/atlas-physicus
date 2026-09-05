"""Small read-bridge fixtures; never real evidence, replay, DB or network."""

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from physics_atlas_api.storage import historical_read as reader


def write_json(path, value):
    body = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    data = root / "artifacts/affiliation-shares/fixture.jsonl"
    data.parent.mkdir(parents=True)
    body = b'{"missing":null,"zero":0,"eligible":false}\n'
    data.write_bytes(body)
    manifest = root / "manifests/historical.json"
    manifest.parent.mkdir()
    manifest.write_bytes(b'{"historical":"unchanged"}')
    authority = tmp_path / "authority"
    authority.mkdir()
    descriptor = authority / "descriptor.json"
    checksum = hashlib.sha256(body).hexdigest()
    descriptor_sha = write_json(
        descriptor,
        {
            "artifact": {
                "type": "affiliation-shares",
                "sha256": checksum,
                "bytes": len(body),
                "rows": 1,
            },
        },
    )
    entry = {
        "relative_path": data.relative_to(root).as_posix(),
        "role": "affiliation-shares",
        "checksum": checksum,
        "byte_count": len(body),
        "row_count": 1,
        "descriptor_path": "../authority/descriptor.json",
        "descriptor_sha256": descriptor_sha,
        "storage_root": "../authority",
        "historical_manifest_path": "manifests/historical.json",
        "historical_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "historical_recorded_path": str(manifest),
    }
    index = {"version": reader.INDEX_VERSION, "entries": [entry]}
    args = {
        "role": entry["role"],
        "checksum": checksum,
        "byte_count": len(body),
        "row_count": 1,
        "bundle_root": root,
    }
    return root, data, body, index, args


def test_inline_unchanged_without_authority_and_missing_refuses(source):
    _root, data, body, _index, args = source
    with reader.open_artifact(data, **args) as stream:
        assert stream.read() == body
    data.unlink()
    with pytest.raises(FileNotFoundError), reader.open_artifact(data, **args):
        pass


def test_archive_selection_never_opens_original_and_preserves_request(
    source,
    monkeypatch,
    tmp_path,
):
    root, data, body, index, args = source
    write_json(root / "artifact-authority.json", index)
    restored = tmp_path / "isolated.jsonl"
    restored.write_bytes(body)
    calls = []

    @contextmanager
    def resolver(path, **kwargs):
        calls.append((path, kwargs))
        try:
            yield SimpleNamespace(path=restored)
        finally:
            restored.unlink()

    original_open = Path.open

    def deny_original(path, *a, **kw):
        if path == data:
            raise AssertionError("selected archive must not read original")
        return original_open(path, *a, **kw)

    monkeypatch.setattr(reader, "resolve_historical_artifact", resolver)
    monkeypatch.setattr(Path, "open", deny_original)
    with reader.open_artifact(data, **args) as stream:
        assert stream.read() == body
    assert not restored.exists()
    assert calls[0][1]["historical_recorded_path"] == Path(
        index["entries"][0]["historical_recorded_path"]
    )
    assert (
        calls[0][1]["expected_descriptor_sha256"]
        == index["entries"][0]["descriptor_sha256"]
    )


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "duplicate",
        "missing-binding",
        "checksum",
        "bytes",
        "rows",
        "role",
        "historical-root",
        "descriptor-pin",
        "unknown-key",
        "traversal",
        "bad-reference",
    ],
)
def test_invalid_selected_authority_refuses_without_inline_fallback(source, change):
    root, data, _body, index, args = source
    entry = index["entries"][0]
    if change == "version":
        index["version"] = "unrecognized"
    elif change == "duplicate":
        index["entries"].append(dict(entry))
    elif change == "missing-binding":
        entry["relative_path"] = "other.jsonl"
    elif change == "checksum":
        entry["checksum"] = "0" * 64
    elif change == "bytes":
        entry["byte_count"] += 1
    elif change == "rows":
        entry["row_count"] += 1
    elif change == "role":
        entry["role"] = "paper-time-affiliation-shares"
    elif change == "historical-root":
        entry["historical_recorded_path"] = str(root / "../other/manifests/a.json")
    elif change == "descriptor-pin":
        entry["descriptor_sha256"] = "0" * 64
    elif change == "unknown-key":
        entry["guess"] = True
    elif change == "traversal":
        entry["relative_path"] = "../affiliation.jsonl"
    elif change == "bad-reference":
        entry["descriptor_path"] = "https://example.invalid/descriptor"
    write_json(root / "artifact-authority.json", index)
    with pytest.raises(reader.HistoricalReadError), reader.open_artifact(data, **args):
        pytest.fail("invalid authority was admitted")


@pytest.mark.parametrize(
    "damage", ["unavailable", "malformed", "symlink", "duplicate-json"]
)
def test_index_unreadable_never_falls_back(source, damage):
    root, data, _body, _index, args = source
    index_path = root / "artifact-authority.json"
    if damage == "unavailable":
        index_path.mkdir()
    elif damage == "malformed":
        index_path.write_bytes(b"{")
    elif damage == "symlink":
        index_path.symlink_to(root / "absent.json")
    else:
        index_path.write_bytes(b'{"version":"a","version":"b","entries":[]}')
    with pytest.raises(reader.HistoricalReadError), reader.open_artifact(data, **args):
        pass


def test_resolver_failure_does_not_fall_back_to_available_inline(source, monkeypatch):
    root, data, _body, index, args = source
    write_json(root / "artifact-authority.json", index)

    @contextmanager
    def unavailable(*args, **kwargs):
        raise reader.HistoricalReadError("selected archive unavailable")
        yield  # pragma: no cover

    monkeypatch.setattr(reader, "resolve_historical_artifact", unavailable)
    with pytest.raises(reader.HistoricalReadError, match="unavailable"):
        with reader.open_artifact(data, **args):
            pass
    assert data.exists()


def test_boolean_dimensions_cannot_alias_integer_authority(source):
    root, data, _body, index, args = source
    write_json(root / "artifact-authority.json", index)
    args["row_count"] = True
    with pytest.raises(reader.HistoricalReadError, match="integer dimensions"):
        with reader.open_artifact(data, **args):
            pass


def test_other_artifact_roles_do_not_consult_affiliation_authority(source):
    root, data, body, _index, args = source
    (root / "artifact-authority.json").write_bytes(b"invalid")
    args["role"] = "field-ledgers"
    with reader.open_artifact(data, **args) as stream:
        assert stream.read() == body


def test_relocated_kit_keeps_historical_namespace_without_original_io(
    source,
    monkeypatch,
    tmp_path,
):
    root, data, body, index, args = source
    historical_manifest = Path(index["entries"][0]["historical_recorded_path"])
    moved = tmp_path / "relocated-kit"
    root.rename(moved)
    write_json(moved / "artifact-authority.json", index)
    restored = tmp_path / "verified-restored.jsonl"
    restored.write_bytes(body)
    old_stat, old_open = Path.stat, Path.open

    def denied_stat(path, *a, **kw):
        if path.is_relative_to(root):
            raise AssertionError("historical original namespace must not be statted")
        return old_stat(path, *a, **kw)

    def denied_open(path, *a, **kw):
        if path.is_relative_to(root):
            raise AssertionError("historical original namespace must not be opened")
        return old_open(path, *a, **kw)

    @contextmanager
    def resolver(_path, **kwargs):
        assert kwargs["historical_recorded_path"] == historical_manifest
        assert kwargs["certification_manifest"] == moved / "manifests/historical.json"
        yield SimpleNamespace(path=restored)

    monkeypatch.setattr(Path, "stat", denied_stat)
    monkeypatch.setattr(Path, "open", denied_open)
    monkeypatch.setattr(reader, "resolve_historical_artifact", resolver)
    args["bundle_root"] = moved
    with reader.open_artifact(moved / data.relative_to(root), **args) as stream:
        assert stream.read() == body


def test_small_comparison_helper_preserves_exact_bytes(source):
    root, _data, body, index, _args = source
    entry = dict(index["entries"][0])
    entry["path"] = entry["relative_path"]
    assert reader.read_artifact(root, entry) == body
