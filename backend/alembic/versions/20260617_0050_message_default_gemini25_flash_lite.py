"""message default gemini25 flash lite

Revision ID: 20260617_0050
Revises: 20260616_0049
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260617_0050"
down_revision: str | None = "20260616_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_DEFAULT = "gemini-2.5-flash-lite"
OLD_DEFAULT = "gemma-4-26b-a4b-it"


def upgrade() -> None:
    op.alter_column(
        "user_message_preferences",
        "default_model",
        existing_type=sa.String(length=120),
        server_default=NEW_DEFAULT,
        existing_nullable=False,
    )
    op.alter_column(
        "message_threads",
        "selected_model",
        existing_type=sa.String(length=120),
        server_default=NEW_DEFAULT,
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "message_threads",
        "selected_model",
        existing_type=sa.String(length=120),
        server_default=OLD_DEFAULT,
        existing_nullable=False,
    )
    op.alter_column(
        "user_message_preferences",
        "default_model",
        existing_type=sa.String(length=120),
        server_default=OLD_DEFAULT,
        existing_nullable=False,
    )
