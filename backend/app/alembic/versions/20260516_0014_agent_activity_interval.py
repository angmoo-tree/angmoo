"""add agent activity interval

Revision ID: 20260516_0014
Revises: 20260516_0013
Create Date: 2026-05-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0014"
down_revision: str | None = "20260516_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_activity_settings",
        sa.Column(
            "activity_interval_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )
    op.alter_column("agent_activity_settings", "activity_interval_minutes", server_default=None)


def downgrade() -> None:
    op.drop_column("agent_activity_settings", "activity_interval_minutes")
