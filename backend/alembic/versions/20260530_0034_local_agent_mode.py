"""add local agent execution mode

Revision ID: 20260530_0034
Revises: 20260529_0033
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260530_0034"
down_revision: Union[str, None] = "20260529_0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column(
            "execution_mode",
            sa.String(length=20),
            server_default="llm",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_characters_execution_mode",
        "characters",
        "execution_mode in ('llm', 'local')",
    )

    op.create_table(
        "agent_local_keys",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_agent_local_keys_token_hash"),
    )
    op.create_index(
        "ix_agent_local_keys_owner_id",
        "agent_local_keys",
        ["owner_id"],
    )
    op.create_index(
        "ix_agent_local_keys_character_id",
        "agent_local_keys",
        ["character_id"],
    )
    op.create_index(
        "uq_agent_local_keys_active_character",
        "agent_local_keys",
        ["character_id"],
        unique=True,
        postgresql_where=sa.text("enabled IS TRUE AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_agent_local_keys_active_character", table_name="agent_local_keys")
    op.drop_index("ix_agent_local_keys_character_id", table_name="agent_local_keys")
    op.drop_index("ix_agent_local_keys_owner_id", table_name="agent_local_keys")
    op.drop_table("agent_local_keys")
    op.drop_constraint(
        "ck_characters_execution_mode", "characters", type_="check"
    )
    op.drop_column("characters", "execution_mode")
