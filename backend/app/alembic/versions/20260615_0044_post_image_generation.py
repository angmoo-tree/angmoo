"""post image generation settings and media

Revision ID: 20260615_0044
Revises: 20260615_0043
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260615_0044"
down_revision: str | None = "20260615_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_image_generation_settings",
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("encrypted_openrouter_api_key", sa.Text(), nullable=True),
        sa.Column("key_fingerprint", sa.String(length=32), nullable=True),
        sa.Column(
            "image_generation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "max_images_per_day",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
        sa.Column(
            "openrouter_image_model",
            sa.String(length=120),
            nullable=False,
            server_default="black-forest-labs/flux.2-klein-4b",
        ),
        sa.Column("seed_image_url", sa.String(length=500), nullable=True),
        sa.Column("visual_identity_prompt", sa.Text(), nullable=True),
        sa.Column("visual_identity_source_hash", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("character_id"),
    )
    op.create_table(
        "post_media",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=False),
        sa.Column(
            "media_type",
            sa.String(length=20),
            nullable=False,
            server_default="image",
        ),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_post_media_post_id"), "post_media", ["post_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_post_media_post_id"), table_name="post_media")
    op.drop_table("post_media")
    op.drop_table("agent_image_generation_settings")
