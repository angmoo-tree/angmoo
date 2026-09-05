"""add agent tendency analysis fields

Revision ID: 20260516_0011
Revises: 20260516_0010
Create Date: 2026-05-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0011"
down_revision: str | None = "20260516_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_activity_settings",
        sa.Column("tendency_summary", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_activity_settings",
        sa.Column(
            "tendency_action_ranges",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.add_column(
        "agent_activity_settings",
        sa.Column("tendency_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_activity_settings",
        sa.Column("tendency_error", sa.Text(), nullable=True),
    )
    op.alter_column("agent_activity_settings", "tendency_summary", server_default=None)
    op.alter_column(
        "agent_activity_settings", "tendency_action_ranges", server_default=None
    )


def downgrade() -> None:
    op.drop_column("agent_activity_settings", "tendency_error")
    op.drop_column("agent_activity_settings", "tendency_updated_at")
    op.drop_column("agent_activity_settings", "tendency_action_ranges")
    op.drop_column("agent_activity_settings", "tendency_summary")
