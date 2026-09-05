"""add deterministic daily activity runtime

Revision ID: 20260809_0074
Revises: 20260808_0073
Create Date: 2026-08-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260809_0074"
down_revision: str | None = "20260808_0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None

JSON_DOCUMENT = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()), "postgresql"
)


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_world_characters_id_world",
        "world_characters",
        ["id", "world_id"],
    )

    op.create_table(
        "daily_activity_plans",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone_name", sa.String(length=64), nullable=False),
        sa.Column("timezone_contract_version", sa.String(length=40), nullable=False),
        sa.Column("repertoire_id", sa.String(length=64), nullable=False),
        sa.Column("world_definition_hash", sa.String(length=64), nullable=False),
        sa.Column("character_definition_hash", sa.String(length=64), nullable=False),
        sa.Column("repertoire_contract_version", sa.String(length=40), nullable=False),
        sa.Column("selection_contract_version", sa.String(length=40), nullable=False),
        sa.Column("selection_seed_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned','active','completed','interrupted','cancelled')",
            name="ck_daily_activity_plans_status",
        ),
        sa.CheckConstraint(
            "revision_count >= 0 AND revision_count <= 2",
            name="ck_daily_activity_plans_revision_count",
        ),
        sa.CheckConstraint("version >= 1", name="ck_daily_activity_plans_version"),
        sa.ForeignKeyConstraint(
            ["repertoire_id"], ["world_activity_repertoires.id"]
        ),
        sa.ForeignKeyConstraint(
            ["world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_daily_activity_plans_world_character_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "world_character_id",
            "local_date",
            name="uq_daily_activity_plans_character_date",
        ),
        sa.UniqueConstraint(
            "id",
            "world_id",
            "world_character_id",
            name="uq_daily_activity_plans_scope",
        ),
    )
    op.create_index(
        "ix_daily_activity_plans_world_date",
        "daily_activity_plans",
        ["world_id", "local_date"],
    )

    op.create_table(
        "joint_activities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("activity_seed", sa.String(length=500), nullable=False),
        sa.Column("place_key", sa.String(length=64), nullable=True),
        sa.Column("schedule_mode", sa.String(length=20), nullable=False),
        sa.Column("eligible_dayparts", JSON_DOCUMENT, nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=28), nullable=False),
        sa.Column("source_proposal_event_id", sa.String(length=64), nullable=True),
        sa.Column("source_acceptance_event_id", sa.String(length=64), nullable=True),
        sa.Column("representation_post_id", sa.String(length=64), nullable=True),
        sa.Column(
            "represented_by_world_character_id", sa.String(length=64), nullable=True
        ),
        sa.Column("represented_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "schedule_mode IN ('exact','window','flexible')",
            name="ck_joint_activities_schedule_mode",
        ),
        sa.CheckConstraint(
            "status IN ('accepted_unscheduled','scheduled','ready','represented',"
            "'completed','cancelled','expired','interrupted')",
            name="ck_joint_activities_status",
        ),
        sa.CheckConstraint(
            "scheduled_start_at IS NULL OR scheduled_end_at IS NULL "
            "OR scheduled_start_at < scheduled_end_at",
            name="ck_joint_activities_scheduled_window",
        ),
        sa.CheckConstraint("version >= 1", name="ck_joint_activities_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["representation_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(
            ["represented_by_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_joint_activities_represented_by_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "world_id", name="uq_joint_activities_scope"),
        sa.UniqueConstraint("representation_post_id"),
    )
    op.create_index(
        "ix_joint_activities_world_status",
        "joint_activities",
        ["world_id", "status"],
    )

    op.create_table(
        "daily_activity_plan_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("daypart", sa.String(length=20), nullable=False),
        sa.Column("selected_candidate_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_signature", sa.String(length=64), nullable=False),
        sa.Column("candidate_ordinal", sa.Integer(), nullable=False),
        sa.Column("activity_kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("activity_seed", sa.String(length=500), nullable=False),
        sa.Column("social_mode", sa.String(length=32), nullable=False),
        sa.Column("place_key", sa.String(length=64), nullable=True),
        sa.Column("joint_activity_id", sa.String(length=64), nullable=True),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("revision_count", sa.Integer(), nullable=False),
        sa.Column("terminal_reason_code", sa.String(length=80), nullable=True),
        *_timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_daily_activity_plan_items_daypart",
        ),
        sa.CheckConstraint(
            "status IN ('planned','active','completed','skipped','interrupted','cancelled')",
            name="ck_daily_activity_plan_items_status",
        ),
        sa.CheckConstraint(
            "revision_count >= 0 AND revision_count <= 1",
            name="ck_daily_activity_plan_items_revision_count",
        ),
        sa.CheckConstraint(
            "scheduled_start_at < scheduled_end_at",
            name="ck_daily_activity_plan_items_window",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_daily_activity_plan_items_version"
        ),
        sa.ForeignKeyConstraint(
            ["joint_activity_id", "world_id"],
            ["joint_activities.id", "joint_activities.world_id"],
            name="fk_daily_activity_plan_items_joint_scope",
        ),
        sa.ForeignKeyConstraint(
            ["selected_candidate_id"], ["world_activity_candidates.id"]
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "world_id", "world_character_id"],
            [
                "daily_activity_plans.id",
                "daily_activity_plans.world_id",
                "daily_activity_plans.world_character_id",
            ],
            name="fk_daily_activity_plan_items_plan_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "daypart", name="uq_daily_activity_plan_items_daypart"
        ),
        sa.UniqueConstraint(
            "id",
            "world_id",
            "world_character_id",
            name="uq_daily_activity_plan_items_scope",
        ),
    )
    op.create_index(
        "ix_daily_activity_plan_items_character_window",
        "daily_activity_plan_items",
        ["world_character_id", "scheduled_start_at", "scheduled_end_at"],
    )

    op.create_table(
        "activity_episodes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("plan_item_id", sa.String(length=64), nullable=False),
        sa.Column("effective_activity_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_state_schema_version", sa.Integer(), nullable=False),
        sa.Column("current_state_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("last_successful_beat_id", sa.String(length=64), nullable=True),
        sa.Column("next_sequence_no", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_summary", JSON_DOCUMENT, nullable=True),
        sa.Column("terminal_reason_code", sa.String(length=80), nullable=True),
        *_timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned','active','completed','interrupted','cancelled')",
            name="ck_activity_episodes_status",
        ),
        sa.CheckConstraint(
            "next_sequence_no >= 1", name="ck_activity_episodes_sequence"
        ),
        sa.CheckConstraint("version >= 1", name="ck_activity_episodes_version"),
        sa.ForeignKeyConstraint(
            ["plan_item_id", "world_id", "world_character_id"],
            [
                "daily_activity_plan_items.id",
                "daily_activity_plan_items.world_id",
                "daily_activity_plan_items.world_character_id",
            ],
            name="fk_activity_episodes_item_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_item_id", name="uq_activity_episodes_plan_item"
        ),
        sa.UniqueConstraint(
            "id",
            "world_id",
            "world_character_id",
            name="uq_activity_episodes_scope",
        ),
    )
    op.create_index(
        "uq_activity_episodes_active_character",
        "activity_episodes",
        ["world_character_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "activity_beats",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("episode_id", sa.String(length=64), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger_kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("previous_successful_beat_id", sa.String(length=64), nullable=True),
        sa.Column("source_post_id", sa.String(length=64), nullable=True),
        sa.Column("source_event_ids", JSON_DOCUMENT, nullable=False),
        sa.Column("state_before_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("state_after_snapshot", JSON_DOCUMENT, nullable=True),
        sa.Column("result_snapshot", JSON_DOCUMENT, nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("claim_run_id", sa.String(length=64), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("skipped_tick_count", sa.Integer(), nullable=False),
        sa.Column("failure_reason_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "trigger_kind IN ('scheduled','comment_influenced','joint_activity')",
            name="ck_activity_beats_trigger_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending','claimed','succeeded','failed','cancelled','skipped')",
            name="ck_activity_beats_status",
        ),
        sa.CheckConstraint("sequence_no >= 1", name="ck_activity_beats_sequence"),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_activity_beats_attempt_count"
        ),
        sa.CheckConstraint(
            "skipped_tick_count >= 0", name="ck_activity_beats_skipped_count"
        ),
        sa.CheckConstraint(
            "status != 'failed' OR (state_after_snapshot IS NULL AND source_post_id IS NULL)",
            name="ck_activity_beats_failed_no_success_state",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id", "world_id", "world_character_id"],
            [
                "activity_episodes.id",
                "activity_episodes.world_id",
                "activity_episodes.world_character_id",
            ],
            name="fk_activity_beats_episode_scope",
        ),
        sa.ForeignKeyConstraint(
            ["previous_successful_beat_id"], ["activity_beats.id"]
        ),
        sa.ForeignKeyConstraint(["source_post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "episode_id", "sequence_no", name="uq_activity_beats_sequence"
        ),
        sa.UniqueConstraint(
            "world_character_id",
            "scheduled_for",
            "idempotency_key",
            name="uq_activity_beats_request",
        ),
    )
    op.create_index(
        "ix_activity_beats_claim_expiry",
        "activity_beats",
        ["status", "claim_expires_at"],
    )

    op.create_table(
        "activity_event_consumptions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("consumer_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("source_social_event_id", sa.String(length=64), nullable=False),
        sa.Column("namespace", sa.String(length=40), nullable=False),
        sa.Column("target_activity_beat_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("claim_run_id", sa.String(length=64), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason_code", sa.String(length=80), nullable=True),
        *_timestamps(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "namespace IN ('next_activity_beat')",
            name="ck_activity_event_consumptions_namespace",
        ),
        sa.CheckConstraint(
            "status IN ('claimed','applied','released','rejected')",
            name="ck_activity_event_consumptions_status",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_activity_event_consumptions_version"
        ),
        sa.ForeignKeyConstraint(
            ["consumer_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_activity_event_consumptions_character_scope",
        ),
        sa.ForeignKeyConstraint(
            ["target_activity_beat_id"], ["activity_beats.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "consumer_world_character_id",
            "source_social_event_id",
            "namespace",
            name="uq_activity_event_consumptions_event_namespace",
        ),
    )
    op.create_index(
        "ix_activity_event_consumptions_claim_expiry",
        "activity_event_consumptions",
        ["status", "claim_expires_at"],
    )

    op.create_table(
        "activity_plan_revisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("plan_item_id", sa.String(length=64), nullable=False),
        sa.Column("joint_activity_id", sa.String(length=64), nullable=False),
        sa.Column("revision_ordinal", sa.Integer(), nullable=False),
        sa.Column("before_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("after_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("source_acceptance_event_id", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision_ordinal >= 1 AND revision_ordinal <= 2",
            name="ck_activity_plan_revisions_ordinal",
        ),
        sa.ForeignKeyConstraint(["joint_activity_id"], ["joint_activities.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["daily_activity_plans.id"]),
        sa.ForeignKeyConstraint(
            ["plan_item_id"], ["daily_activity_plan_items.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id",
            "revision_ordinal",
            name="uq_activity_plan_revisions_ordinal",
        ),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_activity_plan_revisions_request"
        ),
    )
    op.create_index(
        "ix_activity_plan_revisions_item",
        "activity_plan_revisions",
        ["plan_item_id", "applied_at"],
    )

    op.create_table(
        "joint_activity_participants",
        sa.Column("joint_activity_id", sa.String(length=64), nullable=False),
        sa.Column("world_character_id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("participation_status", sa.String(length=20), nullable=False),
        sa.Column(
            "linked_daily_activity_plan_item_id", sa.String(length=64), nullable=True
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('proposer','acceptor')",
            name="ck_joint_activity_participants_role",
        ),
        sa.CheckConstraint(
            "participation_status IN ('accepted','scheduled','consumed','cancelled','interrupted')",
            name="ck_joint_activity_participants_status",
        ),
        sa.ForeignKeyConstraint(
            ["joint_activity_id", "world_id"],
            ["joint_activities.id", "joint_activities.world_id"],
            name="fk_joint_activity_participants_activity_scope",
        ),
        sa.ForeignKeyConstraint(
            ["world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_joint_activity_participants_character_scope",
        ),
        sa.ForeignKeyConstraint(
            ["linked_daily_activity_plan_item_id", "world_id", "world_character_id"],
            [
                "daily_activity_plan_items.id",
                "daily_activity_plan_items.world_id",
                "daily_activity_plan_items.world_character_id",
            ],
            name="fk_joint_activity_participants_linked_item_scope",
        ),
        sa.PrimaryKeyConstraint("joint_activity_id", "world_character_id"),
    )
    op.create_index(
        "ix_joint_activity_participants_character",
        "joint_activity_participants",
        ["world_character_id"],
    )

    op.create_table(
        "joint_activity_representation_claims",
        sa.Column("joint_activity_id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("representation_status", sa.String(length=20), nullable=False),
        sa.Column(
            "claimed_by_world_character_id", sa.String(length=64), nullable=True
        ),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_version", sa.Integer(), nullable=False),
        sa.Column("representation_post_id", sa.String(length=64), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "representation_status IN ('pending','claimed','represented')",
            name="ck_joint_activity_representation_claims_status",
        ),
        sa.CheckConstraint(
            "claim_version >= 1",
            name="ck_joint_activity_representation_claims_version",
        ),
        sa.ForeignKeyConstraint(
            ["joint_activity_id", "world_id"],
            ["joint_activities.id", "joint_activities.world_id"],
            name="fk_joint_activity_representation_claims_activity_scope",
        ),
        sa.ForeignKeyConstraint(
            ["claimed_by_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_joint_activity_representation_claims_character_scope",
        ),
        sa.ForeignKeyConstraint(["representation_post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("joint_activity_id"),
        sa.UniqueConstraint("representation_post_id"),
    )
    op.create_index(
        "ix_joint_activity_representation_claims_expiry",
        "joint_activity_representation_claims",
        ["representation_status", "claim_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_joint_activity_representation_claims_expiry",
        table_name="joint_activity_representation_claims",
    )
    op.drop_table("joint_activity_representation_claims")
    op.drop_index(
        "ix_joint_activity_participants_character",
        table_name="joint_activity_participants",
    )
    op.drop_table("joint_activity_participants")
    op.drop_index(
        "ix_activity_plan_revisions_item", table_name="activity_plan_revisions"
    )
    op.drop_table("activity_plan_revisions")
    op.drop_index(
        "ix_activity_event_consumptions_claim_expiry",
        table_name="activity_event_consumptions",
    )
    op.drop_table("activity_event_consumptions")
    op.drop_index("ix_activity_beats_claim_expiry", table_name="activity_beats")
    op.drop_table("activity_beats")
    op.drop_index(
        "uq_activity_episodes_active_character", table_name="activity_episodes"
    )
    op.drop_table("activity_episodes")
    op.drop_index(
        "ix_daily_activity_plan_items_character_window",
        table_name="daily_activity_plan_items",
    )
    op.drop_table("daily_activity_plan_items")
    op.drop_index(
        "ix_joint_activities_world_status", table_name="joint_activities"
    )
    op.drop_table("joint_activities")
    op.drop_index(
        "ix_daily_activity_plans_world_date", table_name="daily_activity_plans"
    )
    op.drop_table("daily_activity_plans")
    op.drop_constraint(
        "uq_world_characters_id_world", "world_characters", type_="unique"
    )
