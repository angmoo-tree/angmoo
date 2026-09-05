"""add agent writing repetition level

Revision ID: 20260529_0033
Revises: 20260529_0032
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260529_0033"
down_revision: Union[str, None] = "20260529_0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_activity_settings",
        sa.Column(
            "writing_repetition_level",
            sa.String(length=20),
            server_default="light",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_agent_activity_settings_writing_repetition_level",
        "agent_activity_settings",
        "writing_repetition_level in ('off', 'light', 'normal', 'strong')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_activity_settings_writing_repetition_level",
        "agent_activity_settings",
        type_="check",
    )
    op.drop_column("agent_activity_settings", "writing_repetition_level")
