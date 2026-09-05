"""Owner graph read inputs and canonical fact callbacks."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import (datetime)
from typing import Literal, Protocol


from app.domains.relationships.contracts.graph_query import (
    GraphEvidenceCandidate,
    GraphNodeCandidate,
    GraphRelationshipHit,
    OwnerWorldCharacterAccess,
    RelationshipGraphQueryPort,
    RelationshipRevalidationFacts,
)


GraphView = Literal["neighborhood", "direct", "evidence"]


GraphProvider = Literal["ladybug"]


@dataclass(frozen=True)
class GraphProjectionCounts:
    pending: int
    processing: int
    oldest_pending_at: datetime | None
    active_replay: bool
    failed_rebuild: bool


class RelationshipGraphReadGateway(Protocol):
    """Persistence and integration facts required by the read use case."""

    def owner_access(
        self,
        *,
        character_id: str,
        world_id: str,
    ) -> OwnerWorldCharacterAccess: ...

    def target_world_id(self, *, world_character_id: str) -> str | None: ...

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
