"""add acquisition scope to provider cursors

Revision ID: 79a430f5b6c2
Revises: 1a36959a7f7b
Create Date: 2026-08-28 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "79a430f5b6c2"
down_revision: str | Sequence[str] | None = "1a36959a7f7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_cursors",
        sa.Column(
            "scope_version",
            sa.String(length=240),
            nullable=False,
            server_default="legacy-unbounded-v1",
        ),
    )


def downgrade() -> None:
    op.drop_column("source_cursors", "scope_version")
