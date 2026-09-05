"""add post info metadata

Revision ID: 20260530_0035
Revises: 20260530_0034
Create Date: 2026-05-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260530_0035"
down_revision: Union[str, None] = "20260530_0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("info_kind", sa.String(length=40), nullable=True))
    op.add_column("posts", sa.Column("source_name", sa.String(length=120), nullable=True))
    op.add_column("posts", sa.Column("source_url", sa.String(length=500), nullable=True))
    op.add_column(
        "posts", sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "posts", sa.Column("location_label", sa.String(length=120), nullable=True)
    )
    op.create_check_constraint(
        "ck_posts_info_kind",
        "posts",
        "info_kind is null or info_kind in "
        "('weather', 'news', 'calendar', 'market', 'knowledge', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_posts_info_kind", "posts", type_="check")
    op.drop_column("posts", "location_label")
    op.drop_column("posts", "observed_at")
    op.drop_column("posts", "source_url")
    op.drop_column("posts", "source_name")
    op.drop_column("posts", "info_kind")
