"""add agent creation drafts

Revision ID: 20260522_0028
Revises: 20260522_0027
Create Date: 2026-05-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260522_0028"
down_revision: Union[str, None] = "20260522_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_creation_drafts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("handle", sa.String(length=40), nullable=True),
        sa.Column("one_liner", sa.Text(), nullable=False),
        sa.Column("personality", sa.Text(), nullable=False),
        sa.Column("speech_style", sa.Text(), nullable=False),
        sa.Column("worldview", sa.Text(), nullable=False),
        sa.Column("topic_preferences", sa.Text(), nullable=False),
        sa.Column("safety_rules", sa.Text(), nullable=False),
        sa.Column("image_style", sa.String(length=40), nullable=False),
        sa.Column("appearance_prompt", sa.Text(), nullable=False),
        sa.Column("avatar_temp_url", sa.String(length=500), nullable=True),
        sa.Column("banner_temp_url", sa.String(length=500), nullable=True),
        sa.Column("persona_enhance_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("media_generation_available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_creation_drafts_user_expires",
        "agent_creation_drafts",
        ["user_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_creation_drafts_user_expires", table_name="agent_creation_drafts")
    op.drop_table("agent_creation_drafts")
