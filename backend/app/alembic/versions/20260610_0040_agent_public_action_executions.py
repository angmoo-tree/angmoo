"""agent public action executions

Revision ID: 20260610_0040
Revises: 20260609_0039
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260610_0040"
down_revision: str | None = "20260609_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_public_action_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("signature", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("target_post_id", sa.String(), nullable=True),
        sa.Column("target_profile_type", sa.String(length=40), nullable=True),
        sa.Column("target_profile_id", sa.String(length=64), nullable=True),
        sa.Column("brief_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("failure_class", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["target_post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signature", name="uq_agent_public_action_executions_signature"),
    )
    op.create_index(
        op.f("ix_agent_public_action_executions_character_id"),
        "agent_public_action_executions",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_public_action_executions_run_id"),
        "agent_public_action_executions",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_public_action_executions_target_post_id"),
        "agent_public_action_executions",
        ["target_post_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_public_action_executions_target_post_id"),
        table_name="agent_public_action_executions",
    )
    op.drop_index(
        op.f("ix_agent_public_action_executions_run_id"),
        table_name="agent_public_action_executions",
    )
    op.drop_index(
        op.f("ix_agent_public_action_executions_character_id"),
        table_name="agent_public_action_executions",
    )
    op.drop_table("agent_public_action_executions")
