"""add resident agent slot fields

Revision ID: 20260511_0004
Revises: 20260511_0003
Create Date: 2026-05-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260511_0004"
down_revision: str | None = "20260511_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_slots",
        sa.Column("assigned_user_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_slots",
        sa.Column("assigned_character_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_slots",
        sa.Column("assigned_credential_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_slots",
        sa.Column("next_tick_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_slots",
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_slots",
        sa.Column("heartbeat_interval_seconds", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_slots_assigned_user_id",
        "agent_slots",
        "users",
        ["assigned_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_agent_slots_assigned_character_id",
        "agent_slots",
        "characters",
        ["assigned_character_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_agent_slots_assigned_credential_id",
        "agent_slots",
        "llm_credentials",
        ["assigned_credential_id"],
        ["id"],
    )
    op.create_index("ix_agent_slots_next_tick", "agent_slots", ["next_tick_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_slots_next_tick", table_name="agent_slots")
    op.drop_constraint(
        "fk_agent_slots_assigned_credential_id", "agent_slots", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_agent_slots_assigned_character_id", "agent_slots", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_agent_slots_assigned_user_id", "agent_slots", type_="foreignkey"
    )
    op.drop_column("agent_slots", "heartbeat_interval_seconds")
    op.drop_column("agent_slots", "last_run_at")
    op.drop_column("agent_slots", "next_tick_at")
    op.drop_column("agent_slots", "assigned_credential_id")
    op.drop_column("agent_slots", "assigned_character_id")
    op.drop_column("agent_slots", "assigned_user_id")
