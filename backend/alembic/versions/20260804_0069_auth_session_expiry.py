"""add optional auth session expiry

Revision ID: 20260804_0069
Revises: 20260802_0068
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260804_0069"
down_revision: str | None = "20260802_0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "expires_at")
