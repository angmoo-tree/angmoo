"""add community mutation quota buckets

Revision ID: 20260726_0065
Revises: 20260726_0064
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0065"
down_revision: str | None = "20260726_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "community_mutation_quota_buckets",
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('reply_minute','reply_day','report_10m','report_day')",
            name="ck_community_mutation_quota_scope",
        ),
        sa.CheckConstraint(
            "used_count >= 0",
            name="ck_community_mutation_quota_used_nonnegative",
        ),
        sa.PrimaryKeyConstraint("scope", "subject_hash"),
    )


def downgrade() -> None:
    op.drop_table("community_mutation_quota_buckets")
