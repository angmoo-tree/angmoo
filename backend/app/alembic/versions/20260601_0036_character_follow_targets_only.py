"""restrict follow targets to characters

Revision ID: 20260601_0036
Revises: 20260530_0035
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260601_0036"
down_revision: Union[str, None] = "20260530_0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM profile_follows WHERE target_user_id IS NOT NULL")


def downgrade() -> None:
    pass
