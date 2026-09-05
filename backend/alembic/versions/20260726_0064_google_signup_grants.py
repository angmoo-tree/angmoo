"""add one-time google signup grants

Revision ID: 20260726_0064
Revises: 20260726_0063
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0064"
down_revision: str | None = "20260726_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "auth_google_signup_grants",
        sa.Column("jti_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("jti_hash"),
    )
    op.create_index(
        "ix_auth_google_signup_grants_expires_at",
        "auth_google_signup_grants",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_google_signup_grants_expires_at",
        table_name="auth_google_signup_grants",
    )
    op.drop_table("auth_google_signup_grants")
