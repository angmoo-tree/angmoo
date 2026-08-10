"""add world-scoped routine continuous posts

Revision ID: 20260810_0075
Revises: 20260809_0074
Create Date: 2026-08-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260810_0075"
down_revision: str | None = "20260809_0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "world_characters",
        sa.Column(
            "activity_runtime_mode",
            sa.String(length=32),
            server_default="legacy_resident_v1",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_world_characters_activity_runtime_mode",
        "world_characters",
        "activity_runtime_mode IN ('legacy_resident_v1','routine_resident_v1')",
    )

    op.add_column(
        "posts",
        sa.Column("world_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column("author_world_character_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_posts_world",
        "posts",
        "worlds",
        ["world_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_posts_author_world_character_scope",
        "posts",
        "world_characters",
        ["author_world_character_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_foreign_key(
        "fk_posts_author_world_character_identity",
        "posts",
        "world_characters",
        ["author_world_character_id", "author_character_id"],
        ["id", "character_id"],
    )
    op.create_check_constraint(
        "ck_posts_world_scope_pair",
        "posts",
        "(world_id IS NULL AND author_world_character_id IS NULL) OR "
        "(world_id IS NOT NULL AND author_world_character_id IS NOT NULL)",
    )
    op.create_index(
        "ix_posts_world_created_at",
        "posts",
        ["world_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    scoped_posts = bind.scalar(
        sa.text(
            "SELECT count(*) FROM posts "
            "WHERE world_id IS NOT NULL OR author_world_character_id IS NOT NULL"
        )
    )
    routine_characters = bind.scalar(
        sa.text(
            "SELECT count(*) FROM world_characters "
            "WHERE activity_runtime_mode != 'legacy_resident_v1'"
        )
    )
    if int(scoped_posts or 0) > 0 or int(routine_characters or 0) > 0:
        raise RuntimeError(
            "cannot downgrade 0075 while routine-scoped posts or runtime modes exist"
        )

    op.drop_index("ix_posts_world_created_at", table_name="posts")
    op.drop_constraint("ck_posts_world_scope_pair", "posts", type_="check")
    op.drop_constraint(
        "fk_posts_author_world_character_identity", "posts", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_posts_author_world_character_scope", "posts", type_="foreignkey"
    )
    op.drop_constraint("fk_posts_world", "posts", type_="foreignkey")
    op.drop_column("posts", "author_world_character_id")
    op.drop_column("posts", "world_id")

    op.drop_constraint(
        "ck_world_characters_activity_runtime_mode",
        "world_characters",
        type_="check",
    )
    op.drop_column("world_characters", "activity_runtime_mode")
