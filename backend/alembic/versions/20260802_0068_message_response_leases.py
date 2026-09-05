"""add message response leases

Revision ID: 20260802_0068
Revises: 20260802_0067
Create Date: 2026-08-02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260802_0068"
down_revision: str | None = "20260802_0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "message_threads",
        sa.Column("response_lease_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "message_threads",
        sa.Column(
            "response_lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_message_threads_response_lease_pair",
        "message_threads",
        "(response_lease_token IS NULL) = "
        "(response_lease_expires_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_message_threads_response_lease_pair",
        "message_threads",
        type_="check",
    )
    op.drop_column("message_threads", "response_lease_expires_at")
    op.drop_column("message_threads", "response_lease_token")
