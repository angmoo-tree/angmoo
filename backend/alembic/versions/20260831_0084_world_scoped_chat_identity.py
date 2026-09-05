"""add World-scoped Chat v2 identity and deterministic legacy binding

Revision ID: 20260831_0084
Revises: 20260825_0083
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.domains.chat.infrastructure.world_scope_migration import (
    backfill_message_thread_world_scope,
    rebuild_and_backfill_message_threads_v4,
    rebuild_message_threads_v3,
)


revision: str = "20260831_0084"
down_revision: str | None = "20260825_0083"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        rebuild_and_backfill_message_threads_v4(bind)
        return

    op.add_column(
        "message_threads",
        sa.Column("world_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "message_threads",
        sa.Column(
            "requester_world_character_id", sa.String(length=64), nullable=True
        ),
    )
    op.add_column(
        "message_threads",
        sa.Column(
            "responding_world_character_id", sa.String(length=64), nullable=True
        ),
    )
    op.add_column(
        "message_threads",
        sa.Column(
            "world_scope_status",
            sa.String(length=20),
            nullable=False,
            server_default="ambiguous",
        ),
    )
    op.create_foreign_key(
        "fk_message_threads_world",
        "message_threads",
        "worlds",
        ["world_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_message_threads_requester_world",
        "message_threads",
        "world_characters",
        ["requester_world_character_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_foreign_key(
        "fk_message_threads_responding_world",
        "message_threads",
        "world_characters",
        ["responding_world_character_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_foreign_key(
        "fk_message_threads_responding_character",
        "message_threads",
        "world_characters",
        ["responding_world_character_id", "character_id"],
        ["id", "character_id"],
    )
    op.create_check_constraint(
        "ck_message_threads_world_scope_binding",
        "message_threads",
        "(world_scope_status = 'resolved' AND world_id IS NOT NULL "
        "AND requester_world_character_id IS NOT NULL "
        "AND responding_world_character_id IS NOT NULL "
        "AND requester_world_character_id <> responding_world_character_id) OR "
        "(world_scope_status IN ('ambiguous', 'quarantined') "
        "AND world_id IS NULL "
        "AND requester_world_character_id IS NULL "
        "AND responding_world_character_id IS NULL)",
    )
    backfill_message_thread_world_scope(bind)
    op.drop_index(
        "uq_message_threads_active_requester_character",
        table_name="message_threads",
    )
    op.create_index(
        "ix_message_threads_owner_world_status",
        "message_threads",
        ["requester_id", "world_id", "world_scope_status"],
    )
    op.create_index(
        "uq_message_threads_active_legacy_ambiguous",
        "message_threads",
        ["requester_id", "character_id"],
        unique=True,
        postgresql_where=sa.text(
            "deleted_at IS NULL AND world_scope_status = 'ambiguous'"
        ),
    )
    op.create_index(
        "uq_message_threads_active_world_roles",
        "message_threads",
        [
            "requester_id",
            "world_id",
            "requester_world_character_id",
            "responding_world_character_id",
        ],
        unique=True,
        postgresql_where=sa.text(
            "deleted_at IS NULL AND world_scope_status = 'resolved'"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        rebuild_message_threads_v3(bind, create_legacy_unique_index=True)
        return

    duplicate = bind.execute(
        sa.text(
            "SELECT requester_id, character_id, count(*) AS row_count "
            "FROM message_threads WHERE deleted_at IS NULL "
            "GROUP BY requester_id, character_id HAVING count(*) > 1 LIMIT 1"
        )
    ).mappings().first()
    if duplicate is not None:
        raise RuntimeError(
            "cannot_downgrade_world_chat_duplicate_legacy_active_tuple"
        )
    op.drop_index(
        "uq_message_threads_active_world_roles", table_name="message_threads"
    )
    op.drop_index(
        "uq_message_threads_active_legacy_ambiguous",
        table_name="message_threads",
    )
    op.drop_index(
        "ix_message_threads_owner_world_status", table_name="message_threads"
    )
    op.drop_constraint(
        "ck_message_threads_world_scope_binding",
        "message_threads",
        type_="check",
    )
    for name in (
        "fk_message_threads_responding_character",
        "fk_message_threads_responding_world",
        "fk_message_threads_requester_world",
        "fk_message_threads_world",
    ):
        op.drop_constraint(name, "message_threads", type_="foreignkey")
    op.drop_column("message_threads", "world_scope_status")
    op.drop_column("message_threads", "responding_world_character_id")
    op.drop_column("message_threads", "requester_world_character_id")
    op.drop_column("message_threads", "world_id")
    op.create_index(
        "uq_message_threads_active_requester_character",
        "message_threads",
        ["requester_id", "character_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
