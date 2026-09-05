"""local api post image jobs

Revision ID: 20260618_0052
Revises: 20260617_0051
Create Date: 2026-06-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260618_0052"
down_revision: str | None = "20260617_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "post_image_generation_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("image_model", sa.String(length=120), nullable=False),
        sa.Column("image_prompt", sa.Text(), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("reference_source", sa.String(length=40), nullable=True),
        sa.Column("skip_reason", sa.String(length=80), nullable=True),
        sa.Column("failure_class", sa.String(length=120), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("media_url", sa.String(length=500), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", name="uq_post_image_generation_jobs_post_id"),
    )
    op.create_index(
        op.f("ix_post_image_generation_jobs_character_id"),
        "post_image_generation_jobs",
        ["character_id"],
    )
    op.create_index(
        op.f("ix_post_image_generation_jobs_post_id"),
        "post_image_generation_jobs",
        ["post_id"],
    )
    op.create_index(
        "ix_post_image_generation_jobs_status_created_at",
        "post_image_generation_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_post_image_generation_jobs_status_created_at",
        table_name="post_image_generation_jobs",
    )
    op.drop_index(
        op.f("ix_post_image_generation_jobs_post_id"),
        table_name="post_image_generation_jobs",
    )
    op.drop_index(
        op.f("ix_post_image_generation_jobs_character_id"),
        table_name="post_image_generation_jobs",
    )
    op.drop_table("post_image_generation_jobs")
