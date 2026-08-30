"""add Metric System v1 scientific attribution foundation

Revision ID: 9f4a2c7d8e10
Revises: 4d6f7a8b9c10
Create Date: 2026-08-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9f4a2c7d8e10"
down_revision: str | Sequence[str] | None = "4d6f7a8b9c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.JSON:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")


def upgrade() -> None:
    json_type = _json_type()

    with op.batch_alter_table("research_fields") as batch_op:
        batch_op.add_column(
            sa.Column("parent_field_id", sa.String(length=120), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "aliases", json_type, nullable=False, server_default=sa.text("'[]'")
            )
        )
        batch_op.add_column(
            sa.Column(
                "ontology_version",
                sa.String(length=120),
                nullable=False,
                server_default="legacy-flat-physics-fields-v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "node_kind",
                sa.String(length=40),
                nullable=False,
                server_default="field",
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_explorable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_foreign_key(
            op.f("fk_research_fields_parent_field_id_research_fields"),
            "research_fields",
            ["parent_field_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            op.f("ck_research_fields_research_field_not_own_parent"),
            "parent_field_id IS NULL OR parent_field_id != id",
        )
        batch_op.create_check_constraint(
            op.f("ck_research_fields_research_field_node_kind"),
            "node_kind IN ('domain-root', 'branch', 'field')",
        )
        batch_op.create_check_constraint(
            op.f("ck_research_fields_research_field_display_order"),
            "display_order >= 0",
        )
    op.create_index(
        op.f("ix_research_fields_parent_field_id"),
        "research_fields",
        ["parent_field_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_research_fields_ontology_version"),
        "research_fields",
        ["ontology_version"],
        unique=False,
    )

    op.add_column("papers", sa.Column("publication_date", sa.Date(), nullable=True))
    op.add_column(
        "papers",
        sa.Column("publication_date_precision", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column(
            "document_type",
            sa.String(length=80),
            nullable=False,
            server_default="article",
        ),
    )

    with op.batch_alter_table("paper_fields") as batch_op:
        batch_op.add_column(
            sa.Column(
                "weight",
                sa.Numeric(precision=14, scale=12),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "classification_role",
                sa.String(length=40),
                nullable=False,
                server_default="unspecified",
            )
        )
        batch_op.add_column(
            sa.Column(
                "ontology_version",
                sa.String(length=120),
                nullable=False,
                server_default="legacy-flat-physics-fields-v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "mapping_rule_version",
                sa.String(length=120),
                nullable=False,
                server_default="provider-category-rules-v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "weighting_policy_version",
                sa.String(length=120),
                nullable=False,
                server_default="legacy-full-membership-v1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "provider_categories",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(sa.Column("uncertainty_note", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_paper_fields_paper_field_weight"),
            "weight > 0 AND weight <= 1",
        )
        batch_op.create_check_constraint(
            op.f("ck_paper_fields_paper_field_classification_role"),
            "classification_role IN ('primary', 'secondary', 'mixed', 'unspecified')",
        )
    op.create_index(
        op.f("ix_paper_fields_ontology_version"),
        "paper_fields",
        ["ontology_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_paper_fields_mapping_rule_version"),
        "paper_fields",
        ["mapping_rule_version"],
        unique=False,
    )

    op.create_table(
        "metric_system_releases",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("metric_ids", json_type, nullable=False),
        sa.Column("algorithm_versions", json_type, nullable=False),
        sa.Column("attribution_policy_version", sa.String(length=160), nullable=False),
        sa.Column("ontology_version", sa.String(length=160), nullable=False),
        sa.Column("mapping_policy_version", sa.String(length=160), nullable=False),
        sa.Column("threshold_version", sa.String(length=160), nullable=False),
        sa.Column(
            "validation_evidence",
            json_type,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", json_type, nullable=False),
        sa.CheckConstraint(
            "status IN ('experimental-withheld', 'eligible', 'active', 'retired')",
            name=op.f("ck_metric_system_releases_metric_system_release_status"),
        ),
        sa.CheckConstraint(
            "(status = 'active' AND activated_at IS NOT NULL) OR status != 'active'",
            name=op.f(
                "ck_metric_system_releases_metric_system_release_activation_time"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metric_system_releases")),
    )
    op.create_index(
        op.f("ix_metric_system_releases_status"),
        "metric_system_releases",
        ["status"],
        unique=False,
    )

    op.create_table(
        "paper_affiliations",
        sa.Column("id", sa.String(length=240), nullable=False),
        sa.Column("paper_id", sa.String(length=200), nullable=False),
        sa.Column("authorship_id", sa.String(length=200), nullable=True),
        sa.Column("researcher_id", sa.String(length=160), nullable=True),
        sa.Column("institution_id", sa.String(length=160), nullable=True),
        sa.Column("country_id", sa.String(length=120), nullable=True),
        sa.Column("source_snapshot_id", sa.String(length=240), nullable=False),
        sa.Column("dataset_version", sa.String(length=160), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("source_record_id", sa.String(length=400), nullable=False),
        sa.Column("author_position", sa.Integer(), nullable=False),
        sa.Column("raw_author_name", sa.Text(), nullable=False),
        sa.Column("raw_affiliation", sa.Text(), nullable=True),
        sa.Column("provider_affiliation_id", sa.String(length=500), nullable=True),
        sa.Column("subunit_label", sa.Text(), nullable=True),
        sa.Column("author_resolution_status", sa.String(length=40), nullable=False),
        sa.Column(
            "affiliation_resolution_status", sa.String(length=40), nullable=False
        ),
        sa.Column("author_weight", sa.Numeric(precision=24, scale=22), nullable=False),
        sa.Column(
            "affiliation_weight", sa.Numeric(precision=24, scale=22), nullable=False
        ),
        sa.Column(
            "attribution_weight", sa.Numeric(precision=24, scale=22), nullable=False
        ),
        sa.Column("author_weight_numerator", sa.Integer(), nullable=False),
        sa.Column("author_weight_denominator", sa.Integer(), nullable=False),
        sa.Column("attribution_weight_numerator", sa.Integer(), nullable=False),
        sa.Column("attribution_weight_denominator", sa.Integer(), nullable=False),
        sa.Column("effective_affiliation_count", sa.Integer(), nullable=False),
        sa.Column("attribution_policy_version", sa.String(length=160), nullable=False),
        sa.Column("materialization_version", sa.String(length=160), nullable=False),
        sa.Column(
            "contribution_evidence",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "resolution_evidence",
            json_type,
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", json_type, nullable=False),
        sa.CheckConstraint(
            "author_position > 0",
            name=op.f("ck_paper_affiliations_paper_affiliation_position"),
        ),
        sa.CheckConstraint(
            "author_resolution_status IN ('resolved', 'unresolved', 'ambiguous')",
            name=op.f("ck_paper_affiliations_paper_affiliation_author_status"),
        ),
        sa.CheckConstraint(
            "affiliation_resolution_status IN "
            "('resolved', 'unresolved', 'ambiguous', 'missing')",
            name=op.f("ck_paper_affiliations_paper_affiliation_status"),
        ),
        sa.CheckConstraint(
            "author_weight > 0 AND author_weight <= 1",
            name=op.f("ck_paper_affiliations_paper_affiliation_author_weight"),
        ),
        sa.CheckConstraint(
            "affiliation_weight > 0 AND affiliation_weight <= 1",
            name=op.f("ck_paper_affiliations_paper_affiliation_affiliation_weight"),
        ),
        sa.CheckConstraint(
            "attribution_weight > 0 AND attribution_weight <= 1",
            name=op.f("ck_paper_affiliations_paper_affiliation_attribution_weight"),
        ),
        sa.CheckConstraint(
            "author_weight_numerator > 0 AND author_weight_denominator > 0",
            name=op.f("ck_paper_affiliations_paper_affiliation_author_fraction"),
        ),
        sa.CheckConstraint(
            "attribution_weight_numerator > 0 AND attribution_weight_denominator > 0",
            name=op.f("ck_paper_affiliations_paper_affiliation_attribution_fraction"),
        ),
        sa.CheckConstraint(
            "effective_affiliation_count > 0",
            name=op.f("ck_paper_affiliations_paper_affiliation_effective_count"),
        ),
        sa.CheckConstraint(
            "(affiliation_resolution_status = 'resolved' AND "
            "institution_id IS NOT NULL AND country_id IS NOT NULL) OR "
            "(affiliation_resolution_status != 'resolved' AND "
            "institution_id IS NULL AND country_id IS NULL)",
            name=op.f("ck_paper_affiliations_paper_affiliation_resolution_target"),
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name=op.f("fk_paper_affiliations_paper_id_papers"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["authorship_id"],
            ["authorships.id"],
            name=op.f("fk_paper_affiliations_authorship_id_authorships"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["researcher_id"],
            ["researchers.id"],
            name=op.f("fk_paper_affiliations_researcher_id_researchers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_paper_affiliations_institution_id_institutions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["countries.id"],
            name=op.f("fk_paper_affiliations_country_id_countries"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshots.id"],
            name=op.f("fk_paper_affiliations_source_snapshot_id_source_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paper_affiliations")),
    )
    for column in (
        "paper_id",
        "authorship_id",
        "researcher_id",
        "institution_id",
        "country_id",
        "source_snapshot_id",
        "dataset_version",
        "attribution_policy_version",
        "is_current",
    ):
        op.create_index(
            op.f(f"ix_paper_affiliations_{column}"),
            "paper_affiliations",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_paper_affiliation_current_dataset",
        "paper_affiliations",
        ["paper_id", "is_current", "dataset_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_paper_affiliation_current_dataset", table_name="paper_affiliations"
    )
    for column in reversed(
        (
            "paper_id",
            "authorship_id",
            "researcher_id",
            "institution_id",
            "country_id",
            "source_snapshot_id",
            "dataset_version",
            "attribution_policy_version",
            "is_current",
        )
    ):
        op.drop_index(
            op.f(f"ix_paper_affiliations_{column}"),
            table_name="paper_affiliations",
        )
    op.drop_table("paper_affiliations")
    op.drop_index(
        op.f("ix_metric_system_releases_status"),
        table_name="metric_system_releases",
    )
    op.drop_table("metric_system_releases")

    op.drop_index(
        op.f("ix_paper_fields_mapping_rule_version"), table_name="paper_fields"
    )
    op.drop_index(op.f("ix_paper_fields_ontology_version"), table_name="paper_fields")
    with op.batch_alter_table("paper_fields") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_paper_fields_paper_field_classification_role"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_paper_fields_paper_field_weight"), type_="check"
        )
        batch_op.drop_column("uncertainty_note")
        batch_op.drop_column("provider_categories")
        batch_op.drop_column("weighting_policy_version")
        batch_op.drop_column("mapping_rule_version")
        batch_op.drop_column("ontology_version")
        batch_op.drop_column("classification_role")
        batch_op.drop_column("weight")

    op.drop_column("papers", "document_type")
    op.drop_column("papers", "publication_date_precision")
    op.drop_column("papers", "publication_date")

    op.drop_index(
        op.f("ix_research_fields_ontology_version"), table_name="research_fields"
    )
    op.drop_index(
        op.f("ix_research_fields_parent_field_id"), table_name="research_fields"
    )
    with op.batch_alter_table("research_fields") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_research_fields_research_field_display_order"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("ck_research_fields_research_field_node_kind"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_research_fields_research_field_not_own_parent"),
            type_="check",
        )
        batch_op.drop_constraint(
            op.f("fk_research_fields_parent_field_id_research_fields"),
            type_="foreignkey",
        )
        batch_op.drop_column("display_order")
        batch_op.drop_column("is_explorable")
        batch_op.drop_column("node_kind")
        batch_op.drop_column("ontology_version")
        batch_op.drop_column("aliases")
        batch_op.drop_column("parent_field_id")
