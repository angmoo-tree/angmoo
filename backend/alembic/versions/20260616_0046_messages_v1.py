"""messages v1

Revision ID: 20260616_0046
Revises: 20260615_0045
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260616_0046"
down_revision: str | None = "20260615_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_credentials",
        sa.Column(
            "purpose",
            sa.String(length=20),
            nullable=False,
            server_default="agent",
        ),
    )
    op.drop_constraint(
        "uq_llm_credentials_character_id", "llm_credentials", type_="unique"
    )
    op.create_check_constraint(
        "ck_llm_credentials_purpose",
        "llm_credentials",
        "purpose in ('agent', 'message')",
    )
    op.create_index(
        "uq_llm_credentials_agent_character",
        "llm_credentials",
        ["character_id"],
        unique=True,
        postgresql_where=sa.text("purpose = 'agent' and character_id is not null"),
    )
    op.create_index(
        "uq_llm_credentials_message_owner",
        "llm_credentials",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("purpose = 'message'"),
    )

    op.create_table(
        "character_message_settings",
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
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
        "user_message_preferences",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "credential_source",
            sa.String(length=20),
            nullable=False,
            server_default="message_key",
        ),
        sa.Column("source_character_id", sa.String(length=64), nullable=True),
        sa.Column(
            "default_model",
            sa.String(length=120),
            nullable=False,
            server_default="gemini-3.1-flash-lite",
        ),
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
        sa.CheckConstraint(
            "credential_source in ('message_key', 'agent_key')",
            name="ck_user_message_preferences_source",
        ),
        sa.ForeignKeyConstraint(["source_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "message_threads",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("requester_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column(
            "selected_model",
            sa.String(length=120),
            nullable=False,
            server_default="gemini-3.1-flash-lite",
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_message_threads_active_requester_character",
        "message_threads",
        ["requester_id", "character_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at is null"),
    )
    op.create_index(
        "ix_message_threads_requester_last",
        "message_threads",
        ["requester_id", "last_message_at"],
    )
    op.create_table(
        "message_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("role in ('user', 'assistant')", name="ck_message_messages_role"),
        sa.CheckConstraint(
            "status in ('ok', 'error')", name="ck_message_messages_status"
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["message_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_message_messages_thread_created",
        "message_messages",
        ["thread_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_messages_thread_created", table_name="message_messages")
    op.drop_table("message_messages")
    op.drop_index("ix_message_threads_requester_last", table_name="message_threads")
    op.drop_index(
        "uq_message_threads_active_requester_character", table_name="message_threads"
    )
    op.drop_table("message_threads")
    op.drop_table("user_message_preferences")
    op.drop_table("character_message_settings")
    op.drop_index("uq_llm_credentials_message_owner", table_name="llm_credentials")
    op.drop_index("uq_llm_credentials_agent_character", table_name="llm_credentials")
    op.drop_constraint(
        "ck_llm_credentials_purpose", "llm_credentials", type_="check"
    )
    op.create_unique_constraint(
        "uq_llm_credentials_character_id", "llm_credentials", ["character_id"]
    )
    op.drop_column("llm_credentials", "purpose")
