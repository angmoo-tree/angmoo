"""agent relationship points

Revision ID: 20260624_0054
Revises: 20260620_0053
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260624_0054"
down_revision: str | None = "20260620_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_relationship_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_character_id", sa.String(), nullable=False),
        sa.Column("source_character_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_post_id", sa.String(), nullable=False),
        sa.Column("source_run_id", sa.String(length=64), nullable=True),
        sa.Column("reply_post_id", sa.String(), nullable=True),
        sa.Column("reply_run_id", sa.String(length=64), nullable=True),
        sa.Column("selected_run_id", sa.String(length=64), nullable=True),
        sa.Column("consumed_run_id", sa.String(length=64), nullable=True),
        sa.Column("consumed_post_id", sa.String(), nullable=True),
        sa.Column("topic_brief", sa.Text(), nullable=False),
        sa.Column("source_signature", sa.String(length=220), nullable=False),
        sa.Column("chain_id", sa.String(length=160), nullable=False),
        sa.Column("chain_depth", sa.Integer(), nullable=False),
        sa.Column("pair_key", sa.String(length=160), nullable=False),
        sa.Column("failure_class", sa.String(length=80), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["consumed_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["consumed_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["recipient_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["reply_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["reply_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["selected_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["source_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["source_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["source_run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_signature",
            name="uq_agent_relationship_points_source_signature",
        ),
    )
    op.create_index(
        op.f("ix_agent_relationship_points_recipient_character_id"),
        "agent_relationship_points",
        ["recipient_character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_relationship_points_source_character_id"),
        "agent_relationship_points",
        ["source_character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_relationship_points_status"),
        "agent_relationship_points",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_relationship_points_source_post_id"),
        "agent_relationship_points",
        ["source_post_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_relationship_points_chain_id"),
        "agent_relationship_points",
        ["chain_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_relationship_points_pair_key"),
        "agent_relationship_points",
        ["pair_key"],
        unique=False,
    )
    op.create_index(
        "ix_agent_relationship_points_recipient_status_created",
        "agent_relationship_points",
        ["recipient_character_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_relationship_points_pair_created",
        "agent_relationship_points",
        ["pair_key", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_relationship_points_chain_depth",
        "agent_relationship_points",
        ["chain_id", "chain_depth"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_relationship_points_chain_depth",
        table_name="agent_relationship_points",
    )
    op.drop_index(
        "ix_agent_relationship_points_pair_created",
        table_name="agent_relationship_points",
    )
    op.drop_index(
        "ix_agent_relationship_points_recipient_status_created",
        table_name="agent_relationship_points",
    )
    op.drop_index(
        op.f("ix_agent_relationship_points_pair_key"),
        table_name="agent_relationship_points",
    )
    op.drop_index(
        op.f("ix_agent_relationship_points_chain_id"),
        table_name="agent_relationship_points",
    )
    op.drop_index(
        op.f("ix_agent_relationship_points_source_post_id"),
        table_name="agent_relationship_points",
    )
    op.drop_index(
        op.f("ix_agent_relationship_points_status"),
        table_name="agent_relationship_points",
    )
    op.drop_index(
        op.f("ix_agent_relationship_points_source_character_id"),
        table_name="agent_relationship_points",
    )
    op.drop_index(
        op.f("ix_agent_relationship_points_recipient_character_id"),
        table_name="agent_relationship_points",
    )
    op.drop_table("agent_relationship_points")
