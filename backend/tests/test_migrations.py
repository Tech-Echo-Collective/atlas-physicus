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
        "paper_affiliations",
        "metric_system_releases",
    }.issubset(tables)
    cursor_columns = {
        column["name"] for column in inspector.get_columns("source_cursors")
    }
    assert "scope_version" in cursor_columns
    metric_columns = {
        column["name"] for column in inspector.get_columns("metric_observations")
    }
    assert {
        "metric_definition_version",
        "acquisition_scope",
        "raw_value",
        "raw_unit",
        "normalization_method",
        "normalization_parameters",
        "input_count",
        "quality_flags",
    }.issubset(metric_columns)
    metric_unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("metric_observations")
    }
    assert metric_unique_constraints["uq_metric_observations_entity_type"] == (
        "entity_type",
        "entity_id",
        "science_domain_id",
        "field_id",
        "metric_id",
        "period",
        "metric_definition_version",
        "algorithm_version",
        "data_source_version",
        "acquisition_scope",
        "calculation_version",
    )
    metric_check_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("metric_observations")
    }
    assert "ck_metric_observations_reconstruction_metadata" in metric_check_names
    research_field_columns = {
        column["name"] for column in inspector.get_columns("research_fields")
    }
    assert {
        "parent_field_id",
        "aliases",
        "ontology_version",
        "node_kind",
        "is_explorable",
        "display_order",
    }.issubset(research_field_columns)
    paper_field_columns = {
        column["name"] for column in inspector.get_columns("paper_fields")
    }
    assert {
        "weight",
        "classification_role",
        "ontology_version",
        "mapping_rule_version",
        "weighting_policy_version",
        "provider_categories",
        "uncertainty_note",
    }.issubset(paper_field_columns)
    paper_affiliation_columns = {
        column["name"] for column in inspector.get_columns("paper_affiliations")
    }
    assert {
        "paper_id",
        "author_position",
        "institution_id",
        "country_id",
        "attribution_weight",
        "attribution_weight_numerator",
        "attribution_weight_denominator",
        "attribution_policy_version",
        "dataset_version",
        "is_current",
    }.issubset(paper_affiliation_columns)

    command.downgrade(config, "base")
    remaining = set(inspect(create_engine(database_url)).get_table_names())
    assert remaining <= {"alembic_version"}
    get_settings.cache_clear()
