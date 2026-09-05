"""add canonical social events and directional relationships

Revision ID: 20260811_0077
Revises: 20260811_0076
Create Date: 2026-08-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260811_0077"
down_revision: str | None = "20260811_0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


JSON_DOCUMENT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _preflight_opaque_event_references() -> None:
    bind = op.get_bind()
    checks = (
        ("activity_event_consumptions", "source_social_event_id"),
        ("activity_plan_revisions", "source_acceptance_event_id"),
        ("joint_activities", "source_proposal_event_id"),
        ("joint_activities", "source_acceptance_event_id"),
    )
    offenders: list[str] = []
    for table_name, column_name in checks:
        count = bind.scalar(
            sa.text(
                f"SELECT count(*) FROM {table_name} "
                f"WHERE {column_name} IS NOT NULL"
            )
        )
        if int(count or 0) > 0:
            offenders.append(f"{table_name}.{column_name}={int(count or 0)}")
    if offenders:
        raise RuntimeError(
            "cannot add canonical SocialEvent foreign keys while opaque P3 "
            "references exist: " + ", ".join(offenders)
        )


def upgrade() -> None:
    _preflight_opaque_event_references()

    for name, type_ in (
        ("joint_activity_id", sa.String(length=64)),
        ("opening_post_id", sa.String(length=64)),
        ("activity_episode_id", sa.String(length=64)),
        ("activity_beat_id", sa.String(length=64)),
    ):
        op.add_column("posts", sa.Column(name, type_, nullable=True))
    op.create_foreign_key(
        "fk_posts_joint_activity_scope",
        "posts",
        "joint_activities",
        ["joint_activity_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_foreign_key(
        "fk_posts_opening_post", "posts", "posts", ["opening_post_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_posts_activity_episode",
        "posts",
        "activity_episodes",
        ["activity_episode_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_posts_activity_beat",
        "posts",
        "activity_beats",
        ["activity_beat_id"],
        ["id"],
    )
    op.create_index("ix_posts_joint_activity", "posts", ["joint_activity_id", "created_at"])

    for table_name, actor_name in (
        ("post_likes", "actor_world_character_id"),
        ("post_reposts", "actor_world_character_id"),
    ):
        op.add_column(table_name, sa.Column("world_id", sa.String(length=64), nullable=True))
        op.add_column(table_name, sa.Column(actor_name, sa.String(length=64), nullable=True))
        op.add_column(
            table_name,
            sa.Column("target_world_character_id", sa.String(length=64), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table_name}_world", table_name, "worlds", ["world_id"], ["id"]
        )
        op.create_foreign_key(
            f"fk_{table_name}_actor_scope",
            table_name,
            "world_characters",
            [actor_name, "world_id"],
            ["id", "world_id"],
        )
        op.create_foreign_key(
            f"fk_{table_name}_target_scope",
            table_name,
            "world_characters",
            ["target_world_character_id", "world_id"],
            ["id", "world_id"],
        )
        op.create_check_constraint(
            f"ck_{table_name}_world_scope",
            table_name,
            "(world_id IS NULL AND actor_world_character_id IS NULL AND "
            "target_world_character_id IS NULL) OR "
            "(world_id IS NOT NULL AND actor_world_character_id IS NOT NULL AND "
            "target_world_character_id IS NOT NULL)",
        )
        op.create_index(
            f"uq_{table_name}_post_actor_world_character",
            table_name,
            ["post_id", actor_name],
            unique=True,
            postgresql_where=sa.text(f"{actor_name} IS NOT NULL"),
            sqlite_where=sa.text(f"{actor_name} IS NOT NULL"),
        )

    op.add_column("profile_follows", sa.Column("world_id", sa.String(length=64), nullable=True))
    op.add_column(
        "profile_follows",
        sa.Column("follower_world_character_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "profile_follows",
        sa.Column("target_world_character_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_profile_follows_world", "profile_follows", "worlds", ["world_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_profile_follows_follower_scope",
        "profile_follows",
        "world_characters",
        ["follower_world_character_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_foreign_key(
        "fk_profile_follows_target_scope",
        "profile_follows",
        "world_characters",
        ["target_world_character_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_check_constraint(
        "ck_profile_follows_world_scope",
        "profile_follows",
        "(world_id IS NULL AND follower_world_character_id IS NULL AND "
        "target_world_character_id IS NULL) OR "
        "(world_id IS NOT NULL AND follower_world_character_id IS NOT NULL AND "
        "target_world_character_id IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_profile_follows_world_direction",
        "profile_follows",
        ["world_id", "follower_world_character_id", "target_world_character_id"],
    )

    for name, type_ in (
        ("world_id", sa.String(length=64)),
        ("recipient_world_character_id", sa.String(length=64)),
        ("actor_world_character_id", sa.String(length=64)),
        ("source_social_event_id", sa.String(length=64)),
        ("source_joint_activity_id", sa.String(length=64)),
        ("handled_at", sa.DateTime(timezone=True)),
        ("handling_outcome", sa.String(length=40)),
    ):
        op.add_column("notifications", sa.Column(name, type_, nullable=True))
    op.create_foreign_key(
        "fk_notifications_world", "notifications", "worlds", ["world_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_notifications_recipient_scope",
        "notifications",
        "world_characters",
        ["recipient_world_character_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_foreign_key(
        "fk_notifications_actor_scope",
        "notifications",
        "world_characters",
        ["actor_world_character_id", "world_id"],
        ["id", "world_id"],
    )

    op.add_column(
        "agent_public_action_executions",
        sa.Column("social_event_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_agent_public_action_executions_social_event_id",
        "agent_public_action_executions",
        ["social_event_id"],
    )

    op.drop_constraint(
        "ck_daily_activity_plan_items_status",
        "daily_activity_plan_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_daily_activity_plan_items_status",
        "daily_activity_plan_items",
        "status IN ('planned','active','completed','skipped','interrupted',"
        "'cancelled','superseded')",
    )
    op.drop_constraint(
        "uq_daily_activity_plan_items_daypart",
        "daily_activity_plan_items",
        type_="unique",
    )
    op.alter_column(
        "daily_activity_plan_items", "selected_candidate_id", nullable=True
    )
    op.alter_column(
        "daily_activity_plan_items", "candidate_signature", nullable=True
    )
    op.alter_column("daily_activity_plan_items", "candidate_ordinal", nullable=True)
    op.add_column(
        "daily_activity_plan_items",
        sa.Column(
            "origin_type",
            sa.String(length=24),
            server_default="repertoire",
            nullable=False,
        ),
    )
    op.add_column(
        "daily_activity_plan_items",
        sa.Column("supersedes_plan_item_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "daily_activity_plan_items",
        sa.Column("is_user_pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_check_constraint(
        "ck_daily_activity_plan_items_origin",
        "daily_activity_plan_items",
        "origin_type IN ('repertoire','joint_activity')",
    )
    op.create_foreign_key(
        "fk_daily_activity_plan_items_supersedes",
        "daily_activity_plan_items",
        "daily_activity_plan_items",
        ["supersedes_plan_item_id"],
        ["id"],
    )
    op.create_index(
        "uq_daily_activity_plan_items_current_daypart",
        "daily_activity_plan_items",
        ["plan_id", "daypart"],
        unique=True,
        postgresql_where=sa.text("status != 'superseded'"),
        sqlite_where=sa.text("status != 'superseded'"),
    )
    op.create_index(
        "uq_daily_activity_plan_items_joint_participant",
        "daily_activity_plan_items",
        ["joint_activity_id", "world_character_id"],
        unique=True,
        postgresql_where=sa.text(
            "joint_activity_id IS NOT NULL AND status != 'superseded'"
        ),
        sqlite_where=sa.text(
            "joint_activity_id IS NOT NULL AND status != 'superseded'"
        ),
    )

    op.drop_constraint("ck_joint_activities_status", "joint_activities", type_="check")
    op.create_check_constraint(
        "ck_joint_activities_status",
        "joint_activities",
        "status IN ('accepted_unscheduled','scheduled','ready','active','represented',"
        "'completed','cancelled','expired','expired_unrepresented','interrupted')",
    )
    for name, type_ in (
        ("proposal_id", sa.String(length=64)),
        ("scheduled_local_date", sa.Date()),
        ("target_daypart", sa.String(length=20)),
        ("timezone_snapshot", sa.String(length=64)),
        ("opening_post_id", sa.String(length=64)),
        ("opened_by_world_character_id", sa.String(length=64)),
        ("started_at", sa.DateTime(timezone=True)),
        ("completed_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("joint_activities", sa.Column(name, type_, nullable=True))
    op.add_column(
        "joint_activities",
        sa.Column(
            "opening_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_joint_activities_target_daypart",
        "joint_activities",
        "target_daypart IS NULL OR target_daypart IN "
        "('dawn','morning','afternoon','evening')",
    )
    op.create_check_constraint(
        "ck_joint_activities_opening_attempt_count",
        "joint_activities",
        "opening_attempt_count >= 0 AND opening_attempt_count <= 4",
    )

    op.drop_constraint(
        "ck_joint_activity_participants_status",
        "joint_activity_participants",
        type_="check",
    )
    op.create_check_constraint(
        "ck_joint_activity_participants_status",
        "joint_activity_participants",
        "participation_status IN ('accepted','scheduled','active','consumed',"
        "'completed','cancelled','interrupted')",
    )
    op.add_column(
        "joint_activity_participants",
        sa.Column("linked_activity_episode_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "joint_activity_participants",
        sa.Column("represented_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "joint_activity_participants",
        sa.Column("last_joint_post_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "joint_activity_participants",
        sa.Column(
            "opening_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_joint_activity_participants_opening_attempt_count",
        "joint_activity_participants",
        "opening_attempt_count >= 0 AND opening_attempt_count <= 2",
    )
    op.create_foreign_key(
        "fk_joint_activity_participants_linked_episode_scope",
        "joint_activity_participants",
        "activity_episodes",
        ["linked_activity_episode_id", "world_id", "world_character_id"],
        ["id", "world_id", "world_character_id"],
    )
    op.create_foreign_key(
        "fk_joint_activity_participants_last_post",
        "joint_activity_participants",
        "posts",
        ["last_joint_post_id"],
        ["id"],
    )

    op.create_table(
        "social_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("actor_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("target_world_character_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=20), server_default="succeeded", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column(
            "retrieval_status", sa.String(length=20), server_default="eligible", nullable=False
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('post_published','comment_created','reply_created',"
            "'mention_created','like_added','like_removed','follow_added',"
            "'follow_removed','repost_added','repost_removed','joint_proposed',"
            "'joint_accepted','joint_started','joint_completed','joint_declined',"
            "'joint_cancelled')",
            name="ck_social_events_type",
        ),
        sa.CheckConstraint("result = 'succeeded'", name="ck_social_events_result"),
        sa.CheckConstraint(
            "retrieval_status IN ('eligible','audit_only','excluded')",
            name="ck_social_events_retrieval_status",
        ),
        sa.CheckConstraint(
            "invalidation_reason IS NULL OR invalidation_reason IN "
            "('source_deleted','source_hidden','membership_inactive','blocked',"
            "'world_mismatch','manual_exclusion')",
            name="ck_social_events_invalidation_reason",
        ),
        sa.CheckConstraint(
            "target_world_character_id IS NULL OR "
            "actor_world_character_id != target_world_character_id",
            name="ck_social_events_not_self",
        ),
        sa.CheckConstraint(
            "event_type IN ('post_published','joint_started') OR "
            "target_world_character_id IS NOT NULL",
            name="ck_social_events_target_required",
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_social_events_actor_scope",
        ),
        sa.ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_social_events_target_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "world_id", name="uq_social_events_scope"),
        sa.UniqueConstraint("idempotency_key", name="uq_social_events_idempotency"),
    )
    op.create_index("ix_social_events_world_occurred", "social_events", ["world_id", "occurred_at"])
    op.create_index(
        "ix_social_events_actor_occurred",
        "social_events",
        ["actor_world_character_id", "occurred_at"],
    )
    op.create_index(
        "ix_social_events_target_occurred",
        "social_events",
        ["target_world_character_id", "occurred_at"],
    )

    op.create_table(
        "social_event_evidence",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("social_event_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_kind", sa.String(length=32), nullable=False),
        sa.Column("source_object_type", sa.String(length=48), nullable=False),
        sa.Column("source_object_id", sa.String(length=128), nullable=False),
        sa.Column("root_post_id", sa.String(length=64), nullable=True),
        sa.Column("source_post_id", sa.String(length=64), nullable=True),
        sa.Column("target_post_id", sa.String(length=64), nullable=True),
        sa.Column("source_notification_id", sa.Integer(), nullable=True),
        sa.Column("agent_run_id", sa.String(length=64), nullable=True),
        sa.Column("public_action_execution_id", sa.Integer(), nullable=True),
        sa.Column("interaction_intent", sa.String(length=40), nullable=True),
        sa.Column("comment_purpose", sa.String(length=40), nullable=True),
        sa.Column("proposal_decision", sa.String(length=20), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_visibility_at_event", sa.String(length=20), nullable=True),
        sa.Column("source_author_id_at_event", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "evidence_kind IN ('post','reply_post','like','repost','follow',"
            "'notification','execution','joint_activity')",
            name="ck_social_event_evidence_kind",
        ),
        sa.CheckConstraint(
            "source_object_type IN ('post','post_like','post_repost','profile_follow',"
            "'notification','agent_public_action_execution','joint_activity')",
            name="ck_social_event_evidence_source_type",
        ),
        sa.CheckConstraint(
            "source_visibility_at_event IS NULL OR source_visibility_at_event IN "
            "('public','unlisted','private','not_applicable')",
            name="ck_social_event_evidence_visibility",
        ),
        sa.ForeignKeyConstraint(["social_event_id"], ["social_events.id"]),
        sa.ForeignKeyConstraint(["root_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["source_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["target_post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["source_notification_id"], ["notifications.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(
            ["public_action_execution_id"], ["agent_public_action_executions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "social_event_id",
            "evidence_kind",
            "source_object_type",
            "source_object_id",
            name="uq_social_event_evidence_source",
        ),
    )
    op.create_index("ix_social_event_evidence_event", "social_event_evidence", ["social_event_id"])
    op.create_index(
        "ix_social_event_evidence_source_post", "social_event_evidence", ["source_post_id"]
    )

    op.create_table(
        "relationship_states",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("actor_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("target_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("familiarity", sa.Integer(), nullable=False),
        sa.Column("affinity", sa.Integer(), nullable=False),
        sa.Column("trust", sa.Integer(), nullable=False),
        sa.Column("tension", sa.Integer(), nullable=False),
        sa.Column("interaction_count", sa.Integer(), nullable=False),
        sa.Column("last_event_id", sa.String(length=64), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "actor_world_character_id != target_world_character_id",
            name="ck_relationship_states_not_self",
        ),
        sa.CheckConstraint(
            "familiarity >= 0 AND familiarity <= 100",
            name="ck_relationship_states_familiarity",
        ),
        sa.CheckConstraint(
            "affinity >= -100 AND affinity <= 100",
            name="ck_relationship_states_affinity",
        ),
        sa.CheckConstraint(
            "trust >= -100 AND trust <= 100", name="ck_relationship_states_trust"
        ),
        sa.CheckConstraint(
            "tension >= 0 AND tension <= 100", name="ck_relationship_states_tension"
        ),
        sa.CheckConstraint(
            "interaction_count >= 0", name="ck_relationship_states_interactions"
        ),
        sa.CheckConstraint("version >= 1", name="ck_relationship_states_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_states_actor_scope",
        ),
        sa.ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_states_target_scope",
        ),
        sa.ForeignKeyConstraint(["last_event_id"], ["social_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "world_id", name="uq_relationship_states_scope"),
        sa.UniqueConstraint(
            "world_id",
            "actor_world_character_id",
            "target_world_character_id",
            name="uq_relationship_states_direction",
        ),
    )
    op.create_index(
        "ix_relationship_states_actor_updated",
        "relationship_states",
        ["actor_world_character_id", "updated_at"],
    )

    op.create_table(
        "relationship_state_changes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("relationship_state_id", sa.String(length=64), nullable=False),
        sa.Column("social_event_id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("actor_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("target_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("valence", sa.String(length=16), nullable=False),
        sa.Column("intensity", sa.String(length=16), nullable=False),
        sa.Column("delta_familiarity", sa.SmallInteger(), nullable=False),
        sa.Column("delta_affinity", sa.SmallInteger(), nullable=False),
        sa.Column("delta_trust", sa.SmallInteger(), nullable=False),
        sa.Column("delta_tension", sa.SmallInteger(), nullable=False),
        sa.Column("before_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("after_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("not_applied_reason", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "valence IN ('positive','neutral','negative')",
            name="ck_relationship_state_changes_valence",
        ),
        sa.CheckConstraint(
            "intensity IN ('low','medium')",
            name="ck_relationship_state_changes_intensity",
        ),
        sa.CheckConstraint(
            "not_applied_reason IS NULL OR not_applied_reason IN "
            "('duplicate','daily_delta_cap','no_delta_event')",
            name="ck_relationship_state_changes_reason",
        ),
        sa.ForeignKeyConstraint(["relationship_state_id"], ["relationship_states.id"]),
        sa.ForeignKeyConstraint(["social_event_id"], ["social_events.id"]),
        sa.ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_state_changes_actor_scope",
        ),
        sa.ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_state_changes_target_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "relationship_state_id",
            "social_event_id",
            name="uq_relationship_state_changes_event",
        ),
    )
    op.create_index(
        "ix_relationship_state_changes_world_created",
        "relationship_state_changes",
        ["world_id", "created_at"],
    )

    op.create_table(
        "activity_proposals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("root_proposal_id", sa.String(length=64), nullable=False),
        sa.Column("parent_proposal_id", sa.String(length=64), nullable=True),
        sa.Column("proposal_version", sa.Integer(), nullable=False),
        sa.Column("proposer_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("target_world_character_id", sa.String(length=64), nullable=False),
        sa.Column("activity_seed", sa.String(length=500), nullable=False),
        sa.Column("place_key", sa.String(length=64), nullable=True),
        sa.Column("target_daypart", sa.String(length=20), nullable=False),
        sa.Column("date_policy", sa.String(length=24), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("proposed_local_snapshot", JSON_DOCUMENT, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_proposal_event_id", sa.String(length=64), nullable=False),
        sa.Column("source_response_event_id", sa.String(length=64), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("countered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "proposer_world_character_id != target_world_character_id",
            name="ck_activity_proposals_not_self",
        ),
        sa.CheckConstraint(
            "proposal_version >= 1 AND proposal_version <= 3",
            name="ck_activity_proposals_version_ordinal",
        ),
        sa.CheckConstraint(
            "target_daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_activity_proposals_daypart",
        ),
        sa.CheckConstraint(
            "date_policy IN ('exact','earliest_available')",
            name="ck_activity_proposals_date_policy",
        ),
        sa.CheckConstraint(
            "date_policy != 'exact' OR target_date IS NOT NULL",
            name="ck_activity_proposals_exact_date",
        ),
        sa.CheckConstraint(
            "status IN ('proposed','accepted','rejected','countered','cancelled','expired')",
            name="ck_activity_proposals_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_activity_proposals_version"),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["root_proposal_id"], ["activity_proposals.id"]),
        sa.ForeignKeyConstraint(["parent_proposal_id"], ["activity_proposals.id"]),
        sa.ForeignKeyConstraint(
            ["proposer_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_activity_proposals_proposer_scope",
        ),
        sa.ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_activity_proposals_target_scope",
        ),
        sa.ForeignKeyConstraint(["source_proposal_event_id"], ["social_events.id"]),
        sa.ForeignKeyConstraint(["source_response_event_id"], ["social_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_proposal_event_id", name="uq_activity_proposals_source"),
        sa.UniqueConstraint("source_response_event_id", name="uq_activity_proposals_response"),
        sa.UniqueConstraint("idempotency_key", name="uq_activity_proposals_idempotency"),
    )
    op.create_index(
        "ix_activity_proposals_target_status",
        "activity_proposals",
        ["target_world_character_id", "status"],
    )
    op.create_index(
        "ix_activity_proposals_world_status",
        "activity_proposals",
        ["world_id", "status"],
    )

    op.create_table(
        "graph_projection_outbox",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_id", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=64), nullable=False),
        sa.Column("projection_type", sa.String(length=32), nullable=False),
        sa.Column("payload_version", sa.String(length=40), nullable=False),
        sa.Column("payload", JSON_DOCUMENT, nullable=False),
        sa.Column("source_signature", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_class", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "projection_type IN ('social_event','relationship_state','source_exclusion')",
            name="ck_graph_projection_outbox_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','succeeded','dead','cancelled')",
            name="ck_graph_projection_outbox_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_graph_projection_outbox_attempts"
        ),
        sa.ForeignKeyConstraint(["world_id"], ["worlds.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["social_events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_graph_projection_outbox_dedupe"),
        sa.UniqueConstraint(
            "projection_type",
            "source_event_id",
            "payload_version",
            name="uq_graph_projection_outbox_event",
        ),
    )
    op.create_index(
        "ix_graph_projection_outbox_pending",
        "graph_projection_outbox",
        ["status", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "ix_graph_projection_outbox_world_created",
        "graph_projection_outbox",
        ["world_id", "created_at"],
    )

    op.create_foreign_key(
        "fk_agent_public_action_executions_social_event",
        "agent_public_action_executions",
        "social_events",
        ["social_event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_notifications_source_social_event",
        "notifications",
        "social_events",
        ["source_social_event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_notifications_source_joint_activity",
        "notifications",
        "joint_activities",
        ["source_joint_activity_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_joint_activities_proposal",
        "joint_activities",
        "activity_proposals",
        ["proposal_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_joint_activities_proposal", "joint_activities", ["proposal_id"]
    )
    op.create_foreign_key(
        "fk_joint_activities_source_proposal_event",
        "joint_activities",
        "social_events",
        ["source_proposal_event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_joint_activities_source_acceptance_event",
        "joint_activities",
        "social_events",
        ["source_acceptance_event_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_joint_activities_source_acceptance_event",
        "joint_activities",
        ["source_acceptance_event_id"],
    )
    op.create_foreign_key(
        "fk_joint_activities_opening_post",
        "joint_activities",
        "posts",
        ["opening_post_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_joint_activities_opening_post", "joint_activities", ["opening_post_id"]
    )
    op.create_foreign_key(
        "fk_joint_activities_opened_by_scope",
        "joint_activities",
        "world_characters",
        ["opened_by_world_character_id", "world_id"],
        ["id", "world_id"],
    )
    op.create_foreign_key(
        "fk_activity_event_consumptions_source_event",
        "activity_event_consumptions",
        "social_events",
        ["source_social_event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_activity_plan_revisions_source_acceptance_event",
        "activity_plan_revisions",
        "social_events",
        ["source_acceptance_event_id"],
        ["id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "social_events",
        "relationship_states",
        "activity_proposals",
        "graph_projection_outbox",
    ):
        count = bind.scalar(sa.text(f"SELECT count(*) FROM {table_name}"))
        if int(count or 0) > 0:
            raise RuntimeError(
                f"cannot downgrade 0077 while {table_name} contains P6 rows"
            )

    op.drop_constraint(
        "fk_activity_plan_revisions_source_acceptance_event",
        "activity_plan_revisions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_activity_event_consumptions_source_event",
        "activity_event_consumptions",
        type_="foreignkey",
    )
    for name in (
        "fk_joint_activities_opened_by_scope",
        "fk_joint_activities_opening_post",
        "fk_joint_activities_source_acceptance_event",
        "fk_joint_activities_source_proposal_event",
        "fk_joint_activities_proposal",
    ):
        op.drop_constraint(name, "joint_activities", type_="foreignkey")
    op.drop_constraint(
        "uq_joint_activities_opening_post", "joint_activities", type_="unique"
    )
    op.drop_constraint(
        "uq_joint_activities_source_acceptance_event",
        "joint_activities",
        type_="unique",
    )
    op.drop_constraint(
        "uq_joint_activities_proposal", "joint_activities", type_="unique"
    )
    op.drop_constraint(
        "fk_notifications_source_joint_activity", "notifications", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_notifications_source_social_event", "notifications", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_agent_public_action_executions_social_event",
        "agent_public_action_executions",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_graph_projection_outbox_world_created",
        table_name="graph_projection_outbox",
    )
    op.drop_index(
        "ix_graph_projection_outbox_pending", table_name="graph_projection_outbox"
    )
    op.drop_table("graph_projection_outbox")
    op.drop_index("ix_activity_proposals_world_status", table_name="activity_proposals")
    op.drop_index("ix_activity_proposals_target_status", table_name="activity_proposals")
    op.drop_table("activity_proposals")
    op.drop_index(
        "ix_relationship_state_changes_world_created",
        table_name="relationship_state_changes",
    )
    op.drop_table("relationship_state_changes")
    op.drop_index(
        "ix_relationship_states_actor_updated", table_name="relationship_states"
    )
    op.drop_table("relationship_states")
    op.drop_index(
        "ix_social_event_evidence_source_post", table_name="social_event_evidence"
    )
    op.drop_index("ix_social_event_evidence_event", table_name="social_event_evidence")
    op.drop_table("social_event_evidence")
    op.drop_index("ix_social_events_target_occurred", table_name="social_events")
    op.drop_index("ix_social_events_actor_occurred", table_name="social_events")
    op.drop_index("ix_social_events_world_occurred", table_name="social_events")
    op.drop_table("social_events")

    op.drop_constraint(
        "fk_joint_activity_participants_last_post",
        "joint_activity_participants",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_joint_activity_participants_linked_episode_scope",
        "joint_activity_participants",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_joint_activity_participants_opening_attempt_count",
        "joint_activity_participants",
        type_="check",
    )
    for column_name in (
        "last_joint_post_id",
        "represented_at",
        "linked_activity_episode_id",
        "opening_attempt_count",
    ):
        op.drop_column("joint_activity_participants", column_name)
    op.drop_constraint(
        "ck_joint_activity_participants_status",
        "joint_activity_participants",
        type_="check",
    )
    op.create_check_constraint(
        "ck_joint_activity_participants_status",
        "joint_activity_participants",
        "participation_status IN ('accepted','scheduled','consumed','cancelled','interrupted')",
    )

    op.drop_constraint(
        "ck_joint_activities_opening_attempt_count",
        "joint_activities",
        type_="check",
    )
    op.drop_constraint(
        "ck_joint_activities_target_daypart", "joint_activities", type_="check"
    )
    for column_name in (
        "completed_at",
        "started_at",
        "opened_by_world_character_id",
        "opening_post_id",
        "timezone_snapshot",
        "target_daypart",
        "scheduled_local_date",
        "proposal_id",
        "opening_attempt_count",
    ):
        op.drop_column("joint_activities", column_name)
    op.drop_constraint("ck_joint_activities_status", "joint_activities", type_="check")
    op.create_check_constraint(
        "ck_joint_activities_status",
        "joint_activities",
        "status IN ('accepted_unscheduled','scheduled','ready','represented',"
        "'completed','cancelled','expired','interrupted')",
    )

    op.drop_index(
        "uq_daily_activity_plan_items_joint_participant",
        table_name="daily_activity_plan_items",
    )
    op.drop_index(
        "uq_daily_activity_plan_items_current_daypart",
        table_name="daily_activity_plan_items",
    )
    op.drop_constraint(
        "fk_daily_activity_plan_items_supersedes",
        "daily_activity_plan_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_daily_activity_plan_items_origin",
        "daily_activity_plan_items",
        type_="check",
    )
    for column_name in ("is_user_pinned", "supersedes_plan_item_id", "origin_type"):
        op.drop_column("daily_activity_plan_items", column_name)
    op.alter_column("daily_activity_plan_items", "candidate_ordinal", nullable=False)
    op.alter_column(
        "daily_activity_plan_items", "candidate_signature", nullable=False
    )
    op.alter_column(
        "daily_activity_plan_items", "selected_candidate_id", nullable=False
    )
    op.create_unique_constraint(
        "uq_daily_activity_plan_items_daypart",
        "daily_activity_plan_items",
        ["plan_id", "daypart"],
    )
    op.drop_constraint(
        "ck_daily_activity_plan_items_status",
        "daily_activity_plan_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_daily_activity_plan_items_status",
        "daily_activity_plan_items",
        "status IN ('planned','active','completed','skipped','interrupted','cancelled')",
    )

    op.drop_index(
        "ix_agent_public_action_executions_social_event_id",
        table_name="agent_public_action_executions",
    )
    op.drop_column("agent_public_action_executions", "social_event_id")

    op.drop_constraint("fk_notifications_actor_scope", "notifications", type_="foreignkey")
    op.drop_constraint(
        "fk_notifications_recipient_scope", "notifications", type_="foreignkey"
    )
    op.drop_constraint("fk_notifications_world", "notifications", type_="foreignkey")
    for column_name in (
        "handling_outcome",
        "handled_at",
        "source_joint_activity_id",
        "source_social_event_id",
        "actor_world_character_id",
        "recipient_world_character_id",
        "world_id",
    ):
        op.drop_column("notifications", column_name)

    op.drop_constraint(
        "uq_profile_follows_world_direction", "profile_follows", type_="unique"
    )
    op.drop_constraint(
        "ck_profile_follows_world_scope", "profile_follows", type_="check"
    )
    op.drop_constraint(
        "fk_profile_follows_target_scope", "profile_follows", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_profile_follows_follower_scope", "profile_follows", type_="foreignkey"
    )
    op.drop_constraint("fk_profile_follows_world", "profile_follows", type_="foreignkey")
    for column_name in (
        "target_world_character_id",
        "follower_world_character_id",
        "world_id",
    ):
        op.drop_column("profile_follows", column_name)

    for table_name in ("post_reposts", "post_likes"):
        op.drop_index(
            f"uq_{table_name}_post_actor_world_character", table_name=table_name
        )
        op.drop_constraint(f"ck_{table_name}_world_scope", table_name, type_="check")
        op.drop_constraint(
            f"fk_{table_name}_target_scope", table_name, type_="foreignkey"
        )
        op.drop_constraint(
            f"fk_{table_name}_actor_scope", table_name, type_="foreignkey"
        )
        op.drop_constraint(f"fk_{table_name}_world", table_name, type_="foreignkey")
        for column_name in (
            "target_world_character_id",
            "actor_world_character_id",
            "world_id",
        ):
            op.drop_column(table_name, column_name)

    op.drop_index("ix_posts_joint_activity", table_name="posts")
    for name in (
        "fk_posts_activity_beat",
        "fk_posts_activity_episode",
        "fk_posts_opening_post",
        "fk_posts_joint_activity_scope",
    ):
        op.drop_constraint(name, "posts", type_="foreignkey")
    for column_name in (
        "activity_beat_id",
        "activity_episode_id",
        "opening_post_id",
        "joint_activity_id",
    ):
        op.drop_column("posts", column_name)
