from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SocialMemorySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SocialEventEvidenceRead(SocialMemorySchema):
    evidence_kind: str
    source_object_type: str
    source_object_id: str
    root_post_id: str | None = None
    source_post_id: str | None = None
    target_post_id: str | None = None
    source_status: Literal["available", "excluded"]
    exclusion_reason: str | None = None


class SocialEventRead(SocialMemorySchema):
    id: str
    world_id: str
    actor_world_character_id: str
    target_world_character_id: str | None = None
    event_type: str
    occurred_at: datetime
    retrieval_status: str
    evidence: list[SocialEventEvidenceRead] = Field(default_factory=list)


class RelationshipStateRead(SocialMemorySchema):
    id: str
    actor_world_character_id: str
    target_world_character_id: str
    familiarity: int
    affinity: int
    trust: int
    tension: int
    interaction_count: int
    last_event_id: str | None = None
    last_event_at: datetime | None = None
    version: int


class ActivityProposalRead(SocialMemorySchema):
    id: str
    proposer_world_character_id: str
    target_world_character_id: str
    activity_seed: str
    place_key: str | None = None
    target_daypart: str
    date_policy: str
    target_date: date | None = None
    status: str
    expires_at: datetime


class JointActivityParticipantRead(SocialMemorySchema):
    world_character_id: str
    role: str
    participation_status: str
    linked_daily_activity_plan_item_id: str | None = None
    linked_activity_episode_id: str | None = None
    represented_at: datetime | None = None
    last_joint_post_id: str | None = None


class JointActivityRead(SocialMemorySchema):
    id: str
    proposal_id: str | None = None
    activity_seed: str
    place_key: str | None = None
    scheduled_local_date: date | None = None
    target_daypart: str | None = None
    timezone_snapshot: str | None = None
    status: str
    opening_post_id: str | None = None
    opened_by_world_character_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    participants: list[JointActivityParticipantRead] = Field(default_factory=list)


class SocialMemoryDiagnosticsRead(SocialMemorySchema):
    world_id: str
    world_character_id: str
    recent_events: list[SocialEventRead] = Field(default_factory=list)
    outgoing_relationships: list[RelationshipStateRead] = Field(default_factory=list)
    incoming_relationships: list[RelationshipStateRead] = Field(default_factory=list)
    open_proposals: list[ActivityProposalRead] = Field(default_factory=list)
    active_joint_activities: list[JointActivityRead] = Field(default_factory=list)
    graph_outbox_pending_count: int = 0
    graph_outbox_processing_count: int = 0
    graph_outbox_dead_count: int = 0
    graph_oldest_pending_age_seconds: float | None = None
    graph_last_succeeded_at: datetime | None = None
    relationship_graph_status: Literal[
        "disabled",
        "healthy",
        "lagging",
        "rebuilding",
        "unavailable",
        "timeout",
        "misconfigured",
    ] = "disabled"
    latest_relationship_version_parity: bool | None = None
    graph_replay_active: bool = False
