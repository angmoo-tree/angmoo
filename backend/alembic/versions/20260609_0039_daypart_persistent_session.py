"""daypart persistent session memory events

Revision ID: 20260609_0039
Revises: 20260605_0038
Create Date: 2026-06-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260609_0039"
down_revision: str | None = "20260605_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("tool_auth_key", sa.String(length=255), nullable=True))
    op.create_index(
        op.f("ix_agent_runs_tool_auth_key"),
        "agent_runs",
        ["tool_auth_key"],
        unique=False,
    )
    op.create_table(
        "agent_daypart_memory_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("memory_session_key", sa.String(length=255), nullable=False),
        sa.Column("daypart_start_date", sa.Date(), nullable=False),
        sa.Column("activity_daypart", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_post_id", sa.String(), nullable=True),
        sa.Column("notification_id", sa.Integer(), nullable=True),
        sa.Column("thread_id", sa.String(length=80), nullable=True),
        sa.Column("topic_signature", sa.String(length=300), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("provided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["source_post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_daypart_memory_events_character_id"),
        "agent_daypart_memory_events",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_daypart_memory_events_event_type"),
        "agent_daypart_memory_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_daypart_memory_events_memory_session_key"),
        "agent_daypart_memory_events",
        ["memory_session_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_daypart_memory_events_notification_id"),
        "agent_daypart_memory_events",
        ["notification_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_daypart_memory_events_run_id"),
        "agent_daypart_memory_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_daypart_memory_events_source_post_id"),
        "agent_daypart_memory_events",
        ["source_post_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_daypart_memory_events_thread_id"),
        "agent_daypart_memory_events",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_daypart_memory_events_window_event",
        "agent_daypart_memory_events",
        ["character_id", "daypart_start_date", "activity_daypart", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_daypart_memory_events_window_event", table_name="agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_daypart_memory_events_thread_id"), table_name="agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_daypart_memory_events_source_post_id"), table_name="agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_daypart_memory_events_run_id"), table_name="agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_daypart_memory_events_notification_id"), table_name="agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_daypart_memory_events_memory_session_key"), table_name="agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_daypart_memory_events_event_type"), table_name="agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_daypart_memory_events_character_id"), table_name="agent_daypart_memory_events")
    op.drop_table("agent_daypart_memory_events")
    op.drop_index(op.f("ix_agent_runs_tool_auth_key"), table_name="agent_runs")
    op.drop_column("agent_runs", "tool_auth_key")
