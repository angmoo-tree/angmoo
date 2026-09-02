"""add World Chat response-model binding policy

Revision ID: 20260903_0087
Revises: 20260831_0086
Create Date: 2026-09-03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.domains.chat.infrastructure.model_binding_migration import (
    rebuild_and_backfill_message_threads_v7,
    rebuild_message_threads_v6,
    validate_resolved_default_models,
)


revision: str = "20260903_0087"
down_revision: str | None = "20260831_0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        rebuild_and_backfill_message_threads_v7(bind)
        return

    validate_resolved_default_models(bind)
    op.add_column(
        "message_threads",
        sa.Column(
            "model_binding_mode",
            sa.String(length=20),
            nullable=False,
            server_default="thread_override",
        ),
    )
    bind.execute(
        sa.text(
            "UPDATE message_threads AS thread SET "
            "model_binding_mode = 'default', "
            "selected_model = COALESCE(("
            "SELECT preference.default_model FROM user_message_preferences AS preference "
            "WHERE preference.user_id = thread.requester_id"
            "), thread.selected_model) "
            "WHERE thread.world_scope_status = 'resolved'"
        )
    )
    op.create_check_constraint(
        "ck_message_threads_model_binding_mode",
        "message_threads",
        "model_binding_mode IN ('default','thread_override')",
    )
    op.create_check_constraint(
        "ck_message_threads_legacy_model_binding",
        "message_threads",
        "world_scope_status = 'resolved' OR "
        "model_binding_mode = 'thread_override'",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        rebuild_message_threads_v6(bind)
        return
    op.drop_constraint(
        "ck_message_threads_legacy_model_binding",
        "message_threads",
        type_="check",
    )
    op.drop_constraint(
        "ck_message_threads_model_binding_mode",
        "message_threads",
        type_="check",
    )
    op.drop_column("message_threads", "model_binding_mode")
