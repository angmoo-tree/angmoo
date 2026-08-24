"""Canonical response contracts for relationship-graph reads."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


GraphStatus = Literal[
    "disabled",
    "healthy",
    "lagging",
    "rebuilding",
    "unavailable",
    "timeout",
    "misconfigured",
]


class RelationshipGraphSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelationshipGraphNodeRead(RelationshipGraphSchema):
    world_character_id: str
    character_id: str
    display_name: str
    is_center: bool = False


class RelationshipGraphEdgeRead(RelationshipGraphSchema):
    relationship_state_id: str
    actor_world_character_id: str
    target_world_character_id: str
    familiarity: int
    affinity: int
    trust: int
    tension: int
    interaction_count: int
    relationship_version: int
    last_event_id: str | None = None
    last_event_at: datetime | None = None


class RelationshipGraphEvidenceRead(RelationshipGraphSchema):
    event_id: str
    event_type: str
    occurred_at: datetime
    actor_world_character_id: str
    target_world_character_id: str | None = None
    root_post_id: str | None = None
    source_post_id: str | None = None


class RelationshipGraphQueryMetaRead(RelationshipGraphSchema):
    template: str
    source: Literal["ladybug", "canonical_fallback"]
    graph_status: GraphStatus
    truncated: bool = False
    projection_lag_seconds: float | None = None
    revalidated_node_count: int = 0
    revalidated_edge_count: int = 0
    fallback_reason: str | None = None


class RelationshipGraphRead(RelationshipGraphSchema):
    world_id: str
    center_world_character_id: str
    nodes: list[RelationshipGraphNodeRead] = Field(default_factory=list)
    edges: list[RelationshipGraphEdgeRead] = Field(default_factory=list)
    evidence: list[RelationshipGraphEvidenceRead] = Field(default_factory=list)
    meta: RelationshipGraphQueryMetaRead
