from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domains.relationships import public as relationships
from app.domains.relationships.graph_read.errors import GraphReadBackendError
from app.domains.relationships.graph_read.repository import (
    EvidencePostFacts,
    GraphEvidenceCandidate,
    GraphEvidenceHit,
    GraphNeighborhoodHit,
    GraphNodeCandidate,
    GraphPathHit,
    GraphRelationshipHit,
    RelationshipRevalidationFacts,
)
from app.runtime.graph_projection.relationship_graph_read import (
    execute_graph_recall,
)
from p7_graph_support import seed_projection_fixture, sqlite_engine


NOW = datetime(2026, 9, 2, 1, 0, tzinfo=UTC)
WORLD_ID = "world-graph-recall"
OWNER_ID = "owner-graph-recall"
SUBJECT_ID = "wc-subject"
COUNTERPART_ID = "wc-counterpart"
NEIGHBOR_ID = "wc-neighbor"


def _scope() -> relationships.GraphRecallScope:
    return relationships.GraphRecallScope(
        owner_id=OWNER_ID,
        world_id=WORLD_ID,
        subject_world_character_id=SUBJECT_ID,
    )


def _hit(
    actor: str,
    target: str,
    *,
    state_id: str | None = None,
    version: int = 1,
    last_event_id: str | None = None,
    affinity: int = 3,
    tension: int = 1,
) -> GraphRelationshipHit:
    return GraphRelationshipHit(
        world_id=WORLD_ID,
        actor_world_character_id=actor,
        target_world_character_id=target,
        relationship_state_id=state_id or f"rel-{actor}-{target}",
        familiarity=5,
        affinity=affinity,
        trust=2,
        tension=tension,
        interaction_count=4,
        relationship_version=version,
        last_event_id=last_event_id or f"event-{actor}-{target}",
        last_event_at=NOW,
        updated_at=NOW,
    )


class FakeGraphRepository:
    def __init__(self) -> None:
        self.direct: list[GraphRelationshipHit] = []
        self.shared: list[str] = []
        self.path: GraphPathHit | None = None
        self.ranked: list[GraphRelationshipHit] = []
        self.evidence: list[GraphEvidenceHit] = []
        self.neighborhood = GraphNeighborhoodHit(
            center_world_character_id=SUBJECT_ID,
            nodes=(SUBJECT_ID,),
            edges=(),
            truncated=False,
        )
        self.failure: str | None = None
        self.calls: list[str] = []

    def _ready(self, name: str) -> None:
        self.calls.append(name)
        if self.failure is not None:
            raise GraphReadBackendError(self.failure)

    def get_direct_relationship(self, **_kwargs) -> list[GraphRelationshipHit]:
        self._ready("direct_relationship")
        return list(self.direct)

    def list_shared_neighbors(self, **_kwargs) -> list[str]:
        self._ready("shared_neighbors")
        return list(self.shared)

    def find_shortest_path(self, **_kwargs) -> GraphPathHit | None:
        self._ready("shortest_path")
        return self.path

    def rank_related_characters(self, **_kwargs) -> list[GraphRelationshipHit]:
        self._ready("rank_related_characters")
        return list(self.ranked)

    def list_relationship_evidence(self, **_kwargs) -> list[GraphEvidenceHit]:
        self._ready("relationship_evidence")
        return list(self.evidence)

    def get_visualization_neighborhood(self, **_kwargs) -> GraphNeighborhoodHit:
        self._ready("relationship_neighborhood")
        return self.neighborhood


class FakeGraphRecallGateway:
    def __init__(self, repository: FakeGraphRepository) -> None:
        self.repository = repository
        self.canonical_by_state: dict[str, GraphRelationshipHit] = {}
        self.observed_by_state: dict[str, bool] = {}
        self.blocked_states: set[str] = set()
        self.canonical_by_center: dict[str, list[GraphRelationshipHit]] = {}
        self.evidence_by_id: dict[str, GraphEvidenceCandidate] = {}
        self.invalid_nodes: set[str] = set()
        self.blocked_nodes: set[str] = set()
        self.counts = relationships.GraphProjectionCounts(
            pending=0,
            processing=0,
            oldest_pending_at=None,
            active_replay=False,
            failed_rebuild=False,
        )
        self.fallback_reasons: list[str] = []
        self.stale_edges = 0
        self.open_count = 0
        self.close_count = 0

    def graph_recall_scope_access(self, *, scope):
        return relationships.GraphRecallScopeAccess(
            subject_exists=True,
            subject_world_id=scope.world_id,
            character_deleted=False,
            character_owner_id=OWNER_ID,
            world_character_status="active",
            membership_status="active",
            membership_world_id=scope.world_id,
        )

    def projection_counts(self, *, world_id):
        assert world_id == WORLD_ID
        return self.counts

    def record_projection_metrics(self, **_kwargs) -> None:
        return None

    def open_graph_repository(self):
        self.open_count += 1
        return self.repository

    def close_graph_repository(self) -> None:
        self.close_count += 1

    def record_fallback(self, *, reason: str) -> None:
        self.fallback_reasons.append(reason)

    def record_stale_edge(self) -> None:
        self.stale_edges += 1

    def canonical_direct_hits(
        self,
        *,
        world_id,
        center_id,
        target_id,
        limit,
    ):
        del target_id
        assert world_id == WORLD_ID
        return list(self.canonical_by_center.get(center_id, ()))[:limit]

    def relationship_revalidation_facts(
        self,
        *,
        world_id,
        hits,
        subject_world_character_id=None,
    ):
        assert world_id == WORLD_ID
        assert subject_world_character_id in {None, SUBJECT_ID}
        return {
            hit.relationship_state_id: RelationshipRevalidationFacts(
                canonical_hit=self.canonical_by_state.get(
                    hit.relationship_state_id
                ),
                actor_active=True,
                target_active=True,
                blocked=hit.relationship_state_id in self.blocked_states,
                observed_by_subject=self.observed_by_state.get(
                    hit.relationship_state_id,
                    True,
                ),
            )
            for hit in hits
        }

    def evidence_candidates(
        self,
        *,
        world_id,
        event_ids,
        subject_world_character_id=None,
    ):
        assert world_id == WORLD_ID
        assert subject_world_character_id in {None, SUBJECT_ID}
        return [
            self.evidence_by_id[event_id]
            for event_id in event_ids
            if event_id in self.evidence_by_id
        ]

    def node_candidates(
        self,
        *,
        world_id,
        world_character_ids,
        subject_world_character_id=None,
    ):
        assert world_id == WORLD_ID
        assert subject_world_character_id in {None, SUBJECT_ID}
        return [
            GraphNodeCandidate(
                world_character_id=value,
                world_id=WORLD_ID,
                character_id=f"character-{value}",
                display_name=value,
                character_deleted=value in self.invalid_nodes,
                world_character_status="active",
                membership_status="active",
                membership_world_id=WORLD_ID,
                blocked_with_subject=value in self.blocked_nodes,
            )
            for value in world_character_ids
        ]


def _gateway_with(
    *hits: GraphRelationshipHit,
) -> tuple[FakeGraphRepository, FakeGraphRecallGateway]:
    graph = FakeGraphRepository()
    gateway = FakeGraphRecallGateway(graph)
    gateway.canonical_by_state.update(
        (value.relationship_state_id, value) for value in hits
    )
    for value in hits:
        gateway.canonical_by_center.setdefault(
            value.actor_world_character_id,
            [],
        ).append(value)
        gateway.canonical_by_center.setdefault(
            value.target_world_character_id,
            [],
        ).append(value)
    return graph, gateway


def _evidence(event_id: str) -> GraphEvidenceCandidate:
    return GraphEvidenceCandidate(
        event_id=event_id,
        event_type="comment_created",
        occurred_at=NOW,
        actor_world_character_id=SUBJECT_ID,
        target_world_character_id=COUNTERPART_ID,
        world_id=WORLD_ID,
        result="succeeded",
        retrieval_status="eligible",
        posts=(
            EvidencePostFacts(
                post_id="post-1",
                root_post_id="post-root",
                source_post_id="post-1",
                exists=True,
                world_id=WORLD_ID,
                deleted=False,
                report_hidden=False,
                visibility="public",
            ),
        ),
        observed_by_subject=True,
    )


def test_graph_recall_registry_is_closed_and_validator_enforces_hard_caps() -> None:
    assert set(relationships.GRAPH_RECALL_PRIMITIVE_REGISTRY) == set(
        relationships.GraphRecallOperation
    )
    assert len(relationships.GRAPH_RECALL_PRIMITIVE_REGISTRY) == 6
    validator = relationships.GraphRecallValidator()
    with pytest.raises(
        relationships.RelationshipGraphRequestError,
        match="counterpart_world_character_required",
    ):
        validator.validate(
            relationships.GraphRecallQuery(
                operation=(
                    relationships.GraphRecallOperation.DIRECT_RELATIONSHIP
                ),
                scope=_scope(),
            )
        )
    with pytest.raises(
        relationships.RelationshipGraphRequestError,
        match="limit_invalid",
    ):
        validator.validate(
            relationships.GraphRecallQuery(
                operation=(
                    relationships.GraphRecallOperation.SHARED_NEIGHBORS
                ),
                scope=_scope(),
                counterpart_world_character_id=COUNTERPART_ID,
                limit=21,
            )
        )
    with pytest.raises(
        relationships.RelationshipGraphRequestError,
        match="hops_invalid",
    ):
        validator.validate(
            relationships.GraphRecallQuery(
                operation=relationships.GraphRecallOperation.SHORTEST_PATH,
                scope=_scope(),
                counterpart_world_character_id=COUNTERPART_ID,
                max_hops=4,
            )
        )


def test_direct_and_evidence_replace_stale_projection_and_filter_unobserved() -> None:
    stale = _hit(SUBJECT_ID, COUNTERPART_ID, version=1)
    canonical = replace(stale, relationship_version=2, affinity=9)
    graph, gateway = _gateway_with(canonical)
    graph.direct = [stale]
    graph.evidence = [
        GraphEvidenceHit(
            event_id=canonical.last_event_id or "",
            event_type="comment_created",
            occurred_at=NOW,
            relationship_state_id=canonical.relationship_state_id,
            relationship_version=1,
        )
    ]
    gateway.evidence_by_id[canonical.last_event_id or ""] = _evidence(
        canonical.last_event_id or ""
    )
    service = relationships.GraphRecallService(gateway)

    direct = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.DIRECT_RELATIONSHIP,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
        ),
        repository=graph,
    )
    assert direct.status is relationships.GraphRecallStatus.READY
    assert direct.source is relationships.GraphRecallSource.GRAPH
    assert direct.relationships[0].relationship_version == 2
    assert direct.relationships[0].affinity == 9
    assert gateway.stale_edges == 1

    evidence = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.RELATIONSHIP_EVIDENCE,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
            limit=5,
        ),
        repository=graph,
    )
    assert [value.event_id for value in evidence.evidence] == [
        canonical.last_event_id
    ]
    gateway.observed_by_state[canonical.relationship_state_id] = False
    gateway.evidence_by_id[canonical.last_event_id or ""] = replace(
        gateway.evidence_by_id[canonical.last_event_id or ""],
        observed_by_subject=False,
    )
    unobserved = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.RELATIONSHIP_EVIDENCE,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
            limit=5,
        ),
        repository=graph,
    )
    assert unobserved.relationships == ()
    assert unobserved.evidence == ()
    assert unobserved.excluded_count == 2


def test_shared_path_rank_and_neighborhood_are_canonically_revalidated() -> None:
    subject_neighbor = _hit(SUBJECT_ID, NEIGHBOR_ID)
    counterpart_neighbor = _hit(COUNTERPART_ID, NEIGHBOR_ID)
    subject_counterpart = _hit(
        SUBJECT_ID,
        COUNTERPART_ID,
        affinity=12,
    )
    graph, gateway = _gateway_with(
        subject_neighbor,
        counterpart_neighbor,
        subject_counterpart,
    )
    graph.shared = [NEIGHBOR_ID, "wc-stale"]
    graph.path = GraphPathHit(
        world_character_ids=(SUBJECT_ID, NEIGHBOR_ID, COUNTERPART_ID),
        oriented_edges=(
            subject_neighbor,
            replace(
                counterpart_neighbor,
                actor_world_character_id=NEIGHBOR_ID,
                target_world_character_id=COUNTERPART_ID,
                relationship_state_id="rel-neighbor-counterpart",
            ),
        ),
        hop_count=2,
    )
    path_edge = graph.path.oriented_edges[1]
    gateway.canonical_by_state[path_edge.relationship_state_id] = path_edge
    graph.ranked = [subject_counterpart]
    graph.neighborhood = GraphNeighborhoodHit(
        center_world_character_id=SUBJECT_ID,
        nodes=(SUBJECT_ID, NEIGHBOR_ID, COUNTERPART_ID),
        edges=(subject_neighbor, subject_counterpart),
        truncated=False,
    )
    service = relationships.GraphRecallService(gateway)

    shared = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.SHARED_NEIGHBORS,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
            direction=relationships.GraphRecallDirection.OUTGOING,
        ),
        repository=graph,
    )
    assert shared.world_character_ids == (NEIGHBOR_ID,)
    assert shared.excluded_count == 1

    path = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.SHORTEST_PATH,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
            direction=relationships.GraphRecallDirection.EITHER,
            max_hops=2,
        ),
        repository=graph,
    )
    assert path.path is not None
    assert path.path.world_character_ids == (
        SUBJECT_ID,
        NEIGHBOR_ID,
        COUNTERPART_ID,
    )

    ranked = service.execute(
        relationships.GraphRecallQuery(
            operation=(
                relationships.GraphRecallOperation.RANK_RELATED_CHARACTERS
            ),
            scope=_scope(),
            ranking=relationships.GraphRecallRanking.POSITIVE,
        ),
        repository=graph,
    )
    assert ranked.world_character_ids == (COUNTERPART_ID,)

    neighborhood = service.execute(
        relationships.GraphRecallQuery(
            operation=(
                relationships.GraphRecallOperation.RELATIONSHIP_NEIGHBORHOOD
            ),
            scope=_scope(),
        ),
        repository=graph,
    )
    assert set(neighborhood.world_character_ids) == {
        SUBJECT_ID,
        NEIGHBOR_ID,
        COUNTERPART_ID,
    }


@pytest.mark.parametrize(
    ("operation", "expected_source", "expected_count"),
    (
        (
            relationships.GraphRecallOperation.DIRECT_RELATIONSHIP,
            relationships.GraphRecallSource.CANONICAL_FALLBACK,
            1,
        ),
        (
            relationships.GraphRecallOperation.RELATIONSHIP_EVIDENCE,
            relationships.GraphRecallSource.CANONICAL_FALLBACK,
            1,
        ),
        (
            relationships.GraphRecallOperation.SHORTEST_PATH,
            relationships.GraphRecallSource.NONE,
            0,
        ),
    ),
)
def test_graph_outage_has_bounded_fallback_without_raising(
    operation,
    expected_source,
    expected_count,
) -> None:
    canonical = _hit(SUBJECT_ID, COUNTERPART_ID)
    graph, gateway = _gateway_with(canonical)
    gateway.evidence_by_id[canonical.last_event_id or ""] = _evidence(
        canonical.last_event_id or ""
    )
    result = relationships.GraphRecallService(gateway).execute(
        relationships.GraphRecallQuery(
            operation=operation,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
            limit=(
                5
                if operation
                is relationships.GraphRecallOperation.RELATIONSHIP_EVIDENCE
                else 10
            ),
        ),
        graph_projection_enabled=False,
    )
    assert result.status is relationships.GraphRecallStatus.DEGRADED
    assert result.source is expected_source
    assert result.reason_code == "graph_disabled"
    assert len(result.relationships) == expected_count
    assert graph.calls == []


def test_graph_outage_shared_and_rank_use_only_bounded_canonical_facts() -> None:
    subject_neighbor = _hit(SUBJECT_ID, NEIGHBOR_ID)
    counterpart_neighbor = _hit(COUNTERPART_ID, NEIGHBOR_ID)
    subject_counterpart = _hit(
        SUBJECT_ID,
        COUNTERPART_ID,
        affinity=11,
    )
    graph, gateway = _gateway_with(
        subject_neighbor,
        counterpart_neighbor,
        subject_counterpart,
    )
    service = relationships.GraphRecallService(gateway)
    shared = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.SHARED_NEIGHBORS,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
        ),
        graph_projection_enabled=False,
    )
    ranked = service.execute(
        relationships.GraphRecallQuery(
            operation=(
                relationships.GraphRecallOperation.RANK_RELATED_CHARACTERS
            ),
            scope=_scope(),
        ),
        graph_projection_enabled=False,
    )
    assert shared.world_character_ids == (NEIGHBOR_ID,)
    assert shared.source is relationships.GraphRecallSource.CANONICAL_FALLBACK
    assert COUNTERPART_ID in ranked.world_character_ids
    assert ranked.source is relationships.GraphRecallSource.CANONICAL_FALLBACK
    assert graph.calls == []


def test_scope_validation_rejects_blocked_counterpart_before_graph_query() -> None:
    graph, gateway = _gateway_with(_hit(SUBJECT_ID, COUNTERPART_ID))
    gateway.blocked_nodes.add(COUNTERPART_ID)
    with pytest.raises(
        relationships.RelationshipGraphRequestError,
        match="counterpart_unavailable",
    ):
        relationships.GraphRecallService(gateway).execute(
            relationships.GraphRecallQuery(
                operation=(
                    relationships.GraphRecallOperation.DIRECT_RELATIONSHIP
                ),
                scope=_scope(),
                counterpart_world_character_id=COUNTERPART_ID,
            ),
            repository=graph,
        )
    assert graph.calls == []


def test_provider_results_cannot_escape_pair_direction_or_path_shape() -> None:
    direct = _hit(SUBJECT_ID, COUNTERPART_ID)
    unrelated = _hit(NEIGHBOR_ID, "wc-other")
    graph, gateway = _gateway_with(direct, unrelated)
    service = relationships.GraphRecallService(gateway)
    graph.direct = [unrelated]
    escaped = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.DIRECT_RELATIONSHIP,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
        ),
        repository=graph,
    )
    assert escaped.relationships == ()
    assert escaped.excluded_count == 1

    graph.direct = [direct]
    graph.evidence = [
        GraphEvidenceHit(
            event_id=direct.last_event_id or "",
            event_type="comment_created",
            occurred_at=NOW,
            relationship_state_id=unrelated.relationship_state_id,
            relationship_version=1,
        )
    ]
    gateway.evidence_by_id[direct.last_event_id or ""] = _evidence(
        direct.last_event_id or ""
    )
    wrong_state = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.RELATIONSHIP_EVIDENCE,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
            limit=5,
        ),
        repository=graph,
    )
    assert wrong_state.evidence == ()
    assert wrong_state.excluded_count == 1

    graph.path = GraphPathHit(
        world_character_ids=(SUBJECT_ID, NEIGHBOR_ID, COUNTERPART_ID),
        oriented_edges=(direct, unrelated),
        hop_count=2,
    )
    malformed_path = service.execute(
        relationships.GraphRecallQuery(
            operation=relationships.GraphRecallOperation.SHORTEST_PATH,
            scope=_scope(),
            counterpart_world_character_id=COUNTERPART_ID,
            direction=relationships.GraphRecallDirection.EITHER,
            max_hops=2,
        ),
        repository=graph,
    )
    assert malformed_path.path is None
    assert malformed_path.excluded_count >= 1


def test_runtime_facade_preserves_direction_evidence_and_owner_scope() -> None:
    engine = sqlite_engine()
    config = Settings(GRAPH_PROJECTION_ENABLED=False)
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="p8-l-i-runtime")
        scope = relationships.GraphRecallScope(
            owner_id=fixture.owner.id,
            world_id=fixture.world.id,
            subject_world_character_id=fixture.actor_world_character.id,
        )
        direct = execute_graph_recall(
            db,
            query=relationships.GraphRecallQuery(
                operation=(
                    relationships.GraphRecallOperation.DIRECT_RELATIONSHIP
                ),
                scope=scope,
                counterpart_world_character_id=(
                    fixture.target_world_character.id
                ),
            ),
            config=config,
        )
        evidence = execute_graph_recall(
            db,
            query=relationships.GraphRecallQuery(
                operation=(
                    relationships.GraphRecallOperation.RELATIONSHIP_EVIDENCE
                ),
                scope=scope,
                counterpart_world_character_id=(
                    fixture.target_world_character.id
                ),
                limit=5,
            ),
            config=config,
        )
        fixture.root_post.report_hidden_at = NOW
        db.flush()
        hidden_evidence = execute_graph_recall(
            db,
            query=relationships.GraphRecallQuery(
                operation=(
                    relationships.GraphRecallOperation.RELATIONSHIP_EVIDENCE
                ),
                scope=scope,
                counterpart_world_character_id=(
                    fixture.target_world_character.id
                ),
                limit=5,
            ),
            config=config,
        )
        with pytest.raises(relationships.RelationshipGraphForbiddenError):
            execute_graph_recall(
                db,
                query=relationships.GraphRecallQuery(
                    operation=(
                        relationships.GraphRecallOperation.DIRECT_RELATIONSHIP
                    ),
                    scope=replace(scope, owner_id=fixture.other_owner.id),
                    counterpart_world_character_id=(
                        fixture.target_world_character.id
                    ),
                ),
                config=config,
            )

    assert direct.source is relationships.GraphRecallSource.CANONICAL_FALLBACK
    assert [value.actor_world_character_id for value in direct.relationships] == [
        fixture.actor_world_character.id
    ]
    assert [value.event_id for value in evidence.evidence] == [fixture.event.id]
    assert hidden_evidence.evidence == ()
