"""add local owner installation identity and bootstrap challenges

Revision ID: 20260815_0079
Revises: 20260812_0078
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260815_0079"
down_revision: str | None = "20260812_0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "installation_identities",
        sa.Column("singleton_key", sa.String(length=40), nullable=False),
        sa.Column("installation_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("bootstrap_state", sa.String(length=24), nullable=False),
        sa.Column("local_label", sa.String(length=80), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
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
            "singleton_key = 'local-installation'",
            name="ck_installation_identities_singleton",
        ),
        sa.CheckConstraint(
            "bootstrap_state IN ('unclaimed','claimed','recovery_required')",
            name="ck_installation_identities_bootstrap_state",
        ),
        sa.CheckConstraint(
            "(bootstrap_state = 'claimed' AND owner_user_id IS NOT NULL "
            "AND claimed_at IS NOT NULL) OR "
            "(bootstrap_state <> 'claimed')",
            name="ck_installation_identities_claimed_owner",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("singleton_key"),
        sa.UniqueConstraint("installation_id"),
        sa.UniqueConstraint("owner_user_id"),
    )
    op.create_table(
        "local_owner_bootstrap_challenges",
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("installation_key", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 5",
            name="ck_local_owner_bootstrap_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["installation_key"],
            ["installation_identities.singleton_key"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("challenge_hash"),
    )
    op.create_index(
        "ix_local_owner_bootstrap_challenges_active",
        "local_owner_bootstrap_challenges",
        ["installation_key", "expires_at"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM auth_sessions WHERE auth_method = 'local_owner'")
    op.drop_index(
        "ix_local_owner_bootstrap_challenges_active",
        table_name="local_owner_bootstrap_challenges",
    )
    op.drop_table("local_owner_bootstrap_challenges")
    op.drop_table("installation_identities")
