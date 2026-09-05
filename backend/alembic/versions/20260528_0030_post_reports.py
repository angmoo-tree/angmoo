"""add post reports and report hidden state

Revision ID: 20260528_0030
Revises: 20260526_0029
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260528_0030"
down_revision: Union[str, None] = "20260526_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("report_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "posts",
        sa.Column("report_hidden_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "post_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=False),
        sa.Column("reporter_user_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "reporter_user_id", name="uq_post_reports_post_user"),
    )
    op.create_index("ix_post_reports_post_id", "post_reports", ["post_id"])
    op.create_index("ix_post_reports_reporter_user_id", "post_reports", ["reporter_user_id"])


def downgrade() -> None:
    op.drop_index("ix_post_reports_reporter_user_id", table_name="post_reports")
    op.drop_index("ix_post_reports_post_id", table_name="post_reports")
    op.drop_table("post_reports")
    op.drop_column("posts", "report_hidden_at")
    op.drop_column("posts", "report_count")
