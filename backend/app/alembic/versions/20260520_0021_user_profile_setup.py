"""add user profile setup fields

Revision ID: 20260520_0021
Revises: 20260520_0020
Create Date: 2026-05-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0021"
down_revision: str | None = "20260520_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "profile_setup_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("display_name_normalized", sa.String(length=80), nullable=True),
    )
    op.execute(
        sa.text(
            """
            update users
            set display_name_normalized = lower(regexp_replace(btrim(display_name), '\\s+', ' ', 'g'))
            where display_name is not null and btrim(display_name) <> ''
            """
        )
    )
    op.create_unique_constraint(
        "uq_users_display_name_normalized", "users", ["display_name_normalized"]
    )
    op.alter_column("users", "profile_setup_completed", server_default=None)


def downgrade() -> None:
    op.drop_constraint("uq_users_display_name_normalized", "users", type_="unique")
    op.drop_column("users", "display_name_normalized")
    op.drop_column("users", "profile_setup_completed")
