"""add user display name cooldown timestamp

Revision ID: 20260520_0022
Revises: 20260520_0021
Create Date: 2026-05-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0022"
down_revision: str | None = "20260520_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("display_name_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "display_name_updated_at")
