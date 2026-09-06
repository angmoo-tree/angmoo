"""Ports and query result types for relationship-graph reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable


DirectionMode = Literal["outgoing", "incoming", "either"]
RankingMode = Literal["positive", "tense", "recent"]


class GraphQueryTemplate(StrEnum):
    """Provider-neutral names for the bounded relationship read workload."""

    DIRECT_RELATIONSHIP = "direct_relationship"
    SHARED_NEIGHBORS_OUTGOING = "shared_neighbors_outgoing"
    SHARED_NEIGHBORS_INCOMING = "shared_neighbors_incoming"
    SHARED_NEIGHBORS_EITHER = "shared_neighbors_either"
    SHORTEST_PATH_OUTGOING_1 = "shortest_path_outgoing_1"
    SHORTEST_PATH_OUTGOING_2 = "shortest_path_outgoing_2"
    SHORTEST_PATH_OUTGOING_3 = "shortest_path_outgoing_3"
    SHORTEST_PATH_INCOMING_1 = "shortest_path_incoming_1"
    SHORTEST_PATH_INCOMING_2 = "shortest_path_incoming_2"
    SHORTEST_PATH_INCOMING_3 = "shortest_path_incoming_3"
    SHORTEST_PATH_EITHER_1 = "shortest_path_either_1"
    SHORTEST_PATH_EITHER_2 = "shortest_path_either_2"
    SHORTEST_PATH_EITHER_3 = "shortest_path_either_3"
    RANK_POSITIVE = "ranked_related_positive"
    RANK_TENSE = "ranked_related_tense"
    RANK_RECENT = "ranked_related_recent"
    RELATIONSHIP_EVIDENCE = "relationship_evidence"
    VISUALIZATION_1 = "visualization_neighborhood_1"
    VISUALIZATION_2 = "visualization_neighborhood_2"


@dataclass(frozen=True)
class GraphRelationshipHit:
    world_id: str
    actor_world_character_id: str
    target_world_character_id: str
    relationship_state_id: str
    familiarity: int
    affinity: int
    trust: int
    tension: int
    interaction_count: int
    relationship_version: int
    last_event_id: str | None = None
    last_event_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphPathHit:
    world_character_ids: tuple[str, ...]
    oriented_edges: tuple[GraphRelationshipHit, ...]
    hop_count: int


@dataclass(frozen=True)
class GraphEvidenceHit:
    event_id: str
    event_type: str
    occurred_at: datetime | str
    relationship_state_id: str
    relationship_version: int


@dataclass(frozen=True)
class GraphNeighborhoodHit:
    center_world_character_id: str
    nodes: tuple[str, ...]
    edges: tuple[GraphRelationshipHit, ...]
    truncated: bool


@dataclass(frozen=True)
class OwnerWorldCharacterAccess:
    character_exists: bool
    character_deleted: bool
    character_owner_id: str | None
    world_character_id: str | None
    world_character_status: str | None
    membership_status: str | None
    membership_world_id: str | None


@dataclass(frozen=True)
class RelationshipRevalidationFacts:
    canonical_hit: GraphRelationshipHit | None
    actor_active: bool
    target_active: bool
    blocked: bool
    observed_by_subject: bool = True


@dataclass(frozen=True)
class EvidencePostFacts:
    post_id: str
    root_post_id: str | None
    source_post_id: str | None
    exists: bool
    world_id: str | None
    deleted: bool
    report_hidden: bool
    visibility: str | None


@dataclass(frozen=True)
class GraphEvidenceCandidate:
    event_id: str
    event_type: str
    occurred_at: datetime
    actor_world_character_id: str
    target_world_character_id: str | None
    world_id: str
    result: str
    retrieval_status: str
    posts: tuple[EvidencePostFacts, ...]
    observed_by_subject: bool = True
    invalidated: bool = False


@dataclass(frozen=True)
class GraphNodeCandidate:
    world_character_id: str
    world_id: str
    character_id: str
    display_name: str
    character_deleted: bool
    world_character_status: str | None = "active"
    membership_status: str | None = "active"
    membership_world_id: str | None = None
    blocked_with_subject: bool = False


@runtime_checkable
class RelationshipGraphQueryPort(Protocol):
    def get_direct_relationship(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        include_reverse: bool = False,
    ) -> list[GraphRelationshipHit]: ...

    def list_shared_neighbors(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        direction_mode: DirectionMode = "either",
        limit: int = 20,
    ) -> list[str]: ...

    def find_shortest_path(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        direction_mode: DirectionMode = "either",
        max_hops: int = 2,
    ) -> GraphPathHit | None: ...

    def rank_related_characters(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        mode: RankingMode = "positive",
        limit: int = 20,
    ) -> list[GraphRelationshipHit]: ...

    def list_relationship_evidence(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        limit: int = 3,
    ) -> list[GraphEvidenceHit]: ...

    def get_visualization_neighborhood(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        depth: int = 1,
        node_limit: int = 20,
        edge_limit: int = 40,
    ) -> GraphNeighborhoodHit: ...
