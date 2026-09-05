"""add tree owner community tables

Revision ID: 20260520_0019
Revises: 20260519_0018
Create Date: 2026-05-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0019"
down_revision: str | None = "20260519_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tree_posts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_user_id", sa.String(length=64), nullable=False),
        sa.Column("related_character_id", sa.String(length=64), nullable=True),
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
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category in ('notice', 'bug', 'suggestion', 'question', 'free')",
            name="ck_tree_posts_category",
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["related_character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tree_posts_category_created_at",
        "tree_posts",
        ["category", "created_at"],
    )
    op.create_table(
        "tree_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=False),
        sa.Column("author_user_id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["tree_posts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tree_comments_post_created_at",
        "tree_comments",
        ["post_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tree_comments_post_created_at", table_name="tree_comments")
    op.drop_table("tree_comments")
    op.drop_index("ix_tree_posts_category_created_at", table_name="tree_posts")
    op.drop_table("tree_posts")
