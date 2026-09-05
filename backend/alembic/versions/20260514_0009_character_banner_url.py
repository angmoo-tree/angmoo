"""add character banner url

Revision ID: 20260514_0009
Revises: 20260514_0008
Create Date: 2026-05-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260514_0009"
down_revision: str | None = "20260514_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters", sa.Column("banner_url", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("characters", "banner_url")
