"""add service image mode and quota reservations

Revision ID: 20260620_0053
Revises: 20260618_0052
Create Date: 2026-06-20 00:53:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260620_0053"
down_revision: Union[str, None] = "20260618_0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_image_generation_settings",
        sa.Column(
            "image_key_mode",
            sa.String(length=20),
            nullable=False,
            server_default="disabled",
        ),
    )
    op.execute(
        """
        UPDATE agent_image_generation_settings
           SET image_key_mode = CASE
                 WHEN image_generation_enabled = true
                  AND encrypted_pollinations_api_key IS NOT NULL
                 THEN 'user'
                 ELSE 'disabled'
               END,
               image_generation_enabled = CASE
                 WHEN image_generation_enabled = true
                  AND encrypted_pollinations_api_key IS NOT NULL
                 THEN true
                 ELSE false
               END
        """
    )
    op.alter_column(
        "agent_image_generation_settings",
        "image_key_mode",
        server_default=None,
    )

    op.add_column(
        "post_media",
        sa.Column(
            "key_source",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )
    op.alter_column("post_media", "key_source", server_default=None)

    op.create_table(
        "post_image_quota_reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("character_id", sa.String(), nullable=False),
        sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("key_source", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("post_id", sa.String(length=64), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_post_image_quota_reservations_character_id"),
        "post_image_quota_reservations",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        "ix_post_image_quota_reservations_user_date_source_status",
        "post_image_quota_reservations",
        ["user_id", "quota_date", "key_source", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_post_image_quota_reservations_post_id"),
        "post_image_quota_reservations",
        ["post_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_post_image_quota_reservations_job_id"),
        "post_image_quota_reservations",
        ["job_id"],
        unique=False,
    )

    op.add_column(
        "post_image_generation_jobs",
        sa.Column("user_id", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE post_image_generation_jobs AS jobs
           SET user_id = characters.owner_id
          FROM characters
         WHERE jobs.character_id = characters.id
        """
    )
    op.alter_column("post_image_generation_jobs", "user_id", nullable=False)
    op.create_index(
        op.f("ix_post_image_generation_jobs_user_id"),
        "post_image_generation_jobs",
        ["user_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_post_image_generation_jobs_user_id_users",
        "post_image_generation_jobs",
        "users",
        ["user_id"],
        ["id"],
    )
    op.add_column(
        "post_image_generation_jobs",
        sa.Column(
            "key_source",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )
    op.alter_column("post_image_generation_jobs", "key_source", server_default=None)
    op.add_column(
        "post_image_generation_jobs",
        sa.Column("quota_reservation_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_post_image_generation_jobs_quota_reservation_id",
        "post_image_generation_jobs",
        "post_image_quota_reservations",
        ["quota_reservation_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_post_image_generation_jobs_quota_reservation_id",
        "post_image_generation_jobs",
        type_="foreignkey",
    )
    op.drop_column("post_image_generation_jobs", "quota_reservation_id")
    op.drop_column("post_image_generation_jobs", "key_source")
    op.drop_constraint(
        "fk_post_image_generation_jobs_user_id_users",
        "post_image_generation_jobs",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_post_image_generation_jobs_user_id"),
        table_name="post_image_generation_jobs",
    )
    op.drop_column("post_image_generation_jobs", "user_id")

    op.drop_index(
        op.f("ix_post_image_quota_reservations_job_id"),
        table_name="post_image_quota_reservations",
    )
    op.drop_index(
        op.f("ix_post_image_quota_reservations_post_id"),
        table_name="post_image_quota_reservations",
    )
    op.drop_index(
        "ix_post_image_quota_reservations_user_date_source_status",
        table_name="post_image_quota_reservations",
    )
    op.drop_index(
        op.f("ix_post_image_quota_reservations_character_id"),
        table_name="post_image_quota_reservations",
    )
    op.drop_table("post_image_quota_reservations")

    op.drop_column("post_media", "key_source")
    op.drop_column("agent_image_generation_settings", "image_key_mode")
