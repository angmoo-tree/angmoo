"""drop user avatar url

Revision ID: 20260520_0024
Revises: 20260520_0023
Create Date: 2026-05-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0024"
down_revision: str | None = "20260520_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("users", "avatar_url")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
    )
