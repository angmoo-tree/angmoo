"""Bounded recall primitives and canonical fact callbacks."""
from __future__ import annotations
from dataclasses import dataclass

from typing import Literal, Protocol

from app.domains.relationships.contracts.graph_query import (
    GraphEvidenceCandidate,
    GraphNodeCandidate,
    GraphRelationshipHit,
    RelationshipGraphQueryPort,
    RelationshipRevalidationFacts,
)
from app.domains.relationships.contracts.graph_read import (GraphProjectionCounts)
from app.domains.relationships.contracts.graph_recall import (
    MAX_GRAPH_RECALL_EVIDENCE,
    MAX_GRAPH_RECALL_RESULTS,
    GraphRecallOperation,
    GraphRecallScope,
    GraphRecallScopeAccess,
)


FallbackMode = Literal["direct", "evidence", "shared", "rank", "none"]


@dataclass(frozen=True, slots=True)
class GraphRecallPrimitiveSpec:
    operation: GraphRecallOperation
    requires_counterpart: bool
    fallback_mode: FallbackMode
    max_results: int = MAX_GRAPH_RECALL_RESULTS


GRAPH_RECALL_PRIMITIVE_REGISTRY = {
    GraphRecallOperation.DIRECT_RELATIONSHIP: GraphRecallPrimitiveSpec(
        operation=GraphRecallOperation.DIRECT_RELATIONSHIP,
        requires_counterpart=True,
        fallback_mode="direct",
    ),
    GraphRecallOperation.RELATIONSHIP_EVIDENCE: GraphRecallPrimitiveSpec(
        operation=GraphRecallOperation.RELATIONSHIP_EVIDENCE,
        requires_counterpart=True,
        fallback_mode="evidence",
        max_results=MAX_GRAPH_RECALL_EVIDENCE,
    ),
    GraphRecallOperation.SHARED_NEIGHBORS: GraphRecallPrimitiveSpec(
        operation=GraphRecallOperation.SHARED_NEIGHBORS,
        requires_counterpart=True,
        fallback_mode="shared",
    ),
    GraphRecallOperation.SHORTEST_PATH: GraphRecallPrimitiveSpec(
        operation=GraphRecallOperation.SHORTEST_PATH,
        requires_counterpart=True,
        fallback_mode="none",
    ),
    GraphRecallOperation.RANK_RELATED_CHARACTERS: GraphRecallPrimitiveSpec(
        operation=GraphRecallOperation.RANK_RELATED_CHARACTERS,
        requires_counterpart=False,
        fallback_mode="rank",
    ),
    GraphRecallOperation.RELATIONSHIP_NEIGHBORHOOD: GraphRecallPrimitiveSpec(
        operation=GraphRecallOperation.RELATIONSHIP_NEIGHBORHOOD,
        requires_counterpart=False,
        fallback_mode="none",
    ),
}


class GraphRecallGateway(Protocol):
    """Canonical facts and graph lifecycle required by graph recall."""

    def graph_recall_scope_access(
        self,
        *,
        scope: GraphRecallScope,
    ) -> GraphRecallScopeAccess: ...

    def projection_counts(self, *, world_id: str) -> GraphProjectionCounts: ...

    def record_projection_metrics(
        self, *, pending_count: int, oldest_pending_age_seconds: float
    ) -> None: ...

    def open_graph_repository(self) -> RelationshipGraphQueryPort: ...

    def close_graph_repository(self) -> None: ...

    def record_fallback(self, *, reason: str) -> None: ...

    def record_stale_edge(self) -> None: ...

    def canonical_direct_hits(
        self,
        *,
        world_id: str,
        center_id: str,
        target_id: str | None,
        limit: int,
    ) -> list[GraphRelationshipHit]: ...

    def relationship_revalidation_facts(
        self,
        *,
        world_id: str,
        hits: list[GraphRelationshipHit],
        subject_world_character_id: str | None = None,
    ) -> dict[str, RelationshipRevalidationFacts]: ...

    def evidence_candidates(
        self,
        *,
        world_id: str,
        event_ids: list[str],
        subject_world_character_id: str | None = None,
    ) -> list[GraphEvidenceCandidate]: ...

    def node_candidates(
        self,
        *,
        world_id: str,
        world_character_ids: set[str],
        subject_world_character_id: str | None = None,
    ) -> list[GraphNodeCandidate]: ...
