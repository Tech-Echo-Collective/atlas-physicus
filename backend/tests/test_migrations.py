from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from physics_atlas_api.config import get_settings


def test_initial_migration_upgrades_and_downgrades(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    database_path = tmp_path / "migration.sqlite"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("PHYSICS_ATLAS_DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))

    command.upgrade(config, "head")
    inspector = inspect(create_engine(database_url))
    tables = set(inspector.get_table_names())
    assert {
        "institutions",
        "researchers",
        "papers",
        "affiliations",
        "metric_observations",
        "source_snapshots",
        "identity_reviews",
        "update_runs",
        "entity_search_terms",
    }.issubset(tables)
    cursor_columns = {
        column["name"] for column in inspector.get_columns("source_cursors")
    }
    assert "scope_version" in cursor_columns

    command.downgrade(config, "base")
    remaining = set(inspect(create_engine(database_url)).get_table_names())
    assert remaining <= {"alembic_version"}
    get_settings.cache_clear()
