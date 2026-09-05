"""add agent feed cues

Revision ID: 20260516_0013
Revises: 20260516_0012
Create Date: 2026-05-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260516_0013"
down_revision: str | None = "20260516_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_feed_cues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("consumed_run_id", sa.String(length=64), nullable=True),
        sa.Column("consumed_post_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["consumed_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["consumed_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_feed_cues_pending_character",
        "agent_feed_cues",
        ["character_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_agent_feed_cues_character_created",
        "agent_feed_cues",
        ["character_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_feed_cues_character_created", table_name="agent_feed_cues")
    op.drop_index("ix_agent_feed_cues_pending_character", table_name="agent_feed_cues")
    op.drop_table("agent_feed_cues")
