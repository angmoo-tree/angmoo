"""add agent run gateway result

Revision ID: 20260526_0029
Revises: 20260522_0028
Create Date: 2026-05-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260526_0029"
down_revision: Union[str, None] = "20260522_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("gateway_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "gateway_result")
