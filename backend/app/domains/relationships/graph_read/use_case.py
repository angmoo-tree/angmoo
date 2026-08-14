"""Owner-only relationship-graph read orchestration.

The domain owns authorization, World isolation, stale/blocked filtering,
fallback selection, evidence visibility, and response assembly. SQLAlchemy and
projection-runtime details are supplied as facts through a narrow L4 gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from app.domains.relationships.graph_read import schemas
from app.domains.relationships.graph_read.errors import (
    GraphReadBackendError,
    RelationshipGraphForbiddenError,
    RelationshipGraphNotFoundError,
    RelationshipGraphRequestError,
)
from app.domains.relationships.graph_read.repository import (
    GraphEvidenceCandidate,
    GraphNodeCandidate,
    GraphRelationshipHit,
    OwnerWorldCharacterAccess,
    RelationshipGraphQueryPort,
    RelationshipRevalidationFacts,
)


GraphView = Literal["neighborhood", "direct", "evidence"]


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

    def postgres_direct_hits(
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
    ) -> dict[str, RelationshipRevalidationFacts]: ...

    def evidence_candidates(
        self,
        *,
        world_id: str,
        event_ids: list[str],
    ) -> list[GraphEvidenceCandidate]: ...

    def node_candidates(
        self,
        *,
        world_id: str,
        world_character_ids: set[str],
    ) -> list[GraphNodeCandidate]: ...


def _owner_world_character(
    gateway: RelationshipGraphReadGateway,
    *,
    character_id: str,
    world_id: str,
    owner_id: str,
) -> str:
    access = gateway.owner_access(
        character_id=character_id,
        world_id=world_id,
    )
    if not access.character_exists or access.character_deleted:
        raise RelationshipGraphNotFoundError(character_id)
    if access.character_owner_id != owner_id:
        raise RelationshipGraphForbiddenError(character_id)
    if access.world_character_id is None:
        raise RelationshipGraphNotFoundError(character_id)
    if (
        access.world_character_status != "active"
        or access.membership_status != "active"
        or access.membership_world_id != world_id
    ):
        raise RelationshipGraphRequestError("membership_inactive")
    return access.world_character_id


def _revalidate_relationships(
    gateway: RelationshipGraphReadGateway,
    *,
    world_id: str,
    hits: list[GraphRelationshipHit],
    allow_stale_replace: bool,
) -> list[GraphRelationshipHit]:
    if not hits:
        return []
    facts_by_state_id = gateway.relationship_revalidation_facts(
        world_id=world_id,
        hits=hits,
    )
    result = []
    for hit in hits:
        facts = facts_by_state_id.get(hit.relationship_state_id)
        canonical = facts.canonical_hit if facts is not None else None
        if (
            facts is None
            or canonical is None
            or canonical.world_id != world_id
            or not facts.actor_active
            or not facts.target_active
            or facts.blocked
            or canonical.actor_world_character_id
            != hit.actor_world_character_id
            or canonical.target_world_character_id
            != hit.target_world_character_id
        ):
            continue
        if canonical.relationship_version != hit.relationship_version:
            gateway.record_stale_edge()
            if allow_stale_replace:
                result.append(canonical)
            continue
        result.append(hit)
    return result


def _evidence_reads(
    gateway: RelationshipGraphReadGateway,
    *,
    world_id: str,
    event_ids: list[str],
    limit: int,
) -> list[schemas.RelationshipGraphEvidenceRead]:
    if not event_ids:
        return []
    candidates = {
        candidate.event_id: candidate
        for candidate in gateway.evidence_candidates(
            world_id=world_id,
            event_ids=event_ids,
        )
    }
    result = []
    for event_id in event_ids:
        candidate = candidates.get(event_id)
        if (
            candidate is None
            or candidate.world_id != world_id
            or candidate.result != "succeeded"
            or candidate.retrieval_status != "eligible"
        ):
            continue
        source_post_id = None
        valid = True
        for post in candidate.posts:
            if (
                not post.exists
                or post.world_id != world_id
                or post.deleted
                or post.report_hidden
                or post.visibility != "public"
            ):
                valid = False
                break
            source_post_id = post.source_post_id or post.post_id
        if valid:
            result.append(
                schemas.RelationshipGraphEvidenceRead(
                    event_id=candidate.event_id,
                    event_type=candidate.event_type,
                    occurred_at=candidate.occurred_at,
                    actor_world_character_id=(
                        candidate.actor_world_character_id
                    ),
                    target_world_character_id=(
                        candidate.target_world_character_id
                    ),
                    source_post_id=source_post_id,
                )
            )
        if len(result) >= limit:
            break
    return result


def _node_reads(
    gateway: RelationshipGraphReadGateway,
    *,
    world_id: str,
    center_id: str,
    edges: list[GraphRelationshipHit],
) -> list[schemas.RelationshipGraphNodeRead]:
    world_character_ids = {center_id}
    for edge in edges:
        world_character_ids.add(edge.actor_world_character_id)
        world_character_ids.add(edge.target_world_character_id)
    candidates = gateway.node_candidates(
        world_id=world_id,
        world_character_ids=world_character_ids,
    )
    return [
        schemas.RelationshipGraphNodeRead(
            world_character_id=candidate.world_character_id,
            character_id=candidate.character_id,
            display_name=candidate.display_name,
            is_center=candidate.world_character_id == center_id,
        )
        for candidate in sorted(
            candidates,
            key=lambda value: value.world_character_id,
        )
        if candidate.world_id == world_id and not candidate.character_deleted
    ]


def get_owner_relationship_graph(
    gateway: RelationshipGraphReadGateway,
    *,
    character_id: str,
    world_id: str,
    owner_id: str,
    view: GraphView = "neighborhood",
    target_world_character_id: str | None = None,
    depth: int = 1,
    limit: int = 20,
    graph_projection_enabled: bool = True,
    repository: RelationshipGraphQueryPort | None = None,
) -> schemas.RelationshipGraphRead:
    if view not in {"neighborhood", "direct", "evidence"}:
        raise RelationshipGraphRequestError("graph_view_invalid")
    if view in {"direct", "evidence"} and not target_world_character_id:
        raise RelationshipGraphRequestError("target_world_character_required")

    depth = max(1, min(depth, 2))
    limit = max(1, min(limit, 20))
    center_id = _owner_world_character(
        gateway,
        character_id=character_id,
        world_id=world_id,
        owner_id=owner_id,
    )
    if (
        target_world_character_id is not None
        and gateway.target_world_id(
            world_character_id=target_world_character_id
        )
        != world_id
    ):
        raise RelationshipGraphRequestError("world_mismatch")

    counts = gateway.projection_counts(world_id=world_id)
    now = datetime.now(UTC)
    oldest = counts.oldest_pending_at
    if oldest is not None:
        oldest = oldest.replace(tzinfo=UTC) if oldest.tzinfo is None else oldest
    lag = max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
    gateway.record_projection_metrics(
        pending_count=counts.pending + counts.processing,
        oldest_pending_age_seconds=lag,
    )

    source: Literal["neo4j", "postgres_fallback"] = "neo4j"
    fallback_reason: str | None = None
    template = {
        "neighborhood": f"visualization_neighborhood_{depth}",
        "direct": "direct_relationship",
        "evidence": "relationship_evidence",
    }[view]
    truncated = False
    graph_status: schemas.GraphStatus
    opened_repository = False

    try:
        if repository is None and not graph_projection_enabled:
            raise GraphReadBackendError("graph_disabled")
        if counts.active_replay:
            raise GraphReadBackendError("graph_rebuilding")
        if counts.failed_rebuild:
            raise GraphReadBackendError("graph_rebuild_failed")
        if repository is None:
            repository = gateway.open_graph_repository()
            opened_repository = True

        if view == "neighborhood":
            neighborhood = repository.get_visualization_neighborhood(
                world_id=world_id,
                source_world_character_id=center_id,
                depth=depth,
                node_limit=limit,
                edge_limit=min(limit * 2, 40),
            )
            graph_hits = list(neighborhood.edges)
            truncated = neighborhood.truncated
        else:
            graph_hits = repository.get_direct_relationship(
                world_id=world_id,
                source_world_character_id=center_id,
                target_world_character_id=target_world_character_id or "",
                include_reverse=True,
            )
        graph_hits = _revalidate_relationships(
            gateway,
            world_id=world_id,
            hits=graph_hits,
            allow_stale_replace=view in {"direct", "evidence"},
        )
        graph_status = (
            "lagging" if counts.pending or counts.processing else "healthy"
        )
    except GraphReadBackendError as exc:
        gateway.record_fallback(reason=exc.error_class)
        source = "postgres_fallback"
        fallback_reason = exc.error_class
        if exc.error_class == "graph_disabled":
            graph_status = "disabled"
        elif exc.error_class == "graph_rebuilding":
            graph_status = "rebuilding"
        elif exc.error_class == "neo4j_query_timeout":
            graph_status = "timeout"
        elif exc.error_class in {"neo4j_auth_invalid", "schema_not_ready"}:
            graph_status = "misconfigured"
        else:
            graph_status = "unavailable"
        graph_hits = gateway.postgres_direct_hits(
            world_id=world_id,
            center_id=center_id,
            target_id=target_world_character_id,
            limit=min(limit * 2, 40),
        )
        graph_hits = _revalidate_relationships(
            gateway,
            world_id=world_id,
            hits=graph_hits,
            allow_stale_replace=True,
        )

    event_ids: list[str] = []
    if view == "evidence" and repository is not None and source == "neo4j":
        try:
            event_hits = repository.list_relationship_evidence(
                world_id=world_id,
                source_world_character_id=center_id,
                target_world_character_id=target_world_character_id or "",
                limit=5,
            )
            event_ids = [hit.event_id for hit in event_hits]
        except GraphReadBackendError:
            event_ids = []
    if opened_repository:
        gateway.close_graph_repository()
    if not event_ids:
        event_ids = [
            hit.last_event_id
            for hit in graph_hits
            if hit.last_event_id is not None
        ][:5]

    evidence = _evidence_reads(
        gateway,
        world_id=world_id,
        event_ids=event_ids,
        limit=5,
    )
    edges = [
        schemas.RelationshipGraphEdgeRead(
            relationship_state_id=hit.relationship_state_id,
            actor_world_character_id=hit.actor_world_character_id,
            target_world_character_id=hit.target_world_character_id,
            familiarity=hit.familiarity,
            affinity=hit.affinity,
            trust=hit.trust,
            tension=hit.tension,
            interaction_count=hit.interaction_count,
            relationship_version=hit.relationship_version,
            last_event_id=hit.last_event_id,
            last_event_at=hit.last_event_at,
        )
        for hit in graph_hits[:40]
    ]
    return schemas.RelationshipGraphRead(
        world_id=world_id,
        center_world_character_id=center_id,
        nodes=_node_reads(
            gateway,
            world_id=world_id,
            center_id=center_id,
            edges=graph_hits,
        )[:limit],
        edges=edges,
        evidence=evidence,
        meta=schemas.RelationshipGraphQueryMetaRead(
            template=template,
            source=source,
            graph_status=graph_status,
            truncated=truncated,
            projection_lag_seconds=lag,
            revalidated_node_count=len(
                {center_id}
                | {
                    value
                    for hit in graph_hits
                    for value in (
                        hit.actor_world_character_id,
                        hit.target_world_character_id,
                    )
                }
            ),
            revalidated_edge_count=len(graph_hits),
            fallback_reason=fallback_reason,
        ),
    )