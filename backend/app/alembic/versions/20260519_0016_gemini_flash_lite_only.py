"""limit google credentials to gemini flash lite

Revision ID: 20260519_0016
Revises: 20260517_0015
Create Date: 2026-05-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0016"
down_revision: str | None = "20260517_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE llm_credentials
            SET model = 'gemini-3.1-flash-lite'
            WHERE provider = 'google'
              AND model <> 'gemini-3.1-flash-lite'
            """
        )
    )


def downgrade() -> None:
    pass
