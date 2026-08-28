"""add reconstructable metric observation metadata

Revision ID: 4d6f7a8b9c10
Revises: 79a430f5b6c2
Create Date: 2026-08-29 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4d6f7a8b9c10"
down_revision: str | Sequence[str] | None = "79a430f5b6c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=Text()), "postgresql"
    )
    op.add_column(
        "metric_observations",
        sa.Column(
            "metric_definition_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-v1",
        ),
    )
    op.add_column(
        "metric_observations",
        sa.Column("acquisition_scope", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "metric_observations", sa.Column("raw_value", sa.Float(), nullable=True)
    )
    op.add_column(
        "metric_observations",
        sa.Column("raw_unit", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "metric_observations",
        sa.Column("normalization_method", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "metric_observations",
        sa.Column(
            "normalization_parameters",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "metric_observations", sa.Column("input_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "metric_observations",
        sa.Column(
            "quality_flags",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    with op.batch_alter_table("metric_observations") as batch_op:
        batch_op.drop_constraint(
            op.f("uq_metric_observations_entity_type"), type_="unique"
        )
        batch_op.create_unique_constraint(
            op.f("uq_metric_observations_entity_type"),
            [
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
            ],
            postgresql_nulls_not_distinct=True,
        )
        batch_op.create_check_constraint(
            op.f("ck_metric_observations_reconstruction_metadata"),
            "metric_definition_version = 'legacy-v1' OR "
            "(data_source_version IS NOT NULL AND "
            "acquisition_scope IS NOT NULL AND raw_value IS NOT NULL AND "
            "raw_unit IS NOT NULL AND normalization_method IS NOT NULL AND "
            "input_count IS NOT NULL AND input_count >= 0)",
        )
    op.create_index(
        op.f("ix_metric_observations_acquisition_scope"),
        "metric_observations",
        ["acquisition_scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_metric_observations_acquisition_scope"),
        table_name="metric_observations",
    )
    with op.batch_alter_table("metric_observations") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_metric_observations_reconstruction_metadata"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("uq_metric_observations_entity_type"), type_="unique"
        )
        batch_op.create_unique_constraint(
            op.f("uq_metric_observations_entity_type"),
            [
                "entity_type",
                "entity_id",
                "science_domain_id",
                "field_id",
                "metric_id",
                "period",
                "calculation_version",
            ],
            postgresql_nulls_not_distinct=True,
        )
    op.drop_column("metric_observations", "quality_flags")
    op.drop_column("metric_observations", "input_count")
    op.drop_column("metric_observations", "normalization_parameters")
    op.drop_column("metric_observations", "normalization_method")
    op.drop_column("metric_observations", "raw_unit")
    op.drop_column("metric_observations", "raw_value")
    op.drop_column("metric_observations", "acquisition_scope")
    op.drop_column("metric_observations", "metric_definition_version")
