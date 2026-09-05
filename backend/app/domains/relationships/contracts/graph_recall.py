"""Framework-free contracts for bounded, evidence-safe graph recall."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


GRAPH_RECALL_CONTRACT_VERSION = "graph-recall.v1"
MAX_GRAPH_RECALL_RESULTS = 20
MAX_GRAPH_RECALL_HOPS = 3
MAX_GRAPH_RECALL_EVIDENCE = 5
MAX_GRAPH_RECALL_EDGES = 40


class GraphRecallOperation(StrEnum):
    DIRECT_RELATIONSHIP = "direct_relationship"
    RELATIONSHIP_EVIDENCE = "relationship_evidence"
    SHARED_NEIGHBORS = "shared_neighbors"
    SHORTEST_PATH = "shortest_path"
    RANK_RELATED_CHARACTERS = "rank_related_characters"
    RELATIONSHIP_NEIGHBORHOOD = "relationship_neighborhood"


class GraphRecallDirection(StrEnum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"
    EITHER = "either"


class GraphRecallRanking(StrEnum):
    POSITIVE = "positive"
    TENSE = "tense"
    RECENT = "recent"


class GraphRecallStatus(StrEnum):
    READY = "ready"
    LAGGING = "lagging"
    DEGRADED = "degraded"


class GraphRecallSource(StrEnum):
    GRAPH = "graph"
    CANONICAL_FALLBACK = "canonical_fallback"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class GraphRecallScope:
    owner_id: str
    world_id: str
    subject_world_character_id: str


@dataclass(frozen=True, slots=True)
class GraphRecallScopeAccess:
    subject_exists: bool
    subject_world_id: str | None
    character_deleted: bool
    character_owner_id: str | None
    world_character_status: str | None
    membership_status: str | None
    membership_world_id: str | None


@dataclass(frozen=True, slots=True)
class GraphRecallQuery:
    operation: GraphRecallOperation
    scope: GraphRecallScope
    counterpart_world_character_id: str | None = None
    direction: GraphRecallDirection = GraphRecallDirection.OUTGOING
    ranking: GraphRecallRanking = GraphRecallRanking.POSITIVE
    max_hops: int = 2
    depth: int = 1
    limit: int = 5


@dataclass(frozen=True, slots=True)
class GraphRecallRelationship:
    relationship_state_id: str
    world_id: str
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
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class GraphRecallEvidence:
    event_id: str
    event_type: str
    occurred_at: datetime
    actor_world_character_id: str
    target_world_character_id: str | None
    root_post_id: str | None = None
    source_post_id: str | None = None


@dataclass(frozen=True, slots=True)
class GraphRecallPath:
    world_character_ids: tuple[str, ...]
    relationships: tuple[GraphRecallRelationship, ...]
    hop_count: int


@dataclass(frozen=True, slots=True)
class GraphRecallResult:
    operation: GraphRecallOperation
    status: GraphRecallStatus
    source: GraphRecallSource
    relationships: tuple[GraphRecallRelationship, ...] = ()
    world_character_ids: tuple[str, ...] = ()
    path: GraphRecallPath | None = None
    evidence: tuple[GraphRecallEvidence, ...] = ()
    candidate_count: int = 0
    excluded_count: int = 0
    truncated: bool = False
    reason_code: str | None = None


__all__ = [
    "GRAPH_RECALL_CONTRACT_VERSION",
    "MAX_GRAPH_RECALL_EDGES",
    "MAX_GRAPH_RECALL_EVIDENCE",
    "MAX_GRAPH_RECALL_HOPS",
    "MAX_GRAPH_RECALL_RESULTS",
    "GraphRecallDirection",
    "GraphRecallEvidence",
    "GraphRecallOperation",
    "GraphRecallPath",
    "GraphRecallQuery",
    "GraphRecallRanking",
    "GraphRecallRelationship",
    "GraphRecallResult",
    "GraphRecallScope",
    "GraphRecallScopeAccess",
    "GraphRecallSource",
    "GraphRecallStatus",
]
