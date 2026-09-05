"""Production callers must not invoke offline validation-artifact generators.

Static imports are deliberately distinct from execution: the certification
package exports staging helpers alongside the pure contracts used by metrics.
The worker smoke test uses mocked persistence and transport, never a database,
provider response, retained evidence or actual production service.
"""

import ast
from contextlib import nullcontext
from datetime import UTC, datetime
from importlib.util import resolve_name
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from physics_atlas_api import certification, models, paired_trial_certification, worker
from physics_atlas_api.certification import staging
from physics_atlas_api.config import Settings
from physics_atlas_api.connectors.base import ConnectorBatch, SourceConnector

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
VALIDATION_MODULES = {
    "physics_atlas_api.certification.staging",
    "physics_atlas_api.paired_trial_certification",
    "physics_atlas_api.replay_certification",
    "physics_atlas_api.storage.compact",
}
REPLAY_GENERATORS = {
    "certify_replay_bundle",
    "summarize_replay_bundle",
    "write_replay_certification_bundle",
}
FORBIDDEN_CALLS = {
    f"{module}.{name}"
    for module in (
        "physics_atlas_api.certification",
        "physics_atlas_api.certification.staging",
    )
    for name in REPLAY_GENERATORS
} | {
    "physics_atlas_api.paired_trial_certification.certify_paired_trial",
    "physics_atlas_api.paired_trial_certification.verify_paired_trial_certification_manifest",
    "physics_atlas_api.paired_trial_certification.run",
    "physics_atlas_api.replay_certification.run",
    "physics_atlas_api.storage.compact.compact_decisions",
    "verify_payload_recovery.run_pilot",
    "verify_staging_dual_read.run",
    "verify_staging_dual_read.scientific_result",
    "compact_historical_artifact.create_archive",
    "compact_historical_artifact.restore_archive",
    "resolve_historical_artifact.resolve_historical_artifact",
    "prove_historical_artifact_resolution.run",
}


def _imports(
    tree: ast.AST, module: str, *, package: bool
) -> tuple[set[str], dict[str, str]]:
    dependencies: set[str] = set()
    bindings: dict[str, str] = {}
    parent = module if package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dependencies.add(alias.name)
                bindings[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(node, ast.ImportFrom):
            source = node.module or ""
            if node.level:
                source = resolve_name("." * node.level + source, parent)
            dependencies.add(source)
            for alias in node.names:
                imported = f"{source}.{alias.name}"
                dependencies.add(imported)
                bindings[alias.asname or alias.name] = imported
    return dependencies, bindings


def _qualified(node: ast.expr, bindings: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{_qualified(node.value, bindings)}.{node.attr}"
    return ""


def test_production_import_closure_does_not_invoke_validation_generators() -> None:
    modules: dict[str, Path] = {}
    for path in (SOURCE_ROOT / "physics_atlas_api").rglob("*.py"):
        parts = path.relative_to(SOURCE_ROOT).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules[".".join(parts)] = path
    pending = ["physics_atlas_api.main", "physics_atlas_api.worker"]
    visited: set[str] = set()
    violations: list[str] = []
    while pending:
        module = pending.pop()
        if module in visited or module not in modules:
            continue
        visited.add(module)
        path = modules[module]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        dependencies, bindings = _imports(
            tree, module, package=path.name == "__init__.py"
        )
        for dependency in dependencies:
            if dependency in VALIDATION_MODULES and not (
                module == "physics_atlas_api.certification"
                and dependency == "physics_atlas_api.certification.staging"
            ):
                violations.append(f"{module} imports offline module {dependency}")
            # Importing a submodule executes its parent package initializers too.
            parts = dependency.split(".")
            pending.extend(".".join(parts[:end]) for end in range(1, len(parts) + 1))
        if module in VALIDATION_MODULES:
            # The known staging implementation is loaded by its export shim;
            # its own internal calls are not production execution edges.
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = _qualified(node.func, bindings)
                if target in FORBIDDEN_CALLS:
                    violations.append(f"{module}:{node.lineno} calls {target}")
    assert "physics_atlas_api.updates.engine" in visited
    assert "physics_atlas_api.metrics.recomputation" in visited
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "source",
    [
        "from .certification import summarize_replay_bundle as generate\ngenerate()",
        "from . import paired_trial_certification as audit\n"
        "audit.certify_paired_trial()",
        "import compact_historical_artifact as archive\narchive.restore_archive()",
        "from .storage.compact import compact_decisions as compact\ncompact()",
    ],
)
def test_static_boundary_recognizes_aliased_generator_calls(source: str) -> None:
    tree = ast.parse(source)
    _, bindings = _imports(tree, "physics_atlas_api.worker", package=False)
    targets = {
        _qualified(node.func, bindings)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert targets & FORBIDDEN_CALLS


def test_mocked_production_worker_cycle_has_no_verbose_artifact_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        fixture_mode=False,
        database_url="postgresql+psycopg://unused:unused@invalid/unused",
    )
    monkeypatch.setenv("PHYSICS_ATLAS_ENVIRONMENT", "production")
    monkeypatch.setenv("PHYSICS_ATLAS_FIXTURE_MODE", "false")
    monkeypatch.chdir(tmp_path)
    invoked: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        invoked.append("verbose generator invoked")
        raise AssertionError("production cycle invoked validation artifact generation")

    for module in (certification, staging):
        for name in REPLAY_GENERATORS:
            monkeypatch.setattr(module, name, forbidden)
    for name in (
        "certify_paired_trial",
        "verify_paired_trial_certification_manifest",
    ):
        monkeypatch.setattr(paired_trial_certification, name, forbidden)

    # This mock tracks ORM objects without creating a connection or executing SQL.
    objects: dict[tuple[type, str], object] = {}
    session = MagicMock(spec=Session)

    def remember(value: object) -> None:
        key = getattr(value, "id", None) or getattr(value, "source", None)
        assert isinstance(key, str)
        objects[(type(value), key)] = value

    session.add.side_effect = remember
    session.get.side_effect = lambda model, key: objects.get((model, key))
    session.scalar.return_value = None
    session.bind = None
    transport = MagicMock()
    transport.is_fixture = False
    transport.__enter__.return_value = transport
    connector = MagicMock(spec=SourceConnector)
    connector.provider = "inspire"
    connector.source_version = "unit-test-empty-transport"
    connector.cursor_scope = "hep-th-v1:unit-test-empty"
    connector.dataset_scope = "hep-th-v1"
    connector.transport = transport
    connector.enabled = True
    connector.fetch_updated_records.return_value = ConnectorBatch(
        records=(),
        next_cursor="unit-test-checkpoint",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "build_connectors", lambda *_: {"inspire": connector})
    monkeypatch.setattr(worker, "SessionLocal", lambda: nullcontext(session))
    monkeypatch.setattr(worker, "ensure_reference_data", lambda _: None)

    # Real scheduler and update engine execute against the mocks, not a stub run().
    assert worker.execute_once(source="inspire") == 0
    connector.fetch_updated_records.assert_called_once_with(None, 100)
    assert objects[(models.SourceCursor, "inspire")].cursor == "unit-test-checkpoint"
    runs = [value for value in objects.values() if isinstance(value, models.UpdateRun)]
    assert len(runs) == 1 and runs[0].status == "succeeded"
    assert not any(
        isinstance(value, models.MetricObservation) for value in objects.values()
    )
    assert invoked == []
    assert list(tmp_path.rglob("*")) == []
