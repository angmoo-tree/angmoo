"""add durable Local Bot quota buckets

Revision ID: 20260726_0060
Revises: 20260721_0059
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0060"
down_revision: str | None = "20260721_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "local_bot_action_quota_buckets",
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("action_label", sa.String(length=24), nullable=False),
        sa.Column("quota_date", sa.Date(), nullable=True),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action_label IN "
            "('follow','like','post','reaction','reply','repost','state','unfollow')",
            name="ck_local_bot_action_quota_label",
        ),
        sa.CheckConstraint(
            "used_count >= 0",
            name="ck_local_bot_action_quota_used_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("character_id", "action_label"),
    )
    op.create_table(
        "local_bot_read_quota_buckets",
        sa.Column("local_key_id", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "used_count >= 0",
            name="ck_local_bot_read_quota_used_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["local_key_id"],
            ["agent_local_keys.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("local_key_id"),
    )


def downgrade() -> None:
    op.drop_table("local_bot_read_quota_buckets")
    op.drop_table("local_bot_action_quota_buckets")
