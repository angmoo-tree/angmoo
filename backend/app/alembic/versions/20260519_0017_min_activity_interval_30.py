"""raise minimum agent activity interval to 30 minutes

Revision ID: 20260519_0017
Revises: 20260519_0016
Create Date: 2026-05-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260519_0017"
down_revision: str | None = "20260519_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE agent_activity_settings
            SET activity_interval_minutes = 30
            WHERE activity_interval_minutes < 30
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE agent_slots
            SET heartbeat_interval_seconds = 1800,
                next_tick_at = CASE
                    WHEN next_tick_at IS NULL
                      OR next_tick_at < NOW() + INTERVAL '30 minutes'
                    THEN NOW() + INTERVAL '30 minutes'
                    ELSE next_tick_at
                END
            WHERE heartbeat_interval_seconds IS NOT NULL
              AND heartbeat_interval_seconds < 1800
            """
        )
    )


def downgrade() -> None:
    pass
