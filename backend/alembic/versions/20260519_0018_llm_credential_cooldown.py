"""add llm credential cooldown

Revision ID: 20260519_0018
Revises: 20260519_0017
Create Date: 2026-05-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0018"
down_revision: str | None = "20260519_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_credentials",
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_credentials", "cooldown_until")
