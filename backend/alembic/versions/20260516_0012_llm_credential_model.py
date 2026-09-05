"""add llm credential model

Revision ID: 20260516_0012
Revises: 20260516_0011
Create Date: 2026-05-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0012"
down_revision: str | None = "20260516_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_credentials",
        sa.Column(
            "model",
            sa.String(length=120),
            nullable=False,
            server_default="gemini-2.5-flash",
        ),
    )
    op.alter_column("llm_credentials", "model", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_credentials", "model")
