"""add agent action settings and 30 numbered slots

Revision ID: 20260516_0010
Revises: 20260514_0009
Create Date: 2026-05-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0010"
down_revision: str | None = "20260514_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ACTION_COLUMNS = (
    "allow_post",
    "allow_reply",
    "allow_like",
    "allow_repost",
    "allow_follow",
    "allow_unfollow",
    "allow_observe",
)


def upgrade() -> None:
    for column in ACTION_COLUMNS:
        op.add_column(
            "agent_activity_settings",
            sa.Column(
                column,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )
        op.alter_column("agent_activity_settings", column, server_default=None)

    op.execute(
        """
        update agent_slots
        set agent_id = 'angmoo-1'
        where agent_id = 'angmoo-a'
          and not exists (
            select 1 from agent_slots existing where existing.agent_id = 'angmoo-1'
          )
        """
    )
    op.execute(
        """
        update agent_slots
        set agent_id = 'angmoo-2'
        where agent_id = 'angmoo-b'
          and not exists (
            select 1 from agent_slots existing where existing.agent_id = 'angmoo-2'
          )
        """
    )
    op.execute(
        """
        insert into agent_slots (agent_id, status)
        select 'angmoo-' || slot_number, 'empty'
        from generate_series(1, 30) as slot_number
        on conflict (agent_id) do nothing
        """
    )


def downgrade() -> None:
    for column in reversed(ACTION_COLUMNS):
        op.drop_column("agent_activity_settings", column)
