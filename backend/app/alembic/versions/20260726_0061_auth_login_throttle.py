"""add durable password login throttle

Revision ID: 20260726_0061
Revises: 20260726_0060
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0061"
down_revision: str | None = "20260726_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "auth_login_throttle_buckets",
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "scope IN ('source','account_source')",
            name="ck_auth_login_throttle_scope",
        ),
        sa.CheckConstraint(
            "failure_count >= 0",
            name="ck_auth_login_throttle_failure_nonnegative",
        ),
        sa.PrimaryKeyConstraint("scope", "subject_hash"),
    )


def downgrade() -> None:
    op.drop_table("auth_login_throttle_buckets")
