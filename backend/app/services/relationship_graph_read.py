from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import Settings, settings
from app.cruds import graph_projection as graph_projection_crud
from app.integrations.neo4j import GraphClientError
from app.repositories.relationship_graph import (
    GraphEvidenceHit,
    GraphRelationshipHit,
    RelationshipGraphRepository,
)
from app.services.graph_projection_metrics import graph_metrics
from app.services.graph_projection_runtime import graph_client_from_settings


GraphView = Literal["neighborhood", "direct", "evidence"]


class RelationshipGraphReadError(RuntimeError):
    reason_code = "relationship_graph_read_error"


class RelationshipGraphNotFoundError(RelationshipGraphReadError):
    reason_code = "world_character_not_found"


class RelationshipGraphForbiddenError(RelationshipGraphReadError):
    reason_code = "character_not_owned"


class RelationshipGraphRequestError(RelationshipGraphReadError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _owner_world_character(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: models.User,
) -> models.WorldCharacter:
    character = db.get(models.Character, character_id)
    if character is None or character.deleted_at is not None:
        raise RelationshipGraphNotFoundError(character_id)
    if character.owner_id != user.id:
        raise RelationshipGraphForbiddenError(character_id)
    world_character = db.scalar(
        select(models.WorldCharacter).where(
            models.WorldCharacter.world_id == world_id,
            models.WorldCharacter.character_id == character_id,
        )
    )
    if world_character is None:
        raise RelationshipGraphNotFoundError(character_id)
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        world_character.status != "active"
        or membership is None
        or membership.status != "active"
        or membership.world_id != world_id
    ):
        raise RelationshipGraphRequestError("membership_inactive")
    return world_character


def _blocked_pairs(db: Session, *, world_id: str) -> set[frozenset[str]]:
    return {
        frozenset(
            (
                row.blocker_world_character_id,
                row.blocked_world_character_id,
            )
        )
        for row in db.scalars(
            select(models.WorldCharacterBlock).where(
                models.WorldCharacterBlock.world_id == world_id
            )
        )
    }


def _relationship_hit(row: models.RelationshipState) -> GraphRelationshipHit:
    return GraphRelationshipHit(
        world_id=row.world_id,
        actor_world_character_id=row.actor_world_character_id,
        target_world_character_id=row.target_world_character_id,
        relationship_state_id=row.id,
        familiarity=row.familiarity,
        affinity=row.affinity,
        trust=row.trust,
        tension=row.tension,
        interaction_count=row.interaction_count,
        relationship_version=row.version,
        last_event_id=row.last_event_id,
        last_event_at=row.last_event_at,
        updated_at=row.updated_at,
    )


def _postgres_direct_hits(
    db: Session,
    *,
    world_id: str,
    center_id: str,
    target_id: str | None,
    limit: int,
) -> list[GraphRelationshipHit]:
    statement = select(models.RelationshipState).where(
        models.RelationshipState.world_id == world_id
    )
    if target_id is None:
        statement = statement.where(
            or_(
                models.RelationshipState.actor_world_character_id == center_id,
                models.RelationshipState.target_world_character_id == center_id,
            )
        )
    else:
        statement = statement.where(
            or_(
                (
                    (models.RelationshipState.actor_world_character_id == center_id)
                    & (
                        models.RelationshipState.target_world_character_id
                        == target_id
                    )
                ),
                (
                    (models.RelationshipState.actor_world_character_id == target_id)
                    & (
                        models.RelationshipState.target_world_character_id
                        == center_id
                    )
                ),
            )
        )
    rows = list(
        db.scalars(
            statement.order_by(
                models.RelationshipState.updated_at.desc(),
                models.RelationshipState.id.asc(),
            ).limit(limit)
        )
    )
    return [_relationship_hit(row) for row in rows]


def _revalidate_relationships(
    db: Session,
    *,
    world_id: str,
    hits: list[GraphRelationshipHit],
    allow_stale_replace: bool,
) -> list[GraphRelationshipHit]:
    if not hits:
        return []
    rows = {
        row.id: row
        for row in db.scalars(
            select(models.RelationshipState).where(
                models.RelationshipState.id.in_(
                    [hit.relationship_state_id for hit in hits]
                ),
                models.RelationshipState.world_id == world_id,
            )
        )
    }
    world_character_ids = {
        value
        for hit in hits
        for value in (
            hit.actor_world_character_id,
            hit.target_world_character_id,
        )
    }
    world_characters = {
        row.id: row
        for row in db.scalars(
            select(models.WorldCharacter).where(
                models.WorldCharacter.id.in_(world_character_ids),
                models.WorldCharacter.world_id == world_id,
                models.WorldCharacter.status == "active",
            )
        )
    }
    membership_ids = {row.membership_id for row in world_characters.values()}
    active_memberships = {
        row.id
        for row in db.scalars(
            select(models.WorldMembership).where(
                models.WorldMembership.id.in_(membership_ids),
                models.WorldMembership.world_id == world_id,
                models.WorldMembership.status == "active",
            )
        )
    }
    blocked = _blocked_pairs(db, world_id=world_id)
    result = []
    for hit in hits:
        row = rows.get(hit.relationship_state_id)
        actor = world_characters.get(hit.actor_world_character_id)
        target = world_characters.get(hit.target_world_character_id)
        if (
            row is None
            or actor is None
            or target is None
            or actor.membership_id not in active_memberships
            or target.membership_id not in active_memberships
            or frozenset((actor.id, target.id)) in blocked
            or row.actor_world_character_id != hit.actor_world_character_id
            or row.target_world_character_id != hit.target_world_character_id
        ):
            continue
        if row.version != hit.relationship_version:
            graph_metrics.increment("graph_query_stale_edge_total")
            if allow_stale_replace:
                result.append(_relationship_hit(row))
            continue
        result.append(hit)
    return result


def _evidence_reads(
    db: Session,
    *,
    world_id: str,
    event_ids: list[str],
    limit: int,
) -> list[schemas.RelationshipGraphEvidenceRead]:
    if not event_ids:
        return []
    events = {
        row.id: row
        for row in db.scalars(
            select(models.SocialEvent).where(
                models.SocialEvent.id.in_(event_ids),
                models.SocialEvent.world_id == world_id,
                models.SocialEvent.result == "succeeded",
                models.SocialEvent.retrieval_status == "eligible",
            )
        )
    }
    evidence_rows = list(
        db.scalars(
            select(models.SocialEventEvidence).where(
                models.SocialEventEvidence.social_event_id.in_(events)
            )
        )
    )
    evidence_by_event: dict[str, list[models.SocialEventEvidence]] = {}
    for evidence in evidence_rows:
        evidence_by_event.setdefault(evidence.social_event_id, []).append(evidence)
    result = []
    for event_id in event_ids:
        event = events.get(event_id)
        if event is None:
            continue
        source_post_id = None
        valid = True
        for evidence in evidence_by_event.get(event_id, []):
            post_id = (
                evidence.source_post_id
                or evidence.target_post_id
                or evidence.root_post_id
                or (
                    evidence.source_object_id
                    if evidence.source_object_type == "post"
                    else None
                )
            )
            if post_id is None:
                continue
            post = db.get(models.Post, post_id)
            if (
                post is None
                or post.world_id != world_id
                or post.deleted_at is not None
                or post.report_hidden_at is not None
                or post.visibility != "public"
            ):
                valid = False
                break
            source_post_id = evidence.source_post_id or post_id
        if valid:
            result.append(
                schemas.RelationshipGraphEvidenceRead(
                    event_id=event.id,
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    actor_world_character_id=event.actor_world_character_id,
                    target_world_character_id=event.target_world_character_id,
                    source_post_id=source_post_id,
                )
            )
        if len(result) >= limit:
            break
    return result


def _node_reads(
    db: Session,
    *,
    world_id: str,
    center_id: str,
    edges: list[GraphRelationshipHit],
) -> list[schemas.RelationshipGraphNodeRead]:
    ids = {center_id}
    for edge in edges:
        ids.add(edge.actor_world_character_id)
        ids.add(edge.target_world_character_id)
    world_characters = {
        row.id: row
        for row in db.scalars(
            select(models.WorldCharacter).where(
                models.WorldCharacter.id.in_(ids),
                models.WorldCharacter.world_id == world_id,
            )
        )
    }
    characters = {
        row.id: row
        for row in db.scalars(
            select(models.Character).where(
                models.Character.id.in_(
                    [row.character_id for row in world_characters.values()]
                )
            )
        )
    }
    result = []
    for world_character_id in sorted(world_characters):
        world_character = world_characters[world_character_id]
        character = characters.get(world_character.character_id)
        if character is None or character.deleted_at is not None:
            continue
        result.append(
            schemas.RelationshipGraphNodeRead(
                world_character_id=world_character.id,
                character_id=character.id,
                display_name=character.name,
                is_center=world_character.id == center_id,
            )
        )
    return result


def get_owner_relationship_graph(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: models.User,
    view: GraphView = "neighborhood",
    target_world_character_id: str | None = None,
    depth: int = 1,
    limit: int = 20,
    config: Settings = settings,
    repository: RelationshipGraphRepository | None = None,
) -> schemas.RelationshipGraphRead:
    if view not in {"neighborhood", "direct", "evidence"}:
        raise RelationshipGraphRequestError("graph_view_invalid")
    if view in {"direct", "evidence"} and not target_world_character_id:
        raise RelationshipGraphRequestError("target_world_character_required")
    depth = max(1, min(depth, 2))
    limit = max(1, min(limit, 20))
    center = _owner_world_character(
        db,
        character_id=character_id,
        world_id=world_id,
        user=user,
    )
    if target_world_character_id is not None:
        target = db.get(models.WorldCharacter, target_world_character_id)
        if target is None or target.world_id != world_id:
            raise RelationshipGraphRequestError("world_mismatch")

    counts = graph_projection_crud.world_counts(db, world_id=world_id)
    now = datetime.now(UTC)
    oldest = counts.oldest_pending_at
    if oldest is not None:
        oldest = oldest.replace(tzinfo=UTC) if oldest.tzinfo is None else oldest
    lag = max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
    graph_metrics.set_gauge(
        "graph_projection_pending_count",
        counts.pending + counts.processing,
    )
    graph_metrics.set_gauge(
        "graph_projection_oldest_pending_age_seconds", lag
    )
    source: Literal["neo4j", "postgres_fallback"] = "neo4j"
    fallback_reason: str | None = None
    template = {
        "neighborhood": f"visualization_neighborhood_{depth}",
        "direct": "direct_relationship",
        "evidence": "relationship_evidence",
    }[view]
    truncated = False
    client = None
    graph_status: schemas.GraphStatus

    try:
        if repository is None and not config.graph_projection_enabled:
            raise GraphClientError("graph_disabled")
        if counts.active_replay:
            raise GraphClientError("graph_rebuilding")
        if counts.failed_rebuild:
            raise GraphClientError("graph_rebuild_failed")
        if repository is None:
            client = graph_client_from_settings(config)
            client.verify_connectivity()
            repository = RelationshipGraphRepository(client)
        if view == "neighborhood":
            neighborhood = repository.get_visualization_neighborhood(
                world_id=world_id,
                source_world_character_id=center.id,
                depth=depth,
                node_limit=limit,
                edge_limit=min(limit * 2, 40),
            )
            graph_hits = list(neighborhood.edges)
            truncated = neighborhood.truncated
        else:
            graph_hits = repository.get_direct_relationship(
                world_id=world_id,
                source_world_character_id=center.id,
                target_world_character_id=target_world_character_id or "",
                include_reverse=True,
            )
        graph_hits = _revalidate_relationships(
            db,
            world_id=world_id,
            hits=graph_hits,
            allow_stale_replace=view in {"direct", "evidence"},
        )
        graph_status = (
            "lagging" if counts.pending or counts.processing else "healthy"
        )
    except GraphClientError as exc:
        graph_metrics.increment(
            "graph_query_fallback_total", reason=exc.error_class
        )
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
        graph_hits = _postgres_direct_hits(
            db,
            world_id=world_id,
            center_id=center.id,
            target_id=target_world_character_id,
            limit=min(limit * 2, 40),
        )
        graph_hits = _revalidate_relationships(
            db,
            world_id=world_id,
            hits=graph_hits,
            allow_stale_replace=True,
        )

    event_ids: list[str] = []
    if view == "evidence" and repository is not None and source == "neo4j":
        try:
            event_hits: list[GraphEvidenceHit] = repository.list_relationship_evidence(
                world_id=world_id,
                source_world_character_id=center.id,
                target_world_character_id=target_world_character_id or "",
                limit=5,
            )
            event_ids = [hit.event_id for hit in event_hits]
        except GraphClientError:
            event_ids = []
    if client is not None:
        client.close()
    if not event_ids:
        event_ids = [
            hit.last_event_id
            for hit in graph_hits
            if hit.last_event_id is not None
        ][:5]
    evidence = _evidence_reads(
        db,
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
        center_world_character_id=center.id,
        nodes=_node_reads(
            db,
            world_id=world_id,
            center_id=center.id,
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
                {center.id}
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
