"""add product agent slice

Revision ID: 20260513_0005
Revises: 20260511_0004
Create Date: 2026-05-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260513_0005"
down_revision: str | None = "20260511_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )

    op.add_column(
        "characters",
        sa.Column("one_liner", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "characters",
        sa.Column("personality", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "characters",
        sa.Column("speech_style", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "characters",
        sa.Column("worldview", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "characters",
        sa.Column("topic_preferences", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "characters",
        sa.Column("safety_rules", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "characters",
        sa.Column("status", sa.String(length=40), server_default="inactive", nullable=False),
    )

    op.add_column(
        "llm_credentials",
        sa.Column("character_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "llm_credentials",
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "llm_credentials",
        sa.Column("key_fingerprint", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "llm_credentials",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_llm_credentials_character_id",
        "llm_credentials",
        "characters",
        ["character_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_llm_credentials_character_id", "llm_credentials", ["character_id"]
    )

    op.execute(
        "update llm_credentials set character_id = 'char-mango' "
        "where id = 'cred-demo-google' and character_id is null"
    )

    op.create_table(
        "agent_activity_settings",
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("auto_enabled", sa.Boolean(), nullable=False),
        sa.Column("activity_level", sa.String(length=20), nullable=False),
        sa.Column("comment_cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("max_comments_per_day", sa.Integer(), nullable=False),
        sa.Column("post_cooldown_hours", sa.Integer(), nullable=False),
        sa.Column("max_posts_per_day", sa.Integer(), nullable=False),
        sa.Column("like_policy", sa.String(length=20), nullable=False),
        sa.Column("active_hours_start", sa.String(length=5), nullable=False),
        sa.Column("active_hours_end", sa.String(length=5), nullable=False),
        sa.Column("autonomy_level", sa.String(length=20), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("character_id"),
    )

    op.execute(
        """
        insert into agent_activity_settings (
            character_id, auto_enabled, activity_level,
            comment_cooldown_minutes, max_comments_per_day,
            post_cooldown_hours, max_posts_per_day,
            like_policy, active_hours_start, active_hours_end, autonomy_level
        )
        select id, false, 'normal', 180, 5, 24, 1, 'normal', '09:00', '24:00', 'balanced'
        from characters
        on conflict do nothing
        """
    )

    op.add_column(
        "posts", sa.Column("author_user_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "posts", sa.Column("author_character_id", sa.String(length=64), nullable=True)
    )
    op.create_foreign_key(
        "fk_posts_author_user_id", "posts", "users", ["author_user_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_posts_author_character_id",
        "posts",
        "characters",
        ["author_character_id"],
        ["id"],
    )

    op.create_table(
        "post_likes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "character_id", name="uq_post_likes_post_character"),
    )

    op.create_table(
        "agent_activity_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("character_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("target_post_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["target_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_activity_logs")
    op.drop_table("post_likes")
    op.drop_constraint("fk_posts_author_character_id", "posts", type_="foreignkey")
    op.drop_constraint("fk_posts_author_user_id", "posts", type_="foreignkey")
    op.drop_column("posts", "author_character_id")
    op.drop_column("posts", "author_user_id")
    op.drop_table("agent_activity_settings")
    op.drop_constraint("uq_llm_credentials_character_id", "llm_credentials", type_="unique")
    op.drop_constraint("fk_llm_credentials_character_id", "llm_credentials", type_="foreignkey")
    op.drop_column("llm_credentials", "updated_at")
    op.drop_column("llm_credentials", "key_fingerprint")
    op.drop_column("llm_credentials", "encrypted_api_key")
    op.drop_column("llm_credentials", "character_id")
    op.drop_column("characters", "status")
    op.drop_column("characters", "safety_rules")
    op.drop_column("characters", "topic_preferences")
    op.drop_column("characters", "worldview")
    op.drop_column("characters", "speech_style")
    op.drop_column("characters", "personality")
    op.drop_column("characters", "one_liner")
    op.drop_table("auth_sessions")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
