"""admin operations and notice controls

Revision ID: 20260614_0042
Revises: 20260610_0041
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260614_0042"
down_revision: str | None = "20260610_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column(
            "auth_method",
            sa.String(length=20),
            nullable=False,
            server_default="password",
        ),
    )
    op.alter_column("auth_sessions", "auth_method", server_default=None)

    op.create_table(
        "site_operation_banners",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("title", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "blocks_auto_ticks",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "blocks_run_now",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "blocks_feed_cues",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("updated_by_user_id", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_user_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.String(length=160), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("request_ip", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_audit_logs_created_at",
        "admin_audit_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_admin_audit_logs_target",
        "admin_audit_logs",
        ["target_type", "target_id"],
    )

    op.add_column(
        "characters",
        sa.Column(
            "moderation_status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column("characters", sa.Column("moderation_reason", sa.String(length=80)))
    op.add_column("characters", sa.Column("moderation_note", sa.Text()))
    op.add_column(
        "characters",
        sa.Column("moderation_updated_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "characters",
        sa.Column("moderation_updated_by_user_id", sa.String(length=64)),
    )
    op.create_foreign_key(
        "fk_characters_moderation_updated_by_user_id",
        "characters",
        "users",
        ["moderation_updated_by_user_id"],
        ["id"],
    )
    op.alter_column("characters", "moderation_status", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "fk_characters_moderation_updated_by_user_id",
        "characters",
        type_="foreignkey",
    )
    op.drop_column("characters", "moderation_updated_by_user_id")
    op.drop_column("characters", "moderation_updated_at")
    op.drop_column("characters", "moderation_note")
    op.drop_column("characters", "moderation_reason")
    op.drop_column("characters", "moderation_status")
    op.drop_index("ix_admin_audit_logs_target", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_table("site_operation_banners")
    op.drop_column("auth_sessions", "auth_method")
