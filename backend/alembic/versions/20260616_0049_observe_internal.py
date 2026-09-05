"""internalize observe fallback

Revision ID: 20260616_0049
Revises: 20260616_0048
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260616_0049"
down_revision: str | None = "20260616_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            update agent_activity_settings as settings
               set allow_observe = true
              from characters
             where characters.id = settings.character_id
               and characters.deleted_at is null
               and settings.allow_observe is false
            """
        )
    )


def downgrade() -> None:
    pass
