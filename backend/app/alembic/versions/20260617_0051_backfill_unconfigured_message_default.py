"""backfill unconfigured message default model

Revision ID: 20260617_0051
Revises: 20260617_0050
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260617_0051"
down_revision: str | None = "20260617_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_DEFAULT = "gemini-2.5-flash-lite"
OLD_GEMMA_DEFAULT = "gemma-4-26b-a4b-it"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            update user_message_preferences preference
               set default_model = :new_default
             where preference.default_model = :old_default
               and preference.credential_source = 'message_key'
               and preference.source_character_id is null
               and not exists (
                    select 1
                      from llm_credentials credential
                     where credential.owner_id = preference.user_id
                       and credential.purpose = 'message'
                       and credential.enabled is true
               )
               and not exists (
                    select 1
                      from message_threads thread
                     where thread.requester_id = preference.user_id
                       and thread.deleted_at is null
               )
            """
        ).bindparams(old_default=OLD_GEMMA_DEFAULT, new_default=NEW_DEFAULT)
    )


def downgrade() -> None:
    # This is a one-way cleanup of unconfigured preferences. Reversing it could
    # overwrite a user's current default model after the upgrade has run.
    pass
