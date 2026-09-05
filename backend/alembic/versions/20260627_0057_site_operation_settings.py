"""add site operation settings

Revision ID: 20260627_0057
Revises: 20260625_0056
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260627_0057"
down_revision: str | None = "20260625_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_operation_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("key"),
    )
    settings_table = sa.table(
        "site_operation_settings",
        sa.column("key", sa.String),
        sa.column("value", sa.String),
    )
    op.bulk_insert(
        settings_table,
        [{"key": "pollinations_free_image_model", "value": "flux"}],
    )


def downgrade() -> None:
    op.drop_table("site_operation_settings")
