"""add lore parser leases

Revision ID: 20260726_0066
Revises: 20260726_0065
Create Date: 2026-07-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260726_0066"
down_revision: str | None = "20260726_0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "lore_parser_leases",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("subject_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lore_parser_leases_subject_hash",
        "lore_parser_leases",
        ["subject_hash"],
        unique=False,
    )
    op.create_index(
        "ix_lore_parser_leases_lease_expires_at",
        "lore_parser_leases",
        ["lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lore_parser_leases_lease_expires_at",
        table_name="lore_parser_leases",
    )
    op.drop_index(
        "ix_lore_parser_leases_subject_hash",
        table_name="lore_parser_leases",
    )
    op.drop_table("lore_parser_leases")
