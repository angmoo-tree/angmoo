"""add profile image daily quota and candidates

Revision ID: 20260705_0058
Revises: 20260627_0057
Create Date: 2026-07-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260705_0058"
down_revision: str | None = "20260627_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_image_quota_reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("bucket", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("candidate_id", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("route_mode", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_profile_image_quota_reservations_user_id"),
        "profile_image_quota_reservations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_image_quota_reservations_quota_date"),
        "profile_image_quota_reservations",
        ["quota_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_image_quota_reservations_bucket"),
        "profile_image_quota_reservations",
        ["bucket"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_image_quota_reservations_candidate_id"),
        "profile_image_quota_reservations",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_profile_image_quota_user_date_bucket_status",
        "profile_image_quota_reservations",
        ["user_id", "quota_date", "bucket", "status"],
        unique=False,
    )

    op.create_table(
        "profile_image_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("draft_id", sa.String(length=64), nullable=True),
        sa.Column("character_id", sa.String(length=64), nullable=True),
        sa.Column("quota_reservation_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("bucket", sa.String(length=40), nullable=False),
        sa.Column("media_type", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("route_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["draft_id"], ["agent_creation_drafts.id"]),
        sa.ForeignKeyConstraint(
            ["quota_reservation_id"], ["profile_image_quota_reservations.id"]
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_profile_image_candidates_user_id"),
        "profile_image_candidates",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_image_candidates_draft_id"),
        "profile_image_candidates",
        ["draft_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_image_candidates_character_id"),
        "profile_image_candidates",
        ["character_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_image_candidates_quota_reservation_id"),
        "profile_image_candidates",
        ["quota_reservation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_profile_image_candidates_bucket"),
        "profile_image_candidates",
        ["bucket"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_profile_image_candidates_bucket"), table_name="profile_image_candidates")
    op.drop_index(
        op.f("ix_profile_image_candidates_quota_reservation_id"),
        table_name="profile_image_candidates",
    )
    op.drop_index(
        op.f("ix_profile_image_candidates_character_id"),
        table_name="profile_image_candidates",
    )
    op.drop_index(
        op.f("ix_profile_image_candidates_draft_id"),
        table_name="profile_image_candidates",
    )
    op.drop_index(op.f("ix_profile_image_candidates_user_id"), table_name="profile_image_candidates")
    op.drop_table("profile_image_candidates")
    op.drop_index(
        "ix_profile_image_quota_user_date_bucket_status",
        table_name="profile_image_quota_reservations",
    )
    op.drop_index(
        op.f("ix_profile_image_quota_reservations_candidate_id"),
        table_name="profile_image_quota_reservations",
    )
    op.drop_index(
        op.f("ix_profile_image_quota_reservations_bucket"),
        table_name="profile_image_quota_reservations",
    )
    op.drop_index(
        op.f("ix_profile_image_quota_reservations_quota_date"),
        table_name="profile_image_quota_reservations",
    )
    op.drop_index(
        op.f("ix_profile_image_quota_reservations_user_id"),
        table_name="profile_image_quota_reservations",
    )
    op.drop_table("profile_image_quota_reservations")
