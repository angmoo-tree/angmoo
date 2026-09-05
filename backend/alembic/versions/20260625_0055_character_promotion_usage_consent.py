"""add character promotion usage consent

Revision ID: 20260625_0055
Revises: 20260624_0054
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260625_0055"
down_revision: str | None = "20260624_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column(
            "promotion_usage_allowed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "characters",
        sa.Column("promotion_usage_agreed_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "characters",
        sa.Column("promotion_usage_revoked_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "characters",
        sa.Column("promotion_usage_policy_version", sa.String(length=20)),
    )


def downgrade() -> None:
    op.drop_column("characters", "promotion_usage_policy_version")
    op.drop_column("characters", "promotion_usage_revoked_at")
    op.drop_column("characters", "promotion_usage_agreed_at")
    op.drop_column("characters", "promotion_usage_allowed")
