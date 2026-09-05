"""Runtime composition from SQLAlchemy/LadybugDB to graph-read domain.

Current consumers are the relationship-graph API route and social-memory
diagnostics. SQLite supplies canonical fallback facts and LadybugDB supplies
the replayable graph projection.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.config import Settings, settings
from app.runtime.graph_projection import sqlalchemy_state as graph_projection_crud
from app.domains.relationships import public as relationships
from app.domains.relationships.graph_read import schemas
from app.domains.relationships.graph_read.errors import GraphReadBackendError
from app.domains.relationships.graph_read.repository import (
    EvidencePostFacts,
    GraphEvidenceCandidate,
    GraphEvidenceHit,
    GraphNeighborhoodHit,
    GraphNodeCandidate,
    GraphPathHit,
    GraphRelationshipHit,
    OwnerWorldCharacterAccess,
    RelationshipGraphQueryPort,
    RelationshipRevalidationFacts,
)
from app.domains.relationships.graph_read.use_case import GraphProjectionCounts
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.domains.relationships.ports.projection import (
    RelationshipProjectionBackendError,
)
from app.integrations.relationship_graph_read import RelationshipGraphRepository
from app.runtime.graph_projection.metrics import graph_metrics
from app.runtime.graph_projection.process_client import (
    borrow_process_graph_client,
)


class _BackendErrorMappingRepository:
    """Normalize graph-provider transport errors before they enter the domain."""

    def __init__(self, delegate: RelationshipGraphQueryPort) -> None:
        self._delegate = delegate

    def _call(self, method_name: str, **kwargs):
        try:
            return getattr(self._delegate, method_name)(**kwargs)
        except RelationshipProjectionBackendError as exc:
            raise GraphReadBackendError(exc.error_class) from exc

    def get_direct_relationship(self, **kwargs) -> list[GraphRelationshipHit]:
        return self._call("get_direct_relationship", **kwargs)

    def list_shared_neighbors(self, **kwargs) -> list[str]:
        return self._call("list_shared_neighbors", **kwargs)

    def find_shortest_path(self, **kwargs) -> GraphPathHit | None:
        return self._call("find_shortest_path", **kwargs)

    def rank_related_characters(self, **kwargs) -> list[GraphRelationshipHit]:
        return self._call("rank_related_characters", **kwargs)

    def list_relationship_evidence(self, **kwargs) -> list[GraphEvidenceHit]:
        return self._call("list_relationship_evidence", **kwargs)

    def get_visualization_neighborhood(self, **kwargs) -> GraphNeighborhoodHit:
        return self._call("get_visualization_neighborhood", **kwargs)


class SqlAlchemyRelationshipGraphReadGateway:
    """SQLAlchemy/runtime adapter for the canonical read use case."""

    def __init__(
        self,
        db: Session,
        *,
        config: Settings = settings,
        graph_provider: relationships.GraphProvider = "ladybug",
    ) -> None:
        self._db = db
        self._config = config
        self._graph_provider = graph_provider
        self._client = None
        self._client_owned = False

    def owner_access(
        self,
        *,
        character_id: str,
        world_id: str,
    ) -> OwnerWorldCharacterAccess:
        character = self._db.get(models.Character, character_id)
        if character is None:
            return OwnerWorldCharacterAccess(
                character_exists=False,
                character_deleted=False,
                character_owner_id=None,
                world_character_id=None,
                world_character_status=None,
                membership_status=None,
                membership_world_id=None,
            )
        world_character = self._db.scalar(
            select(models.WorldCharacter).where(
                models.WorldCharacter.world_id == world_id,
                models.WorldCharacter.character_id == character_id,
            )
        )
        membership = (
            self._db.get(models.WorldMembership, world_character.membership_id)
            if world_character is not None
            else None
        )
        return OwnerWorldCharacterAccess(
            character_exists=True,
            character_deleted=character.deleted_at is not None,
            character_owner_id=character.owner_id,
            world_character_id=(
                world_character.id if world_character is not None else None
            ),
            world_character_status=(
                world_character.status if world_character is not None else None
            ),
            membership_status=(
                membership.status if membership is not None else None
            ),
            membership_world_id=(
                membership.world_id if membership is not None else None
            ),
        )

    def graph_recall_scope_access(
        self,
        *,
        scope: relationships.GraphRecallScope,
    ) -> relationships.GraphRecallScopeAccess:
        world_character = self._db.get(
            models.WorldCharacter,
            scope.subject_world_character_id,
        )
        character = (
            self._db.get(models.Character, world_character.character_id)
            if world_character is not None
            else None
        )
        membership = (
            self._db.get(models.WorldMembership, world_character.membership_id)
            if world_character is not None
            else None
        )
        return relationships.GraphRecallScopeAccess(
            subject_exists=world_character is not None and character is not None,
            subject_world_id=(
                world_character.world_id
                if world_character is not None
                else None
            ),
            character_deleted=(
                character.deleted_at is not None
                if character is not None
                else False
            ),
            character_owner_id=(
                character.owner_id if character is not None else None
            ),
            world_character_status=(
                world_character.status
                if world_character is not None
                else None
            ),
            membership_status=(
                membership.status if membership is not None else None
            ),
            membership_world_id=(
                membership.world_id if membership is not None else None
            ),
        )

    def target_world_id(self, *, world_character_id: str) -> str | None:
        target = self._db.get(models.WorldCharacter, world_character_id)
        return target.world_id if target is not None else None
    def projection_counts(self, *, world_id: str) -> GraphProjectionCounts:
        counts = graph_projection_crud.world_counts(self._db, world_id=world_id)
        return GraphProjectionCounts(
            pending=counts.pending,
            processing=counts.processing,
            oldest_pending_at=counts.oldest_pending_at,
            active_replay=counts.active_replay,
            failed_rebuild=counts.failed_rebuild,
        )

    def record_projection_metrics(
        self, *, pending_count: int, oldest_pending_age_seconds: float
    ) -> None:
        graph_metrics.set_gauge("graph_projection_pending_count", pending_count)
        graph_metrics.set_gauge(
            "graph_projection_oldest_pending_age_seconds",
            oldest_pending_age_seconds,
        )

    def open_graph_repository(self) -> RelationshipGraphQueryPort:
        if self._graph_provider != "ladybug":
            raise GraphReadBackendError("graph_provider_unsupported")
        shared = borrow_process_graph_client(self._config)
        if shared is not None:
            try:
                shared.verify_connectivity()
            except RelationshipProjectionBackendError as exc:
                raise GraphReadBackendError(exc.error_class) from exc
            self._client = shared
            self._client_owned = False
            return _BackendErrorMappingRepository(
                RelationshipGraphRepository(shared)
            )
        projection = None
        try:
            projection = LadybugRelationshipProjection(
                database_root=self._config.ladybug_database_root
            )
            self._client = projection
            self._client_owned = True
            projection.verify_connectivity()
        except RelationshipProjectionBackendError as exc:
            if projection is not None:
                projection.close()
            self._client = None
            raise GraphReadBackendError(exc.error_class) from exc
        return _BackendErrorMappingRepository(
            RelationshipGraphRepository(projection)
        )

    def close_graph_repository(self) -> None:
        if self._client is not None:
            if self._client_owned:
                self._client.close()
            self._client = None
            self._client_owned = False

    def record_fallback(self, *, reason: str) -> None:
        graph_metrics.increment("graph_query_fallback_total", reason=reason)

    def record_stale_edge(self) -> None:
        graph_metrics.increment("graph_query_stale_edge_total")

    def _blocked_pairs(self, *, world_id: str) -> set[frozenset[str]]:
        return {
            frozenset(
                (
                    row.blocker_world_character_id,
                    row.blocked_world_character_id,
                )
            )
            for row in self._db.scalars(
                select(models.WorldCharacterBlock).where(
                    models.WorldCharacterBlock.world_id == world_id
                )
            )
        }

    @staticmethod
    def _relationship_hit(
        row: models.RelationshipState,
    ) -> GraphRelationshipHit:
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

    def canonical_direct_hits(
        self,
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
                        (
                            models.RelationshipState.actor_world_character_id
                            == center_id
                        )
                        & (
                            models.RelationshipState.target_world_character_id
                            == target_id
                        )
                    ),
                    (
                        (
                            models.RelationshipState.actor_world_character_id
                            == target_id
                        )
                        & (
                            models.RelationshipState.target_world_character_id
                            == center_id
                        )
                    ),
                )
            )
        rows = list(
            self._db.scalars(
                statement.order_by(
                    models.RelationshipState.updated_at.desc(),
                    models.RelationshipState.id.asc(),
                ).limit(limit)
            )
        )
        return [self._relationship_hit(row) for row in rows]

    def relationship_revalidation_facts(
        self,
        *,
        world_id: str,
        hits: list[GraphRelationshipHit],
        subject_world_character_id: str | None = None,
    ) -> dict[str, RelationshipRevalidationFacts]:
        if not hits:
            return {}
        rows = {
            row.id: row
            for row in self._db.scalars(
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
            for row in self._db.scalars(
                select(models.WorldCharacter).where(
                    models.WorldCharacter.id.in_(world_character_ids),
                    models.WorldCharacter.world_id == world_id,
                )
            )
        }
        membership_ids = {
            row.membership_id for row in world_characters.values()
        }
        active_memberships = {
            row.id
            for row in self._db.scalars(
                select(models.WorldMembership).where(
                    models.WorldMembership.id.in_(membership_ids),
                    models.WorldMembership.world_id == world_id,
                    models.WorldMembership.status == "active",
                )
            )
        }
        blocked = self._blocked_pairs(world_id=world_id)
        event_ids = {
            value
            for hit in hits
            for value in (hit.last_event_id,)
            if value is not None
        }
        event_ids.update(
            row.last_event_id
            for row in rows.values()
            if row.last_event_id is not None
        )
        observed_event_ids = self._subject_observed_event_ids(
            world_id=world_id,
            subject_world_character_id=subject_world_character_id,
            event_ids=event_ids,
        )
        facts: dict[str, RelationshipRevalidationFacts] = {}
        for hit in hits:
            row = rows.get(hit.relationship_state_id)
            actor = world_characters.get(hit.actor_world_character_id)
            target = world_characters.get(hit.target_world_character_id)
            facts[hit.relationship_state_id] = RelationshipRevalidationFacts(
                canonical_hit=(
                    self._relationship_hit(row) if row is not None else None
                ),
                actor_active=(
                    actor is not None
                    and actor.status == "active"
                    and actor.membership_id in active_memberships
                ),
                target_active=(
                    target is not None
                    and target.status == "active"
                    and target.membership_id in active_memberships
                ),
                blocked=(
                    actor is not None
                    and target is not None
                    and frozenset((actor.id, target.id)) in blocked
                ),
                observed_by_subject=(
                    subject_world_character_id is None
                    or (
                        row is not None
                        and row.last_event_id in observed_event_ids
                    )
                ),
            )
        return facts

    def _subject_observed_event_ids(
        self,
        *,
        world_id: str,
        subject_world_character_id: str | None,
        event_ids: set[str],
    ) -> set[str]:
        if subject_world_character_id is None:
            return set(event_ids)
        if not event_ids:
            return set()
        events = {
            row.id: row
            for row in self._db.scalars(
                select(models.SocialEvent).where(
                    models.SocialEvent.id.in_(event_ids),
                    models.SocialEvent.world_id == world_id,
                    models.SocialEvent.result == "succeeded",
                    models.SocialEvent.retrieval_status == "eligible",
                    models.SocialEvent.invalidated_at.is_(None),
                )
            )
        }
        observed = {
            event.id
            for event in events.values()
            if subject_world_character_id
            in {
                event.actor_world_character_id,
                event.target_world_character_id,
            }
        }
        remaining = set(events) - observed
        if not remaining:
            return observed
        evidence_rows = list(
            self._db.scalars(
                select(models.SocialEventEvidence).where(
                    models.SocialEventEvidence.social_event_id.in_(remaining)
                )
            )
        )
        post_events: dict[str, set[str]] = {}
        for evidence in evidence_rows:
            post_ids = {
                value
                for value in (
                    evidence.source_post_id,
                    evidence.target_post_id,
                    evidence.root_post_id,
                    (
                        evidence.source_object_id
                        if evidence.source_object_type == "post"
                        else None
                    ),
                )
                if value is not None
            }
            for post_id in post_ids:
                post_events.setdefault(post_id, set()).add(
                    evidence.social_event_id
                )
        if not post_events:
            return observed
        observed_post_ids = set(
            self._db.scalars(
                select(models.WorldCharacterFeedObservation.post_id).where(
                    models.WorldCharacterFeedObservation.world_id == world_id,
                    models.WorldCharacterFeedObservation.observer_world_character_id
                    == subject_world_character_id,
                    models.WorldCharacterFeedObservation.post_id.in_(post_events),
                    models.WorldCharacterFeedObservation.status == "observed",
                    models.WorldCharacterFeedObservation.observed_at.is_not(None),
                )
            )
        )
        for post_id in observed_post_ids:
            observed.update(post_events.get(post_id, ()))
        return observed

    def evidence_candidates(
        self,
        *,
        world_id: str,
        event_ids: list[str],
        subject_world_character_id: str | None = None,
    ) -> list[GraphEvidenceCandidate]:
        if not event_ids:
            return []
        events = {
            row.id: row
            for row in self._db.scalars(
                select(models.SocialEvent).where(
                    models.SocialEvent.id.in_(event_ids)
                )
            )
        }
        evidence_rows = list(
            self._db.scalars(
                select(models.SocialEventEvidence).where(
                    models.SocialEventEvidence.social_event_id.in_(events)
                )
            )
        )
        evidence_by_event: dict[str, list[models.SocialEventEvidence]] = {}
        for evidence in evidence_rows:
            evidence_by_event.setdefault(
                evidence.social_event_id, []
            ).append(evidence)

        observed_event_ids = self._subject_observed_event_ids(
            world_id=world_id,
            subject_world_character_id=subject_world_character_id,
            event_ids=set(event_ids),
        )

        result = []
        for event_id in event_ids:
            event = events.get(event_id)
            if event is None:
                continue
            posts = []
            for evidence_row in evidence_by_event.get(event_id, []):
                post_ids = tuple(
                    dict.fromkeys(
                        value
                        for value in (
                            evidence_row.source_post_id,
                            evidence_row.target_post_id,
                            evidence_row.root_post_id,
                            (
                                evidence_row.source_object_id
                                if evidence_row.source_object_type == "post"
                                else None
                            ),
                        )
                        if value is not None
                    )
                )
                for post_id in post_ids:
                    post = self._db.get(models.Post, post_id)
                    posts.append(
                        EvidencePostFacts(
                            post_id=post_id,
                            root_post_id=evidence_row.root_post_id,
                            source_post_id=evidence_row.source_post_id,
                            exists=post is not None,
                            world_id=(
                                post.world_id if post is not None else None
                            ),
                            deleted=(
                                post.deleted_at is not None
                                if post is not None
                                else False
                            ),
                            report_hidden=(
                                post.report_hidden_at is not None
                                if post is not None
                                else False
                            ),
                            visibility=(
                                post.visibility if post is not None else None
                            ),
                        )
                    )
            result.append(
                GraphEvidenceCandidate(
                    event_id=event.id,
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    actor_world_character_id=event.actor_world_character_id,
                    target_world_character_id=(
                        event.target_world_character_id
                    ),
                    world_id=event.world_id,
                    result=event.result,
                    retrieval_status=event.retrieval_status,
                    posts=tuple(posts),
                    observed_by_subject=(
                        subject_world_character_id is None
                        or event.id in observed_event_ids
                    ),
                    invalidated=event.invalidated_at is not None,
                )
            )
        return result

    def node_candidates(
        self,
        *,
        world_id: str,
        world_character_ids: set[str],
        subject_world_character_id: str | None = None,
    ) -> list[GraphNodeCandidate]:
        world_characters = {
            row.id: row
            for row in self._db.scalars(
                select(models.WorldCharacter).where(
                    models.WorldCharacter.id.in_(world_character_ids)
                )
            )
        }
        characters = {
            row.id: row
            for row in self._db.scalars(
                select(models.Character).where(
                    models.Character.id.in_(
                        [row.character_id for row in world_characters.values()]
                    )
                )
            )
        }
        memberships = {
            row.id: row
            for row in self._db.scalars(
                select(models.WorldMembership).where(
                    models.WorldMembership.id.in_(
                        [
                            row.membership_id
                            for row in world_characters.values()
                        ]
                    )
                )
            )
        }
        blocked = self._blocked_pairs(world_id=world_id)
        result = []
        for world_character_id in sorted(world_characters):
            world_character = world_characters[world_character_id]
            character = characters.get(world_character.character_id)
            if character is None:
                continue
            membership = memberships.get(world_character.membership_id)
            result.append(
                GraphNodeCandidate(
                    world_character_id=world_character.id,
                    world_id=world_character.world_id,
                    character_id=character.id,
                    display_name=character.name,
                    character_deleted=character.deleted_at is not None,
                    world_character_status=world_character.status,
                    membership_status=(
                        membership.status if membership is not None else None
                    ),
                    membership_world_id=(
                        membership.world_id if membership is not None else None
                    ),
                    blocked_with_subject=(
                        subject_world_character_id is not None
                        and world_character.id
                        != subject_world_character_id
                        and frozenset(
                            (
                                subject_world_character_id,
                                world_character.id,
                            )
                        )
                        in blocked
                    ),
                )
            )
        return result

def get_owner_relationship_graph(
    db: Session,
    *,
    character_id: str,
    world_id: str,
    user: models.User,
    view: relationships.GraphView = "neighborhood",
    target_world_character_id: str | None = None,
    depth: int = 1,
    limit: int = 20,
    config: Settings = settings,
    repository: RelationshipGraphQueryPort | None = None,
    graph_provider: relationships.GraphProvider = "ladybug",
) -> relationships.RelationshipGraphRead:
    """Compose the SQLAlchemy adapter with the domain-owned read use case."""

    gateway = SqlAlchemyRelationshipGraphReadGateway(
        db,
        config=config,
        graph_provider=graph_provider,
    )
    mapped_repository = (
        _BackendErrorMappingRepository(repository)
        if repository is not None
        else None
    )
    return relationships.get_owner_relationship_graph(
        gateway,
        character_id=character_id,
        world_id=world_id,
        owner_id=user.id,
        view=view,
        target_world_character_id=target_world_character_id,
        depth=depth,
        limit=limit,
        graph_projection_enabled=config.graph_projection_enabled,
        repository=mapped_repository,
        graph_provider=graph_provider,
    )


def execute_graph_recall(
    db: Session,
    *,
    query: relationships.GraphRecallQuery,
    config: Settings = settings,
    repository: RelationshipGraphQueryPort | None = None,
    graph_provider: relationships.GraphProvider = "ladybug",
) -> relationships.GraphRecallResult:
    """Compose runtime adapters behind the relationships public facade."""

    gateway = SqlAlchemyRelationshipGraphReadGateway(
        db,
        config=config,
        graph_provider=graph_provider,
    )
    mapped_repository = (
        _BackendErrorMappingRepository(repository)
        if repository is not None
        else None
    )
    return relationships.GraphRecallService(gateway).execute(
        query,
        graph_projection_enabled=config.graph_projection_enabled,
        repository=mapped_repository,
    )


# Infrastructure consumers use the exact domain-owned contract types.
GraphStatus = relationships.GraphStatus
GraphView = relationships.GraphView
RelationshipGraphForbiddenError = relationships.RelationshipGraphForbiddenError
RelationshipGraphNotFoundError = relationships.RelationshipGraphNotFoundError
RelationshipGraphRead = relationships.RelationshipGraphRead
RelationshipGraphReadError = relationships.RelationshipGraphReadError
RelationshipGraphRequestError = relationships.RelationshipGraphRequestError
