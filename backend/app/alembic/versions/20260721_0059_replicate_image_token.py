"""add encrypted Replicate image token to agent image settings

Revision ID: 20260721_0059
Revises: 20260705_0058
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260721_0059"
down_revision: str | None = "20260705_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "agent_image_generation_settings",
        sa.Column("encrypted_replicate_api_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_image_generation_settings",
        sa.Column("replicate_key_fingerprint", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_image_generation_settings", "replicate_key_fingerprint")
    op.drop_column("agent_image_generation_settings", "encrypted_replicate_api_token")
