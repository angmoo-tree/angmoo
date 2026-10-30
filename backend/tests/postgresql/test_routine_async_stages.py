"""Real PG transactions must not block the loop or outlive Routine ownership."""
import asyncio
from datetime import UTC, datetime
from threading import Event, get_ident
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.runtime.autonomous_activity import routine
from postgresql.test_activity_transactions import store


def lane(db, monkeypatch):
    adapter = routine.RoutineLane.__new__(routine.RoutineLane)
    adapter.ctx = SimpleNamespace(db=db, run_id='run')
    adapter.actor = SimpleNamespace(id='actor', world_id='world')
    adapter.tracker = SimpleNamespace(_notify=lambda *args, **kwargs: None)
    adapter.prepared = SimpleNamespace(context=SimpleNamespace(state_before={}), beat=None)
    adapter.claim_validator = None
    adapter.validated_plan = lambda state: SimpleNamespace()
    adapter.effect_relationship_validator = lambda state: None
    monkeypatch.setattr(routine.schemas, 'RoutinePostDraft',
        SimpleNamespace(model_validate=lambda data: SimpleNamespace()))
    monkeypatch.setattr(routine, '_state_after', lambda *args: {})
    monkeypatch.setattr(routine, 'validate_routine_generation', lambda value, **kwargs: value)
    monkeypatch.setattr('app.runtime.autonomous_activity.situation_memory.participant', lambda *args: None)
    return adapter


def test_routine_publish_yields_loop_and_drains_cancel_before_session_reuse(store, monkeypatch):
    engine, _, _ = store
    started, release, finished = Event(), Event(), Event()
    calls = []
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE routine_stage_effect (id integer PRIMARY KEY)'))

    async def scenario():
        owner_thread = get_ident()
        with Session(engine) as db:
            adapter = lane(db, monkeypatch)
            def publish(ctx, **kwargs):
                calls.append(get_ident())
                assert get_ident() != owner_thread
                started.set()
                assert release.wait(3)
                ctx.db.execute(text('INSERT INTO routine_stage_effect VALUES (1)'))
                ctx.db.commit()
                finished.set()
                return {'status': 'completed', 'routine_outcome': 'POST_SUCCEEDED'}
            monkeypatch.setattr(routine, 'publish_routine_activity', publish)
            state = {'drafts': [{'_thought': {}, '_auxiliary_normalization': {}}],
                'shared_context': {'current_state': {'known': False}}, 'decision': {}}
            task = asyncio.create_task(adapter.execute(state))
            for _ in range(100):
                if started.is_set() or task.done(): break
                await asyncio.sleep(.005)
            if task.done(): await task
            assert started.is_set()
            task.cancel()
            await asyncio.sleep(.01)
            task.cancel()
            await asyncio.sleep(.01)
            assert not task.done() and not finished.is_set()
            release.set()
            with pytest.raises(asyncio.CancelledError): await task
            assert finished.is_set()
            assert db.scalar(text('SELECT count(*) FROM routine_stage_effect')) == 1
    try:
        asyncio.run(scenario())
    finally:
        release.set()
    assert len(calls) == 1
    assert engine.pool.checkedout() == 0


def test_routine_settlement_keeps_database_work_off_loop(store, monkeypatch):
    engine, _, _ = store
    async def scenario():
        owner_thread = get_ident()
        with Session(engine) as db:
            adapter = lane(db, monkeypatch)
            def stage(session, **kwargs):
                assert get_ident() != owner_thread
                session.execute(text('SELECT pg_sleep(0.05)'))
                session.rollback()
            monkeypatch.setattr('app.runtime.relationships.social_metrics.stage_sources', stage)
            monkeypatch.setattr('app.runtime.relationships.experience_metrics.apply_pending_metrics', lambda *args, **kwargs: None)
            result = await adapter.settle({'identity': {'activity_id': 'run'},
                'decision': {'judged_at': datetime.now(UTC).isoformat()},
                'decision_context': {'source_manifest': []}})
            assert result == {'settlement': {'state': 'not_committed'}}
    asyncio.run(scenario())
    assert engine.pool.checkedout() == 0
