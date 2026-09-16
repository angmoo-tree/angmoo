from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.domains.relationships.contracts.graph_recall import (
    GraphRecallOperation, GraphRecallRelationship, GraphRecallResult,
    GraphRecallScope, GraphRecallSource, GraphRecallStatus,
)
from app.domains.relationships.service.social_context import (
    SocialContextChangedError, SocialContextLimits, SocialContextService,
)

SCOPE = GraphRecallScope("owner", "world", "self")
NOW = datetime(2026, 9, 14, tzinfo=UTC)


def relationship(target="friend", **changes):
    return replace(GraphRecallRelationship(
        "rel-" + target, "world", "self", target, 20, 10, 12, 3, 4, 1,
    ), **changes)


def result(query, rows=(), **changes):
    return replace(GraphRecallResult(
        query.operation, GraphRecallStatus.READY, GraphRecallSource.GRAPH,
        relationships=tuple(rows), candidate_count=len(rows),
    ), **changes)


def test_scope_direction_dedup_and_deterministic_content():
    calls = []
    rows = (relationship(), relationship("reverse", actor_world_character_id="other"),
            relationship("hidden"), relationship("cross", world_id="elsewhere"))
    def read(query):
        calls.append(query)
        return result(query, rows)
    service = SocialContextService(read)
    first = service.prepare(SCOPE, labels={"friend": "친구", "reverse": "상대", "cross": "다른 월드"}, now=NOW)
    second = service.prepare(SCOPE, labels={"friend": "친구", "reverse": "상대", "cross": "다른 월드"}, now=NOW)
    assert len(first.items) == 1
    assert first.items[0].selection_reasons == ("recent", "tense", "positive")
    assert first.content_hash == second.content_hash
    assert first.snapshot_id != second.snapshot_id
    assert first.coverage == "partial" and first.manifest()["total_count"] is None
    assert all(q.scope == SCOPE and q.direction.value == "outgoing" for q in calls)


def test_changed_relation_between_queries_is_excluded():
    count = 0
    def read(query):
        nonlocal count
        count += 1
        return result(query, [relationship(relationship_version=count)])
    snapshot = SocialContextService(read).prepare(SCOPE, labels={"friend": "친구"})
    assert not snapshot.items
    assert "changed_during_preparation" in snapshot.truncation_reasons


def test_empty_and_unavailable_are_distinct():
    ready = SocialContextService(lambda q: result(q)).prepare(SCOPE, labels={})
    unavailable = SocialContextService(lambda q: result(
        q, status=GraphRecallStatus.DEGRADED, source=GraphRecallSource.NONE,
    )).prepare(SCOPE, labels={})
    assert ready.status == "empty"
    assert unavailable.status == "unavailable"


def test_budget_bounds_and_current_target_priority():
    rows = [relationship(str(i)) for i in range(8)]
    def read(query):
        return result(query, [relationship("current")] if query.operation is GraphRecallOperation.DIRECT_RELATIONSHIP else rows)
    snapshot = SocialContextService(read, limits=SocialContextLimits(max_items=2)).prepare(
        SCOPE, labels={**{str(i): str(i) for i in range(8)}, "current": "현재 상대"}, counterpart_id="current",
    )
    assert len(snapshot.items) == 2
    assert snapshot.items[0].relationship.target_world_character_id == "current"
    assert len(snapshot.context_text) <= 3000
    assert snapshot.status == "partial"


def test_revalidation_rejects_deleted_or_changed_relation():
    rows = [relationship()]
    service = SocialContextService(lambda q: result(q, rows))
    snapshot = service.prepare(SCOPE, labels={"friend": "친구"})
    service.assert_current(snapshot)
    rows.clear()
    with pytest.raises(SocialContextChangedError, match="social_context_changed"):
        service.assert_current(snapshot)

@pytest.mark.parametrize('enabled', [True, False])
def test_sns_runtime_flag_prepares_context_and_revalidates_actor(monkeypatch, enabled):
    from dataclasses import dataclass
    from types import SimpleNamespace
    from app.config import Settings
    from app.runtime import social_snapshot as runtime
    from app.domains.relationships.contracts.graph_recall import GraphRecallResult, GraphRecallSource, GraphRecallStatus
    monkeypatch.setattr(runtime, 'settings', Settings(_env_file=None, SNS_SOCIAL_CONTEXT_ENABLED=enabled))
    monkeypatch.setattr(runtime, 'SqlAlchemyRelationshipGraphReadGateway', lambda *a, **kw: None)
    monkeypatch.setattr(runtime, 'GraphRecallService', lambda gateway: SimpleNamespace(execute=lambda q:
        GraphRecallResult(q.operation, GraphRecallStatus.READY, GraphRecallSource.GRAPH)))
    @dataclass
    class Context:
        db: object
        character: object
        user_id: str
        social_context: object = None
    ctx = Context(SimpleNamespace(execute=lambda query: SimpleNamespace(all=lambda: [])), SimpleNamespace(id='character'), 'owner')
    actor = SimpleNamespace(id='actor', world_id='world')
    calls = []
    def active_actor(*args, **kwargs):
        calls.append(True)
        return actor
    prepared = runtime.prepare_activity_social_context(ctx, active_actor=active_actor)
    if not enabled:
        assert prepared is ctx and not calls
        return
    assert prepared.social_context.snapshot.scope.subject_world_character_id == 'actor'
    actor.id = 'different'
    with pytest.raises(SocialContextChangedError, match='social_context_scope_changed'):
        prepared.social_context.validate()
