"""add external auth verification reservations

Revision ID: 20260726_0062
Revises: 20260726_0061
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0062"
down_revision: str | None = "20260726_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "auth_external_verification_reservations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_class", sa.String(length=20), nullable=True),
        sa.CheckConstraint(
            "provider IN ('google')",
            name="ck_auth_external_verification_provider",
        ),
        sa.CheckConstraint(
            "outcome_class IS NULL OR "
            "outcome_class IN ('success','invalid','error')",
            name="ck_auth_external_verification_outcome",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_external_verification_provider_source_created",
        "auth_external_verification_reservations",
        ["provider", "source_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_external_verification_provider_lease",
        "auth_external_verification_reservations",
        ["provider", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_external_verification_provider_lease",
        table_name="auth_external_verification_reservations",
    )
    op.drop_index(
        "ix_auth_external_verification_provider_source_created",
        table_name="auth_external_verification_reservations",
    )
    op.drop_table("auth_external_verification_reservations")
