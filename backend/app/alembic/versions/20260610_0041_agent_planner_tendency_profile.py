"""agent planner tendency profile

Revision ID: 20260610_0041
Revises: 20260610_0040
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260610_0041"
down_revision: str | None = "20260610_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_activity_settings",
        sa.Column(
            "planner_tendency_profile",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column(
        "agent_activity_settings",
        "planner_tendency_profile",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("agent_activity_settings", "planner_tendency_profile")
