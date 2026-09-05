"""message default gemma4 26b

Revision ID: 20260616_0047
Revises: 20260616_0046
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260616_0047"
down_revision: str | None = "20260616_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_DEFAULT = "gemini-3.1-flash-lite"
NEW_DEFAULT = "gemma-4-26b-a4b-it"


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
    op.execute(
        sa.text(
            """
            update user_message_preferences
               set default_model = :new_default
             where default_model = :old_default
            """
        ).bindparams(old_default=OLD_DEFAULT, new_default=NEW_DEFAULT)
    )
    op.execute(
        sa.text(
            """
            update llm_credentials
               set label = '쪽지용 Google API key'
             where purpose = 'message'
               and label = '대화용 Google API key'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            update user_message_preferences
               set default_model = :old_default
             where default_model = :new_default
            """
        ).bindparams(old_default=OLD_DEFAULT, new_default=NEW_DEFAULT)
    )
    op.execute(
        sa.text(
            """
            update llm_credentials
               set label = '대화용 Google API key'
             where purpose = 'message'
               and label = '쪽지용 Google API key'
            """
        )
    )
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
