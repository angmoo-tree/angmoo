"""add runtime scheduler singleton lease

Revision ID: 20260816_0080
Revises: 20260815_0079
Create Date: 2026-08-16
"""

from collections.abc import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "20260816_0080"
down_revision: str | None = "20260815_0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO installation_identities (
                singleton_key,
                installation_id,
                bootstrap_state,
                created_at,
                updated_at
            )
            SELECT
                'local-installation',
                :installation_id,
                'unclaimed',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1
                FROM installation_identities
                WHERE singleton_key = 'local-installation'
            )
            """
        ),
        {"installation_id": str(uuid4())},
    )
    op.create_table(
        "runtime_scheduler_leases",
        sa.Column("singleton_key", sa.String(length=40), nullable=False),
        sa.Column("installation_id", sa.String(length=64), nullable=False),
        sa.Column("lease_owner_id", sa.String(length=128), nullable=True),
        sa.Column("fencing_epoch", sa.Integer(), server_default="0", nullable=False),
        sa.Column("state", sa.String(length=20), server_default="stopped", nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sleep_gap_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_tick_window_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tick_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tick_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tick_result", sa.String(length=20), nullable=True),
        sa.Column("next_tick_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("shutdown_requested_at", sa.DateTime(timezone=True), nullable=True),
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
            "singleton_key = 'resident-tick-scheduler'",
            name="ck_runtime_scheduler_leases_singleton",
        ),
        sa.CheckConstraint(
            "state IN ('starting','active','draining','stopped','failed')",
            name="ck_runtime_scheduler_leases_state",
        ),
        sa.CheckConstraint(
            "fencing_epoch >= 0",
            name="ck_runtime_scheduler_leases_fencing_epoch",
        ),
        sa.CheckConstraint(
            "last_tick_result IS NULL OR last_tick_result IN "
            "('success','no_action','partial','failed','skipped')",
            name="ck_runtime_scheduler_leases_tick_result",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["installation_identities.installation_id"],
        ),
        sa.PrimaryKeyConstraint("singleton_key"),
        sa.UniqueConstraint("installation_id"),
    )


def downgrade() -> None:
    op.drop_table("runtime_scheduler_leases")
