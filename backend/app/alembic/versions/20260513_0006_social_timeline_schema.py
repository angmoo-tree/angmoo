"""add social timeline schema

Revision ID: 20260513_0006
Revises: 20260513_0005
Create Date: 2026-05-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260513_0006"
down_revision: str | None = "20260513_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("reply_to_post_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column("quote_post_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column("repost_of_post_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "posts",
        sa.Column(
            "post_type",
            sa.String(length=20),
            server_default=sa.text("'post'"),
            nullable=False,
        ),
    )
    op.add_column(
        "posts",
        sa.Column(
            "visibility",
            sa.String(length=20),
            server_default=sa.text("'public'"),
            nullable=False,
        ),
    )
    op.add_column(
        "posts",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "posts",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_posts_reply_to_post_id",
        "posts",
        "posts",
        ["reply_to_post_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_posts_quote_post_id",
        "posts",
        "posts",
        ["quote_post_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_posts_repost_of_post_id",
        "posts",
        "posts",
        ["repost_of_post_id"],
        ["id"],
    )
    op.create_index("ix_posts_author_character_id", "posts", ["author_character_id"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])
    op.create_index("ix_posts_reply_to_post_id", "posts", ["reply_to_post_id"])

    op.alter_column("post_likes", "character_id", nullable=True)

    op.create_table(
        "post_reposts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("character_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(user_id is null) <> (character_id is null)",
            name="ck_post_reposts_actor_exactly_one",
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "character_id", name="uq_post_reposts_post_character"),
        sa.UniqueConstraint("post_id", "user_id", name="uq_post_reposts_post_user"),
    )
    op.create_index("ix_post_reposts_character_id", "post_reposts", ["character_id"])
    op.create_index("ix_post_reposts_created_at", "post_reposts", ["created_at"])
    op.create_index("ix_post_reposts_post_id", "post_reposts", ["post_id"])

    op.create_table(
        "profile_follows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("follower_user_id", sa.String(length=64), nullable=True),
        sa.Column("follower_character_id", sa.String(length=64), nullable=True),
        sa.Column("target_user_id", sa.String(length=64), nullable=True),
        sa.Column("target_character_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(follower_user_id is null) <> (follower_character_id is null)",
            name="ck_profile_follows_follower_exactly_one",
        ),
        sa.CheckConstraint(
            "(target_user_id is null) <> (target_character_id is null)",
            name="ck_profile_follows_target_exactly_one",
        ),
        sa.ForeignKeyConstraint(["follower_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["follower_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "follower_character_id",
            "target_character_id",
            name="uq_profile_follows_character_character",
        ),
        sa.UniqueConstraint(
            "follower_character_id",
            "target_user_id",
            name="uq_profile_follows_character_user",
        ),
        sa.UniqueConstraint(
            "follower_user_id",
            "target_character_id",
            name="uq_profile_follows_user_character",
        ),
        sa.UniqueConstraint(
            "follower_user_id", "target_user_id", name="uq_profile_follows_user_user"
        ),
    )
    op.create_index(
        "ix_profile_follows_follower_character_id",
        "profile_follows",
        ["follower_character_id"],
    )
    op.create_index(
        "ix_profile_follows_target_character_id",
        "profile_follows",
        ["target_character_id"],
    )
    op.create_index("ix_profile_follows_target_user_id", "profile_follows", ["target_user_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient_user_id", sa.String(length=64), nullable=True),
        sa.Column("recipient_character_id", sa.String(length=64), nullable=True),
        sa.Column("actor_user_id", sa.String(length=64), nullable=True),
        sa.Column("actor_character_id", sa.String(length=64), nullable=True),
        sa.Column("notification_type", sa.String(length=40), nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=True),
        sa.Column("source_post_id", sa.String(length=64), nullable=True),
        sa.Column("data", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(recipient_user_id is null) <> (recipient_character_id is null)",
            name="ck_notifications_recipient_exactly_one",
        ),
        sa.ForeignKeyConstraint(["actor_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["recipient_character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_recipient_character_id",
        "notifications",
        ["recipient_character_id"],
    )
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_index("ix_notifications_recipient_character_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_profile_follows_target_user_id", table_name="profile_follows")
    op.drop_index("ix_profile_follows_target_character_id", table_name="profile_follows")
    op.drop_index("ix_profile_follows_follower_character_id", table_name="profile_follows")
    op.drop_table("profile_follows")

    op.drop_index("ix_post_reposts_post_id", table_name="post_reposts")
    op.drop_index("ix_post_reposts_created_at", table_name="post_reposts")
    op.drop_index("ix_post_reposts_character_id", table_name="post_reposts")
    op.drop_table("post_reposts")

    op.alter_column("post_likes", "character_id", nullable=False)

    op.drop_index("ix_posts_reply_to_post_id", table_name="posts")
    op.drop_index("ix_posts_created_at", table_name="posts")
    op.drop_index("ix_posts_author_character_id", table_name="posts")
    op.drop_constraint("fk_posts_repost_of_post_id", "posts", type_="foreignkey")
    op.drop_constraint("fk_posts_quote_post_id", "posts", type_="foreignkey")
    op.drop_constraint("fk_posts_reply_to_post_id", "posts", type_="foreignkey")
    op.drop_column("posts", "deleted_at")
    op.drop_column("posts", "updated_at")
    op.drop_column("posts", "visibility")
    op.drop_column("posts", "post_type")
    op.drop_column("posts", "repost_of_post_id")
    op.drop_column("posts", "quote_post_id")
    op.drop_column("posts", "reply_to_post_id")
