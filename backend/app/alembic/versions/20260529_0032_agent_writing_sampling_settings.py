"""add agent writing sampling settings

Revision ID: 20260529_0032
Revises: 20260529_0031
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260529_0032"
down_revision: Union[str, None] = "20260529_0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_activity_settings",
        sa.Column(
            "writing_temperature",
            sa.Float(),
            server_default="0.6",
            nullable=False,
        ),
    )
    op.add_column(
        "agent_activity_settings",
        sa.Column(
            "writing_presence_penalty",
            sa.Float(),
            server_default="0.3",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_agent_activity_settings_writing_temperature_range",
        "agent_activity_settings",
        "writing_temperature >= 0.0 AND writing_temperature <= 1.0",
    )
    op.create_check_constraint(
        "ck_agent_activity_settings_writing_presence_penalty_range",
        "agent_activity_settings",
        "writing_presence_penalty >= 0.0 AND writing_presence_penalty <= 1.0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_activity_settings_writing_presence_penalty_range",
        "agent_activity_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_activity_settings_writing_temperature_range",
        "agent_activity_settings",
        type_="check",
    )
    op.drop_column("agent_activity_settings", "writing_presence_penalty")
    op.drop_column("agent_activity_settings", "writing_temperature")
