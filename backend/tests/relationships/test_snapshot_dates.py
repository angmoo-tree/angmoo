"""Source representation changes must not invalidate an unchanged relationship."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.domains.relationships.policies.graph_recall import _relationship_record
from app.domains.relationships.service.graph_recall import GraphRecallService
from app.domains.relationships.service.social_context import SocialContextChangedError, SocialContextService
from test_p8_l_i_graph_recall import (
    FakeGraphRecallGateway, FakeGraphRepository, _hit, _scope,
    SUBJECT_ID, COUNTERPART_ID,
)

NOW = datetime(2026, 9, 22, 4, 11, 59, 123456, tzinfo=UTC)


def date_hit(value, *, updated=True):
    return replace(_hit(SUBJECT_ID, COUNTERPART_ID, version=2),
                   reviewed_at=value, view_updated_at=value if updated else None)


@pytest.mark.parametrize('updated', [False, True])
@pytest.mark.parametrize('value', [NOW, NOW.replace(tzinfo=None), NOW.isoformat(),
    '2026-09-22T04:11:59.123456Z', '2026-09-22 13:11:59.123456+09:00'])
def test_same_instant_has_one_recall_representation(value, updated):
    actual = _relationship_record(date_hit(value, updated=updated))
    assert actual.reviewed_at == NOW
    assert actual.view_updated_at == (NOW if updated else None)


@pytest.mark.parametrize('value', [None, 'invalid-date'])
def test_nullable_dates_keep_existing_parser_contract(value):
    actual = _relationship_record(date_hit(value))
    assert actual.reviewed_at is None and actual.view_updated_at is None


@pytest.mark.parametrize('reverse', [False, True])
def test_canonical_and_graph_switch_during_snapshot_and_revalidation(reverse):
    repo = FakeGraphRepository()
    gateway = FakeGraphRecallGateway(repo)
    canonical = date_hit(NOW.replace(tzinfo=None))
    projected = date_hit(NOW.isoformat())
    gateway.canonical_by_state[canonical.relationship_state_id] = canonical
    recall = GraphRecallService(gateway)
    count = 0

    def read(query):
        nonlocal count
        count += 1
        # A stale graph edge uses canonical SQLite data; a caught-up edge
        # returns the graph representation of the very same relationship.
        stale = bool(count % 2) != reverse
        hit = replace(projected, relationship_version=1) if stale else projected
        repo.direct = repo.ranked = [hit]
        return recall.execute(query)

    service = SocialContextService(read)
    snapshot = service.prepare(_scope(), labels={COUNTERPART_ID: 'Peer'})
    assert len(snapshot.items) == 1
    assert 'changed_during_preparation' not in snapshot.truncation_reasons
    service.assert_current(snapshot)
    service.assert_current(snapshot)
    assert gateway.stale_edges > 0


@pytest.mark.parametrize('changes', [
    {'trust': 9}, {'relationship_label': 'Changed'}, {'perception': 'Changed'},
    {'view_version': 2}, {'relationship_version': 3},
    {'reviewed_at': NOW + timedelta(microseconds=1)},
    {'view_updated_at': None},
])
def test_real_changes_remain_rejected(changes):
    from relationships.test_social_context import result
    current = [_relationship_record(date_hit(NOW))]
    service = SocialContextService(lambda q: result(q, current))
    snapshot = service.prepare(_scope(), labels={COUNTERPART_ID: 'Peer'})
    current[:] = [_relationship_record(replace(date_hit(NOW.isoformat()), **changes))]
    with pytest.raises(SocialContextChangedError):
        service.assert_current(snapshot)


@pytest.mark.parametrize('updated', [False, True])
def test_temporary_ladybug_review_dates_roundtrip(tmp_path, updated):
    from test_l3_er3_ladybug_projection import _relationship
    from app.integrations.ladybug_projection import LadybugRelationshipProjection
    from app.integrations.relationship_graph_read import RelationshipGraphRepository
    command = replace(_relationship(version=5), event=None, world_id='world-arcana', reviewed_at=NOW,
                      view_updated_at=NOW if updated else None)
    with LadybugRelationshipProjection(database_root=tmp_path / 'graph') as projection:
        projection.apply(command)
        hit = RelationshipGraphRepository(projection).get_direct_relationship(
            world_id=command.world_id, source_world_character_id=command.actor_world_character_id,
            target_world_character_id=command.target_world_character_id)[0]
        graph_value = _relationship_record(hit)
        sqlite_value = _relationship_record(replace(hit, reviewed_at=NOW.replace(tzinfo=None),
            view_updated_at=NOW.replace(tzinfo=None) if updated else None))
        assert graph_value == sqlite_value
        assert graph_value.reviewed_at == NOW


@pytest.mark.parametrize('change_at', [None, 'planner', 'writer'])
def test_routine_publication_uses_real_snapshot_fences(monkeypatch, change_at):
    import asyncio
    import json
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from model_fixture_support import models
    from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc
    from relationships.test_social_context import result
    from app.domains.relationships.contracts.social_consumption import SocialContextUse
    from app.domains.routine_posts.service import generation
    from app.runtime.routine_posts.sqlalchemy_runtime import _run_routine_post_runtime

    engine = _engine()
    current = [date_hit(NOW.replace(tzinfo=None))]
    service = SocialContextService(lambda q: result(q, [_relationship_record(current[0])]))
    snapshot = service.prepare(_scope(), labels={COUNTERPART_ID: 'Peer'})
    use = SocialContextUse(snapshot, lambda: service.assert_current(snapshot))
    calls = []

    async def transport(**kwargs):
        node = kwargs['context'].node
        calls.append(node)
        payload = json.loads(kwargs['user_prompt'])
        if node == 'RoutineBeatPlanner':
            current[0] = date_hit(NOW.isoformat())
            if change_at == 'planner':
                current[0] = replace(current[0], trust=99)
            return kwargs['validator']({**payload['beat_identity'],
                'scene_kind': 'start', 'scene_brief': 'Begin the activity.'})
        if change_at == 'writer':
            current[0] = replace(current[0], trust=99)
        return kwargs['validator']({'title': 'A morning scene', 'body': 'The activity begins.',
            'topic_signature': 'morning scene', 'novelty_basis': 'Current scene.'})

    monkeypatch.setattr(generation, '_api_key', lambda credential: 'synthetic-key')
    monkeypatch.setattr(generation, 'generate_json', transport)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        ctx = replace(_resident_context(db, fixture, run_id='date-fence',
            now=_utc(datetime(2026, 8, 10, 10, 5))), social_context=use)
        output = asyncio.run(_run_routine_post_runtime(ctx,
            provider=generation.DirectRoutinePostProvider(thought_enabled=False)))
        posts = list(db.scalars(select(models.Post)))
        if change_at is None:
            assert output['status'] == 'completed'
            assert output['publish_result']['public_action_count'] == 1
            assert len(posts) == 1
            executions = list(db.scalars(select(models.AgentPublicActionExecution)))
            assert len(executions) == 1 and executions[0].status == 'succeeded'
            # Re-entering the same tick cannot publish or call the provider twice.
            asyncio.run(_run_routine_post_runtime(ctx,
                provider=generation.DirectRoutinePostProvider(thought_enabled=False)))
            assert len(list(db.scalars(select(models.Post)))) == 1
        else:
            assert output['status'] == 'failed'
            assert posts == []
        assert calls == (['RoutineBeatPlanner'] if change_at == 'planner'
                         else ['RoutineBeatPlanner', 'PostWriter'])
    engine.dispose()
