"""add user feed content filter preference

Revision ID: 20260529_0031
Revises: 20260528_0030
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260529_0031"
down_revision: Union[str, None] = "20260528_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "feed_content_filter",
            sa.String(length=20),
            server_default="all",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_feed_content_filter",
        "users",
        "feed_content_filter IN ('all', 'posts', 'reposts')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_feed_content_filter", "users", type_="check")
    op.drop_column("users", "feed_content_filter")
