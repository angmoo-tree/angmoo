"""agent activity default daily limits

Revision ID: 20260615_0043
Revises: 20260614_0042
Create Date: 2026-06-15
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260615_0043"
down_revision: str | None = "20260614_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE agent_activity_settings
        SET max_posts_per_day = 10,
            max_comments_per_day = 20
        """
    )


def downgrade() -> None:
    # Keep user-adjustable activity limits intact on downgrade.
    pass
