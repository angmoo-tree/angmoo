"""Pure direction, visibility, evidence and bounded-result rules for graph recall."""
from __future__ import annotations

from datetime import UTC, datetime

from app.domains.relationships.exceptions import (RelationshipGraphRequestError)
from app.domains.relationships.contracts.graph_query import (
    GraphEvidenceCandidate,
    GraphNodeCandidate,
    GraphPathHit,
    GraphRelationshipHit,
    RelationshipRevalidationFacts,
)

from app.domains.relationships.contracts.graph_recall import (
    GraphRecallDirection,
    GraphRecallEvidence,
    GraphRecallPath,
    GraphRecallQuery,
    GraphRecallRanking,
    GraphRecallRelationship,
    GraphRecallResult,
    GraphRecallScope,
    GraphRecallSource,
    GraphRecallStatus,
)


def _validate_reference(value: str | None, label: str) -> None:
    if value is None or not isinstance(value, str):
        raise RelationshipGraphRequestError(
            f"graph_recall_{label}_required"
        )
    normalized = value.strip()
    if not normalized or normalized != value or len(value) > 256:
        raise RelationshipGraphRequestError(
            f"graph_recall_{label}_invalid"
        )


def _result(
    query: GraphRecallQuery,
    *,
    status: GraphRecallStatus,
    relationships: tuple[GraphRecallRelationship, ...] = (),
    world_character_ids: tuple[str, ...] = (),
    path: GraphRecallPath | None = None,
    evidence: tuple[GraphRecallEvidence, ...] = (),
    candidate_count: int = 0,
    excluded_count: int = 0,
    truncated: bool = False,
) -> GraphRecallResult:
    return GraphRecallResult(
        operation=query.operation,
        status=status,
        source=GraphRecallSource.GRAPH,
        relationships=relationships,
        world_character_ids=world_character_ids,
        path=path,
        evidence=evidence,
        candidate_count=candidate_count,
        excluded_count=excluded_count,
        truncated=truncated,
    )


def _direct_orientation(query: GraphRecallQuery) -> tuple[str, str, bool]:
    subject = query.scope.subject_world_character_id
    counterpart = query.counterpart_world_character_id or ""
    if query.direction is GraphRecallDirection.INCOMING:
        return counterpart, subject, False
    return subject, counterpart, query.direction is GraphRecallDirection.EITHER


def _matches_direction(
    query: GraphRecallQuery,
    hit: GraphRelationshipHit,
) -> bool:
    return _ids_match_direction(
        query,
        actor_id=hit.actor_world_character_id,
        target_id=hit.target_world_character_id,
    )


def _ids_match_direction(
    query: GraphRecallQuery,
    *,
    actor_id: str,
    target_id: str | None,
) -> bool:
    subject = query.scope.subject_world_character_id
    counterpart = query.counterpart_world_character_id
    if counterpart is None:
        return True
    outgoing = (
        actor_id == subject
        and target_id == counterpart
    )
    incoming = (
        actor_id == counterpart
        and target_id == subject
    )
    if query.direction is GraphRecallDirection.OUTGOING:
        return outgoing
    if query.direction is GraphRecallDirection.INCOMING:
        return incoming
    return outgoing or incoming


def _filter_direction(
    query: GraphRecallQuery,
    values: tuple[GraphRecallRelationship, ...],
) -> tuple[tuple[GraphRecallRelationship, ...], int]:
    accepted = tuple(
        value
        for value in values
        if _ids_match_direction(
            query,
            actor_id=value.actor_world_character_id,
            target_id=value.target_world_character_id,
        )
    )
    return accepted, len(values) - len(accepted)


def _evidence_matches_direction(
    query: GraphRecallQuery,
    candidate: GraphEvidenceCandidate | None,
) -> bool:
    return bool(
        candidate is not None
        and _ids_match_direction(
            query,
            actor_id=candidate.actor_world_character_id,
            target_id=candidate.target_world_character_id,
        )
    )


def _relationship_facts_valid(
    scope: GraphRecallScope,
    hit: GraphRelationshipHit,
    facts: RelationshipRevalidationFacts | None,
    canonical: GraphRelationshipHit | None,
) -> bool:
    return bool(
        facts is not None
        and canonical is not None
        and canonical.world_id == scope.world_id
        and hit.world_id == scope.world_id
        and canonical.relationship_state_id == hit.relationship_state_id
        and facts.actor_active
        and facts.target_active
        and not facts.blocked
        and facts.observed_by_subject
        and canonical.actor_world_character_id
        == hit.actor_world_character_id
        and canonical.target_world_character_id
        == hit.target_world_character_id
    )


def _relationship_record(hit: GraphRelationshipHit) -> GraphRecallRelationship:
    return GraphRecallRelationship(
        relationship_state_id=hit.relationship_state_id,
        world_id=hit.world_id,
        actor_world_character_id=hit.actor_world_character_id,
        target_world_character_id=hit.target_world_character_id,
        familiarity=hit.familiarity,
        affinity=hit.affinity,
        trust=hit.trust,
        tension=hit.tension,
        interaction_count=hit.interaction_count,
        relationship_version=hit.relationship_version,
        last_event_id=hit.last_event_id,
        last_event_at=_optional_datetime(hit.last_event_at),
        updated_at=_optional_datetime(hit.updated_at),
    )


def _node_valid(
    scope: GraphRecallScope,
    candidate: GraphNodeCandidate | None,
) -> bool:
    return bool(
        candidate is not None
        and candidate.world_id == scope.world_id
        and not candidate.character_deleted
        and candidate.world_character_status == "active"
        and candidate.membership_status == "active"
        and candidate.membership_world_id == scope.world_id
        and not candidate.blocked_with_subject
    )


def _evidence_candidate_valid(
    scope: GraphRecallScope,
    candidate: GraphEvidenceCandidate | None,
) -> bool:
    if (
        candidate is None
        or candidate.world_id != scope.world_id
        or candidate.result != "succeeded"
        or candidate.retrieval_status != "eligible"
        or not candidate.observed_by_subject
        or candidate.invalidated
    ):
        return False
    return all(
        post.exists
        and post.world_id == scope.world_id
        and not post.deleted
        and not post.report_hidden
        and post.visibility == "public"
        for post in candidate.posts
    )


def _neighbor_ids(
    center_id: str,
    hits: tuple[GraphRecallRelationship, ...],
    direction: GraphRecallDirection,
) -> set[str]:
    values: set[str] = set()
    for hit in hits:
        if (
            direction in {GraphRecallDirection.OUTGOING, GraphRecallDirection.EITHER}
            and hit.actor_world_character_id == center_id
        ):
            values.add(hit.target_world_character_id)
        if (
            direction in {GraphRecallDirection.INCOMING, GraphRecallDirection.EITHER}
            and hit.target_world_character_id == center_id
        ):
            values.add(hit.actor_world_character_id)
    return values


def _path_edges_match_nodes(
    query: GraphRecallQuery,
    path: GraphPathHit,
) -> bool:
    for index, edge in enumerate(path.oriented_edges):
        current = path.world_character_ids[index]
        following = path.world_character_ids[index + 1]
        outgoing = (
            edge.actor_world_character_id == current
            and edge.target_world_character_id == following
        )
        incoming = (
            edge.actor_world_character_id == following
            and edge.target_world_character_id == current
        )
        if query.direction is GraphRecallDirection.OUTGOING and not outgoing:
            return False
        if query.direction is GraphRecallDirection.INCOMING and not incoming:
            return False
        if query.direction is GraphRecallDirection.EITHER and not (
            outgoing or incoming
        ):
            return False
    return True


def _bounded_neighborhood(
    center_id: str,
    relationships: tuple[GraphRecallRelationship, ...],
    *,
    depth: int,
) -> tuple[tuple[GraphRecallRelationship, ...], set[str]]:
    reached = {center_id}
    selected: list[GraphRecallRelationship] = []
    selected_ids: set[str] = set()
    frontier = {center_id}
    for _ in range(depth):
        next_frontier: set[str] = set()
        for relationship in relationships:
            relationship_id = relationship.relationship_state_id
            if relationship_id in selected_ids:
                continue
            actor = relationship.actor_world_character_id
            target = relationship.target_world_character_id
            if actor not in frontier and target not in frontier:
                continue
            selected.append(relationship)
            selected_ids.add(relationship_id)
            if actor not in reached:
                next_frontier.add(actor)
            if target not in reached:
                next_frontier.add(target)
            reached.update((actor, target))
        frontier = next_frontier
        if not frontier:
            break
    return tuple(selected), reached


def _rank_key(
    value: GraphRecallRelationship,
    mode: GraphRecallRanking,
) -> tuple[object, ...]:
    if mode is GraphRecallRanking.TENSE:
        return (value.tension, value.interaction_count, value.relationship_state_id)
    if mode is GraphRecallRanking.RECENT:
        return (
            value.updated_at or datetime.min.replace(tzinfo=UTC),
            value.interaction_count,
            value.relationship_state_id,
        )
    return (
        value.affinity + value.trust,
        value.familiarity,
        value.interaction_count,
        value.relationship_state_id,
    )


def _optional_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    try:
        return _as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
