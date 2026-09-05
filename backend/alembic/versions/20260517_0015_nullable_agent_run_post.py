"""allow agent runs without a seed post

Revision ID: 20260517_0015
Revises: 20260516_0014
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260517_0015"
down_revision = "20260516_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "agent_runs",
        "post_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "agent_runs",
        "post_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
