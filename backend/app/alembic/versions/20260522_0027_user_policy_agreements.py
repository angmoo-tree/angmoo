"""Add user policy agreement records

Revision ID: 20260522_0027
Revises: 20260522_0026
Create Date: 2026-05-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260522_0027"
down_revision: str | None = "20260522_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("privacy_policy_agreed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("terms_agreed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users", sa.Column("privacy_policy_version", sa.String(length=40), nullable=True)
    )
    op.add_column("users", sa.Column("terms_version", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "terms_version")
    op.drop_column("users", "privacy_policy_version")
    op.drop_column("users", "terms_agreed_at")
    op.drop_column("users", "privacy_policy_agreed_at")
