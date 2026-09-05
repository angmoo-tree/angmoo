"""increase default reply limit to 30

Revision ID: 20260625_0056
Revises: 20260625_0055
Create Date: 2026-06-25
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260625_0056"
down_revision: str | None = "20260625_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE agent_activity_settings
        SET max_comments_per_day = 30
        WHERE max_comments_per_day = 20
        """
    )


def downgrade() -> None:
    # Keep user-adjustable activity limits intact on downgrade.
    pass
