"""pollinations post image settings

Revision ID: 20260615_0045
Revises: 20260615_0044
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260615_0045"
down_revision: str | None = "20260615_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_image_generation_settings",
        sa.Column("encrypted_pollinations_api_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_image_generation_settings",
        sa.Column(
            "pollinations_image_model",
            sa.String(length=80),
            nullable=False,
            server_default="klein",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_image_generation_settings", "pollinations_image_model")
    op.drop_column("agent_image_generation_settings", "encrypted_pollinations_api_key")
