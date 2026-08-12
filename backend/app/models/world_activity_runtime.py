from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.worlds import JSON_DOCUMENT


_ACTIVE_EPISODE = text("status = 'active'")
_CURRENT_PLAN_ITEM = text("status != 'superseded'")
_CURRENT_JOINT_PLAN_ITEM = text(
    "joint_activity_id IS NOT NULL AND status != 'superseded'"
)


class DailyActivityPlan(Base):
    __tablename__ = "daily_activity_plans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','active','completed','interrupted','cancelled')",
            name="ck_daily_activity_plans_status",
        ),
        CheckConstraint(
            "revision_count >= 0 AND revision_count <= 2",
            name="ck_daily_activity_plans_revision_count",
        ),
        CheckConstraint("version >= 1", name="ck_daily_activity_plans_version"),
        ForeignKeyConstraint(
            ["world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_daily_activity_plans_world_character_scope",
        ),
        UniqueConstraint(
            "world_character_id",
            "local_date",
            name="uq_daily_activity_plans_character_date",
        ),
        UniqueConstraint(
            "id",
            "world_id",
            "world_character_id",
            name="uq_daily_activity_plans_scope",
        ),
        Index(
            "ix_daily_activity_plans_world_date",
            "world_id",
            "local_date",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone_contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    repertoire_id: Mapped[str] = mapped_column(
        ForeignKey("world_activity_repertoires.id"), nullable=False
    )
    world_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    character_definition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    repertoire_contract_version: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    selection_contract_version: Mapped[str] = mapped_column(
        String(40), nullable=False
    )
    selection_seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class JointActivity(Base):
    __tablename__ = "joint_activities"
    __table_args__ = (
        CheckConstraint(
            "schedule_mode IN ('exact','window','flexible')",
            name="ck_joint_activities_schedule_mode",
        ),
        CheckConstraint(
            "status IN ('accepted_unscheduled','scheduled','ready','active',"
            "'represented','completed','cancelled','expired',"
            "'expired_unrepresented','interrupted')",
            name="ck_joint_activities_status",
        ),
        CheckConstraint(
            "target_daypart IS NULL OR target_daypart IN "
            "('dawn','morning','afternoon','evening')",
            name="ck_joint_activities_target_daypart",
        ),
        CheckConstraint(
            "scheduled_start_at IS NULL OR scheduled_end_at IS NULL "
            "OR scheduled_start_at < scheduled_end_at",
            name="ck_joint_activities_scheduled_window",
        ),
        CheckConstraint("version >= 1", name="ck_joint_activities_version"),
        CheckConstraint(
            "opening_attempt_count >= 0 AND opening_attempt_count <= 4",
            name="ck_joint_activities_opening_attempt_count",
        ),
        ForeignKeyConstraint(
            ["represented_by_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_joint_activities_represented_by_scope",
        ),
        ForeignKeyConstraint(
            ["opened_by_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_joint_activities_opened_by_scope",
        ),
        UniqueConstraint("id", "world_id", name="uq_joint_activities_scope"),
        Index("ix_joint_activities_world_status", "world_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    activity_seed: Mapped[str] = mapped_column(String(500), nullable=False)
    place_key: Mapped[str | None] = mapped_column(String(64))
    schedule_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    eligible_dayparts: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schedule_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(28), nullable=False, default="accepted_unscheduled"
    )
    proposal_id: Mapped[str | None] = mapped_column(
        ForeignKey("activity_proposals.id"), unique=True
    )
    scheduled_local_date: Mapped[date | None] = mapped_column(Date)
    target_daypart: Mapped[str | None] = mapped_column(String(20))
    timezone_snapshot: Mapped[str | None] = mapped_column(String(64))
    source_proposal_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("social_events.id")
    )
    source_acceptance_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("social_events.id"), unique=True
    )
    representation_post_id: Mapped[str | None] = mapped_column(
        ForeignKey("posts.id"), unique=True
    )
    opening_post_id: Mapped[str | None] = mapped_column(
        ForeignKey("posts.id"), unique=True
    )
    opened_by_world_character_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opening_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    represented_by_world_character_id: Mapped[str | None] = mapped_column(String(64))
    represented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class DailyActivityPlanItem(Base):
    __tablename__ = "daily_activity_plan_items"
    __table_args__ = (
        CheckConstraint(
            "daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_daily_activity_plan_items_daypart",
        ),
        CheckConstraint(
            "status IN ('planned','active','completed','skipped','interrupted',"
            "'cancelled','superseded')",
            name="ck_daily_activity_plan_items_status",
        ),
        CheckConstraint(
            "revision_count >= 0 AND revision_count <= 1",
            name="ck_daily_activity_plan_items_revision_count",
        ),
        CheckConstraint(
            "scheduled_start_at < scheduled_end_at",
            name="ck_daily_activity_plan_items_window",
        ),
        CheckConstraint("version >= 1", name="ck_daily_activity_plan_items_version"),
        ForeignKeyConstraint(
            ["plan_id", "world_id", "world_character_id"],
            [
                "daily_activity_plans.id",
                "daily_activity_plans.world_id",
                "daily_activity_plans.world_character_id",
            ],
            name="fk_daily_activity_plan_items_plan_scope",
        ),
        ForeignKeyConstraint(
            ["joint_activity_id", "world_id"],
            ["joint_activities.id", "joint_activities.world_id"],
            name="fk_daily_activity_plan_items_joint_scope",
        ),
        CheckConstraint(
            "origin_type IN ('repertoire','joint_activity')",
            name="ck_daily_activity_plan_items_origin",
        ),
        Index(
            "uq_daily_activity_plan_items_current_daypart",
            "plan_id",
            "daypart",
            unique=True,
            postgresql_where=_CURRENT_PLAN_ITEM,
            sqlite_where=_CURRENT_PLAN_ITEM,
        ),
        Index(
            "uq_daily_activity_plan_items_joint_participant",
            "joint_activity_id",
            "world_character_id",
            unique=True,
            postgresql_where=_CURRENT_JOINT_PLAN_ITEM,
            sqlite_where=_CURRENT_JOINT_PLAN_ITEM,
        ),
        UniqueConstraint(
            "id",
            "world_id",
            "world_character_id",
            name="uq_daily_activity_plan_items_scope",
        ),
        Index(
            "ix_daily_activity_plan_items_character_window",
            "world_character_id",
            "scheduled_start_at",
            "scheduled_end_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    daypart: Mapped[str] = mapped_column(String(20), nullable=False)
    selected_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("world_activity_candidates.id")
    )
    candidate_signature: Mapped[str | None] = mapped_column(String(64))
    candidate_ordinal: Mapped[int | None] = mapped_column(Integer)
    origin_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default="repertoire", server_default="repertoire"
    )
    supersedes_plan_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("daily_activity_plan_items.id")
    )
    is_user_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    activity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_seed: Mapped[str] = mapped_column(String(500), nullable=False)
    social_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    place_key: Mapped[str | None] = mapped_column(String(64))
    joint_activity_id: Mapped[str | None] = mapped_column(String(64))
    scheduled_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scheduled_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    terminal_reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ActivityEpisode(Base):
    __tablename__ = "activity_episodes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned','active','completed','interrupted','cancelled')",
            name="ck_activity_episodes_status",
        ),
        CheckConstraint("next_sequence_no >= 1", name="ck_activity_episodes_sequence"),
        CheckConstraint("version >= 1", name="ck_activity_episodes_version"),
        ForeignKeyConstraint(
            ["plan_item_id", "world_id", "world_character_id"],
            [
                "daily_activity_plan_items.id",
                "daily_activity_plan_items.world_id",
                "daily_activity_plan_items.world_character_id",
            ],
            name="fk_activity_episodes_item_scope",
        ),
        UniqueConstraint("plan_item_id", name="uq_activity_episodes_plan_item"),
        UniqueConstraint(
            "id",
            "world_id",
            "world_character_id",
            name="uq_activity_episodes_scope",
        ),
        Index(
            "uq_activity_episodes_active_character",
            "world_character_id",
            unique=True,
            postgresql_where=_ACTIVE_EPISODE,
            sqlite_where=_ACTIVE_EPISODE,
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    effective_activity_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    current_state_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    current_state_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    last_successful_beat_id: Mapped[str | None] = mapped_column(String(64))
    next_sequence_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    terminal_reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ActivityBeat(Base):
    __tablename__ = "activity_beats"
    __table_args__ = (
        CheckConstraint(
            "trigger_kind IN ('scheduled','comment_influenced','joint_activity')",
            name="ck_activity_beats_trigger_kind",
        ),
        CheckConstraint(
            "status IN ('pending','claimed','succeeded','failed','cancelled','skipped')",
            name="ck_activity_beats_status",
        ),
        CheckConstraint("sequence_no >= 1", name="ck_activity_beats_sequence"),
        CheckConstraint("attempt_count >= 0", name="ck_activity_beats_attempt_count"),
        CheckConstraint("skipped_tick_count >= 0", name="ck_activity_beats_skipped_count"),
        CheckConstraint(
            "status != 'failed' OR (state_after_snapshot IS NULL AND source_post_id IS NULL)",
            name="ck_activity_beats_failed_no_success_state",
        ),
        ForeignKeyConstraint(
            ["episode_id", "world_id", "world_character_id"],
            [
                "activity_episodes.id",
                "activity_episodes.world_id",
                "activity_episodes.world_character_id",
            ],
            name="fk_activity_beats_episode_scope",
        ),
        UniqueConstraint(
            "episode_id", "sequence_no", name="uq_activity_beats_sequence"
        ),
        UniqueConstraint(
            "world_character_id",
            "scheduled_for",
            "idempotency_key",
            name="uq_activity_beats_request",
        ),
        Index("ix_activity_beats_claim_expiry", "status", "claim_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    episode_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    previous_successful_beat_id: Mapped[str | None] = mapped_column(
        ForeignKey("activity_beats.id")
    )
    source_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    source_event_ids: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list
    )
    state_before_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    state_after_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    result_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    claim_run_id: Mapped[str | None] = mapped_column(String(64))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_tick_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ActivityEventConsumption(Base):
    __tablename__ = "activity_event_consumptions"
    __table_args__ = (
        CheckConstraint(
            "namespace IN ('next_activity_beat')",
            name="ck_activity_event_consumptions_namespace",
        ),
        CheckConstraint(
            "status IN ('claimed','applied','released','rejected')",
            name="ck_activity_event_consumptions_status",
        ),
        CheckConstraint("version >= 1", name="ck_activity_event_consumptions_version"),
        ForeignKeyConstraint(
            ["consumer_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_activity_event_consumptions_character_scope",
        ),
        UniqueConstraint(
            "consumer_world_character_id",
            "source_social_event_id",
            "namespace",
            name="uq_activity_event_consumptions_event_namespace",
        ),
        Index(
            "ix_activity_event_consumptions_claim_expiry",
            "status",
            "claim_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    consumer_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_social_event_id: Mapped[str] = mapped_column(
        ForeignKey("social_events.id"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(40), nullable=False)
    target_activity_beat_id: Mapped[str | None] = mapped_column(
        ForeignKey("activity_beats.id")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    claim_run_id: Mapped[str | None] = mapped_column(String(64))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ActivityPlanRevision(Base):
    __tablename__ = "activity_plan_revisions"
    __table_args__ = (
        CheckConstraint(
            "revision_ordinal >= 1 AND revision_ordinal <= 2",
            name="ck_activity_plan_revisions_ordinal",
        ),
        UniqueConstraint(
            "plan_id", "revision_ordinal", name="uq_activity_plan_revisions_ordinal"
        ),
        UniqueConstraint("idempotency_key", name="uq_activity_plan_revisions_request"),
        Index("ix_activity_plan_revisions_item", "plan_item_id", "applied_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("daily_activity_plans.id"), nullable=False)
    plan_item_id: Mapped[str] = mapped_column(
        ForeignKey("daily_activity_plan_items.id"), nullable=False
    )
    joint_activity_id: Mapped[str] = mapped_column(
        ForeignKey("joint_activities.id"), nullable=False
    )
    revision_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    after_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    source_acceptance_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("social_events.id")
    )
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class JointActivityParticipant(Base):
    __tablename__ = "joint_activity_participants"
    __table_args__ = (
        CheckConstraint(
            "role IN ('proposer','acceptor')",
            name="ck_joint_activity_participants_role",
        ),
        CheckConstraint(
            "participation_status IN ('accepted','scheduled','active','consumed',"
            "'completed','cancelled','interrupted')",
            name="ck_joint_activity_participants_status",
        ),
        CheckConstraint(
            "opening_attempt_count >= 0 AND opening_attempt_count <= 2",
            name="ck_joint_activity_participants_opening_attempt_count",
        ),
        ForeignKeyConstraint(
            ["joint_activity_id", "world_id"],
            ["joint_activities.id", "joint_activities.world_id"],
            name="fk_joint_activity_participants_activity_scope",
        ),
        ForeignKeyConstraint(
            ["world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_joint_activity_participants_character_scope",
        ),
        ForeignKeyConstraint(
            ["linked_daily_activity_plan_item_id", "world_id", "world_character_id"],
            [
                "daily_activity_plan_items.id",
                "daily_activity_plan_items.world_id",
                "daily_activity_plan_items.world_character_id",
            ],
            name="fk_joint_activity_participants_linked_item_scope",
        ),
        ForeignKeyConstraint(
            ["linked_activity_episode_id", "world_id", "world_character_id"],
            [
                "activity_episodes.id",
                "activity_episodes.world_id",
                "activity_episodes.world_character_id",
            ],
            name="fk_joint_activity_participants_linked_episode_scope",
        ),
        Index("ix_joint_activity_participants_character", "world_character_id"),
    )

    joint_activity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_character_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    participation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted"
    )
    linked_daily_activity_plan_item_id: Mapped[str | None] = mapped_column(String(64))
    linked_activity_episode_id: Mapped[str | None] = mapped_column(String(64))
    represented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_joint_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    opening_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class JointActivityRepresentationClaim(Base):
    __tablename__ = "joint_activity_representation_claims"
    __table_args__ = (
        CheckConstraint(
            "representation_status IN ('pending','claimed','represented')",
            name="ck_joint_activity_representation_claims_status",
        ),
        CheckConstraint(
            "claim_version >= 1",
            name="ck_joint_activity_representation_claims_version",
        ),
        ForeignKeyConstraint(
            ["joint_activity_id", "world_id"],
            ["joint_activities.id", "joint_activities.world_id"],
            name="fk_joint_activity_representation_claims_activity_scope",
        ),
        ForeignKeyConstraint(
            ["claimed_by_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_joint_activity_representation_claims_character_scope",
        ),
        Index(
            "ix_joint_activity_representation_claims_expiry",
            "representation_status",
            "claim_expires_at",
        ),
    )

    joint_activity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    representation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    claimed_by_world_character_id: Mapped[str | None] = mapped_column(String(64))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    representation_post_id: Mapped[str | None] = mapped_column(
        ForeignKey("posts.id"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
