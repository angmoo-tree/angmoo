"""Add character deleted_at

Revision ID: 20260522_0026
Revises: 20260522_0025
Create Date: 2026-05-22 00:26:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "20260522_0026"
down_revision: str | None = "20260522_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "deleted_at")
