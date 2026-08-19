"""add owner-controlled manual social write and Inbox ledgers

Revision ID: 20260819_0082
Revises: 20260818_0081
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260819_0082"
down_revision: str | None = "20260818_0081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "owner_manual_social_writes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("actor_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("target_post_id", sa.String(length=64), nullable=True),
        sa.Column("result_post_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('post','reply')",
            name="ck_owner_manual_social_writes_operation",
        ),
        sa.CheckConstraint(
            "(operation = 'post' AND target_post_id IS NULL) OR "
            "(operation = 'reply' AND target_post_id IS NOT NULL)",
            name="ck_owner_manual_social_writes_target",
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["target_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["result_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_owner_manual_social_writes_actor_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "world_id",
            "owner_user_id",
            "idempotency_key",
            name="uq_owner_manual_social_writes_request",
        ),
        sa.UniqueConstraint(
            "result_post_id", name="uq_owner_manual_social_writes_result"
        ),
    )
    op.create_index(
        "ix_owner_manual_social_writes_world_created",
        "owner_manual_social_writes",
        ["world_id", "created_at"],
    )

    op.create_table(
        "owner_manual_inbox_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("actor_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("target_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("source_reply_post_id", sa.String(length=64), nullable=False),
        sa.Column("target_post_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("target_activity_beat_id", sa.String(length=64), nullable=True),
        sa.Column("claim_run_id", sa.String(length=64), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason_code", sa.String(length=80), nullable=True),
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
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','claimed','consumed','released','rejected')",
            name="ck_owner_manual_inbox_candidates_status",
        ),
        sa.CheckConstraint(
            "actor_world_character_id != target_world_character_id",
            name="ck_owner_manual_inbox_candidates_not_self",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_owner_manual_inbox_candidates_version"
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["source_reply_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["target_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["target_activity_beat_id"], ["activity_beats.id"]),
        sa.ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_owner_manual_inbox_candidates_actor_scope",
        ),
        sa.ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_owner_manual_inbox_candidates_target_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_reply_post_id",
            "target_world_character_id",
            name="uq_owner_manual_inbox_candidates_source_target",
        ),
    )
    op.create_index(
        "ix_owner_manual_inbox_candidates_target_status",
        "owner_manual_inbox_candidates",
        ["target_world_character_id", "status", "created_at"],
    )
    op.create_index(
        "ix_owner_manual_inbox_candidates_claim_expiry",
        "owner_manual_inbox_candidates",
        ["status", "claim_expires_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "owner_manual_inbox_candidates",
        "owner_manual_social_writes",
    ):
        count = bind.scalar(sa.text(f"SELECT count(*) FROM {table_name}"))
        if int(count or 0) > 0:
            raise RuntimeError(
                f"cannot downgrade 0082 while {table_name} contains L3 rows"
            )
    op.drop_index(
        "ix_owner_manual_inbox_candidates_claim_expiry",
        table_name="owner_manual_inbox_candidates",
    )
    op.drop_index(
        "ix_owner_manual_inbox_candidates_target_status",
        table_name="owner_manual_inbox_candidates",
    )
    op.drop_table("owner_manual_inbox_candidates")
    op.drop_index(
        "ix_owner_manual_social_writes_world_created",
        table_name="owner_manual_social_writes",
    )
    op.drop_table("owner_manual_social_writes")
