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
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.worlds import JSON_DOCUMENT


SOCIAL_EVENT_TYPES = (
    "post_published",
    "comment_created",
    "reply_created",
    "mention_created",
    "like_added",
    "like_removed",
    "follow_added",
    "follow_removed",
    "repost_added",
    "repost_removed",
    "joint_proposed",
    "joint_accepted",
    "joint_started",
    "joint_completed",
    "joint_declined",
    "joint_cancelled",
)


class SocialEvent(Base):
    __tablename__ = "social_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            + ",".join(f"'{value}'" for value in SOCIAL_EVENT_TYPES)
            + ")",
            name="ck_social_events_type",
        ),
        CheckConstraint("result = 'succeeded'", name="ck_social_events_result"),
        CheckConstraint(
            "retrieval_status IN ('eligible','audit_only','excluded')",
            name="ck_social_events_retrieval_status",
        ),
        CheckConstraint(
            "invalidation_reason IS NULL OR invalidation_reason IN "
            "('source_deleted','source_hidden','membership_inactive','blocked',"
            "'world_mismatch','manual_exclusion')",
            name="ck_social_events_invalidation_reason",
        ),
        CheckConstraint(
            "target_world_character_id IS NULL OR "
            "actor_world_character_id != target_world_character_id",
            name="ck_social_events_not_self",
        ),
        CheckConstraint(
            "event_type IN ('post_published','joint_started') OR "
            "target_world_character_id IS NOT NULL",
            name="ck_social_events_target_required",
        ),
        ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_social_events_actor_scope",
        ),
        ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_social_events_target_scope",
        ),
        UniqueConstraint("id", "world_id", name="uq_social_events_scope"),
        UniqueConstraint("idempotency_key", name="uq_social_events_idempotency"),
        Index("ix_social_events_world_occurred", "world_id", "occurred_at"),
        Index(
            "ix_social_events_actor_occurred",
            "actor_world_character_id",
            "occurred_at",
        ),
        Index(
            "ix_social_events_target_occurred",
            "target_world_character_id",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_world_character_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str] = mapped_column(
        String(20), nullable=False, default="succeeded", server_default="succeeded"
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="social-event-v1"
    )
    retrieval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="eligible", server_default="eligible"
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SocialEventEvidence(Base):
    __tablename__ = "social_event_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_kind IN ('post','reply_post','like','repost','follow',"
            "'notification','execution','joint_activity')",
            name="ck_social_event_evidence_kind",
        ),
        CheckConstraint(
            "source_object_type IN ('post','post_like','post_repost','profile_follow',"
            "'notification','agent_public_action_execution','joint_activity')",
            name="ck_social_event_evidence_source_type",
        ),
        CheckConstraint(
            "source_visibility_at_event IS NULL OR source_visibility_at_event IN "
            "('public','unlisted','private','not_applicable')",
            name="ck_social_event_evidence_visibility",
        ),
        UniqueConstraint(
            "social_event_id",
            "evidence_kind",
            "source_object_type",
            "source_object_id",
            name="uq_social_event_evidence_source",
        ),
        Index("ix_social_event_evidence_event", "social_event_id"),
        Index("ix_social_event_evidence_source_post", "source_post_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    social_event_id: Mapped[str] = mapped_column(
        ForeignKey("social_events.id"), nullable=False
    )
    evidence_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_object_type: Mapped[str] = mapped_column(String(48), nullable=False)
    source_object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    root_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    source_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    target_post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    source_notification_id: Mapped[int | None] = mapped_column(
        ForeignKey("notifications.id")
    )
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    public_action_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_public_action_executions.id")
    )
    interaction_intent: Mapped[str | None] = mapped_column(String(40))
    comment_purpose: Mapped[str | None] = mapped_column(String(40))
    proposal_decision: Mapped[str | None] = mapped_column(String(20))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    source_visibility_at_event: Mapped[str | None] = mapped_column(String(20))
    source_author_id_at_event: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RelationshipState(Base):
    __tablename__ = "relationship_states"
    __table_args__ = (
        CheckConstraint(
            "actor_world_character_id != target_world_character_id",
            name="ck_relationship_states_not_self",
        ),
        CheckConstraint(
            "familiarity >= 0 AND familiarity <= 100",
            name="ck_relationship_states_familiarity",
        ),
        CheckConstraint(
            "affinity >= -100 AND affinity <= 100",
            name="ck_relationship_states_affinity",
        ),
        CheckConstraint(
            "trust >= -100 AND trust <= 100",
            name="ck_relationship_states_trust",
        ),
        CheckConstraint(
            "tension >= 0 AND tension <= 100",
            name="ck_relationship_states_tension",
        ),
        CheckConstraint(
            "interaction_count >= 0", name="ck_relationship_states_interactions"
        ),
        CheckConstraint("version >= 1", name="ck_relationship_states_version"),
        ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_states_actor_scope",
        ),
        ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_states_target_scope",
        ),
        UniqueConstraint(
            "world_id",
            "actor_world_character_id",
            "target_world_character_id",
            name="uq_relationship_states_direction",
        ),
        UniqueConstraint("id", "world_id", name="uq_relationship_states_scope"),
        Index(
            "ix_relationship_states_actor_updated",
            "actor_world_character_id",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    familiarity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affinity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trust: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tension: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_event_id: Mapped[str | None] = mapped_column(ForeignKey("social_events.id"))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RelationshipStateChange(Base):
    __tablename__ = "relationship_state_changes"
    __table_args__ = (
        CheckConstraint(
            "valence IN ('positive','neutral','negative')",
            name="ck_relationship_state_changes_valence",
        ),
        CheckConstraint(
            "intensity IN ('low','medium')",
            name="ck_relationship_state_changes_intensity",
        ),
        CheckConstraint(
            "not_applied_reason IS NULL OR not_applied_reason IN "
            "('duplicate','daily_delta_cap','no_delta_event')",
            name="ck_relationship_state_changes_reason",
        ),
        ForeignKeyConstraint(
            ["actor_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_state_changes_actor_scope",
        ),
        ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_relationship_state_changes_target_scope",
        ),
        UniqueConstraint(
            "relationship_state_id",
            "social_event_id",
            name="uq_relationship_state_changes_event",
        ),
        Index("ix_relationship_state_changes_world_created", "world_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    relationship_state_id: Mapped[str] = mapped_column(
        ForeignKey("relationship_states.id"), nullable=False
    )
    social_event_id: Mapped[str] = mapped_column(
        ForeignKey("social_events.id"), nullable=False
    )
    world_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    valence: Mapped[str] = mapped_column(String(16), nullable=False)
    intensity: Mapped[str] = mapped_column(String(16), nullable=False)
    delta_familiarity: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    delta_affinity: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    delta_trust: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    delta_tension: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    after_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    not_applied_reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActivityProposal(Base):
    __tablename__ = "activity_proposals"
    __table_args__ = (
        CheckConstraint(
            "proposer_world_character_id != target_world_character_id",
            name="ck_activity_proposals_not_self",
        ),
        CheckConstraint(
            "proposal_version >= 1 AND proposal_version <= 3",
            name="ck_activity_proposals_version_ordinal",
        ),
        CheckConstraint(
            "target_daypart IN ('dawn','morning','afternoon','evening')",
            name="ck_activity_proposals_daypart",
        ),
        CheckConstraint(
            "date_policy IN ('exact','earliest_available')",
            name="ck_activity_proposals_date_policy",
        ),
        CheckConstraint(
            "date_policy != 'exact' OR target_date IS NOT NULL",
            name="ck_activity_proposals_exact_date",
        ),
        CheckConstraint(
            "status IN ('proposed','accepted','rejected','countered','cancelled','expired')",
            name="ck_activity_proposals_status",
        ),
        CheckConstraint("version >= 1", name="ck_activity_proposals_version"),
        ForeignKeyConstraint(
            ["proposer_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_activity_proposals_proposer_scope",
        ),
        ForeignKeyConstraint(
            ["target_world_character_id", "world_id"],
            ["world_characters.id", "world_characters.world_id"],
            name="fk_activity_proposals_target_scope",
        ),
        UniqueConstraint("source_proposal_event_id", name="uq_activity_proposals_source"),
        UniqueConstraint(
            "source_response_event_id", name="uq_activity_proposals_response"
        ),
        UniqueConstraint("idempotency_key", name="uq_activity_proposals_idempotency"),
        Index("ix_activity_proposals_target_status", "target_world_character_id", "status"),
        Index("ix_activity_proposals_world_status", "world_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    root_proposal_id: Mapped[str] = mapped_column(ForeignKey("activity_proposals.id"), nullable=False)
    parent_proposal_id: Mapped[str | None] = mapped_column(ForeignKey("activity_proposals.id"))
    proposal_version: Mapped[int] = mapped_column(Integer, nullable=False)
    proposer_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_world_character_id: Mapped[str] = mapped_column(String(64), nullable=False)
    activity_seed: Mapped[str] = mapped_column(String(500), nullable=False)
    place_key: Mapped[str | None] = mapped_column(String(64))
    target_daypart: Mapped[str] = mapped_column(String(20), nullable=False)
    date_policy: Mapped[str] = mapped_column(String(24), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    proposed_local_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    source_proposal_event_id: Mapped[str] = mapped_column(
        ForeignKey("social_events.id"), nullable=False
    )
    source_response_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("social_events.id")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    countered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GraphProjectionOutbox(Base):
    __tablename__ = "graph_projection_outbox"
    __table_args__ = (
        CheckConstraint(
            "projection_type IN ('social_event','relationship_state','source_exclusion')",
            name="ck_graph_projection_outbox_type",
        ),
        CheckConstraint(
            "status IN ('pending','processing','succeeded','dead','cancelled')",
            name="ck_graph_projection_outbox_status",
        ),
        CheckConstraint(
            "attempt_count >= 0", name="ck_graph_projection_outbox_attempts"
        ),
        UniqueConstraint("dedupe_key", name="uq_graph_projection_outbox_dedupe"),
        UniqueConstraint(
            "projection_type",
            "source_event_id",
            "payload_version",
            name="uq_graph_projection_outbox_event",
        ),
        Index(
            "ix_graph_projection_outbox_pending",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index("ix_graph_projection_outbox_world_created", "world_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    world_id: Mapped[str] = mapped_column(ForeignKey("worlds.id"), nullable=False)
    source_event_id: Mapped[str] = mapped_column(
        ForeignKey("social_events.id"), nullable=False
    )
    projection_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="relationship-v1"
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    source_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_class: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
