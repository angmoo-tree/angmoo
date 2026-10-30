"""SNS DB stages yield the loop and finish before their Session can be reused."""
import asyncio
from datetime import UTC, datetime
from threading import Event, get_ident
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.social_lane import SocialLane
from postgresql.test_activity_transactions import store


def test_feed_publication_drains_repeated_cancel_before_session_reuse(store, monkeypatch):
    engine, _, _ = store
    started, release, finished = Event(), Event(), Event()
    calls = []
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE feed_stage_effect (id integer PRIMARY KEY)'))
    async def scenario():
        owner_thread = get_ident()
        with Session(engine) as db:
            lane = FeedLane.__new__(FeedLane)
            lane.ctx = SimpleNamespace(db=db)
            def execute(adapter, state):
                assert get_ident() != owner_thread
                calls.append(1); started.set()
                assert release.wait(3)
                adapter.ctx.db.execute(text('INSERT INTO feed_stage_effect VALUES (1)'))
                adapter.ctx.db.commit(); finished.set()
                return [{'status': 'succeeded'}]
            monkeypatch.setattr('app.runtime.autonomous_activity.feed_effects.execute', execute)
            task = asyncio.create_task(lane.execute({}))
            for _ in range(100):
                if started.is_set() or task.done(): break
                await asyncio.sleep(.005)
            if task.done(): await task
            assert started.is_set()
            task.cancel(); await asyncio.sleep(.01)
            task.cancel(); await asyncio.sleep(.01)
            assert not task.done() and not finished.is_set()
            release.set()
            with pytest.raises(asyncio.CancelledError): await task
            assert finished.is_set()
            assert db.scalar(text('SELECT count(*) FROM feed_stage_effect')) == 1
    try: asyncio.run(scenario())
    finally: release.set()
    assert calls == [1] and engine.pool.checkedout() == 0


def test_social_settlement_and_feed_finalization_keep_db_work_off_loop(store, monkeypatch):
    engine, _, _ = store
    async def scenario():
        owner_thread = get_ident()
        with Session(engine) as db:
            lane = FeedLane.__new__(FeedLane)
            lane.ctx = SimpleNamespace(db=db, run_id='run')
            lane.actor = SimpleNamespace(id='actor', world_id='world')
            lane.lane = 'feed'; lane.claim_validator = None
            lane.tracker = SimpleNamespace(_notify=lambda *args: None)
            def source_stage(session, **kwargs):
                assert get_ident() != owner_thread
                session.execute(text('SELECT pg_sleep(0.01)')); session.rollback()
                return []
            monkeypatch.setattr('app.runtime.autonomous_activity.social_lane.stage_sources', source_stage)
            monkeypatch.setattr('app.runtime.autonomous_activity.social_lane.apply_pending_metrics', lambda *args, **kwargs: None)
            state = {'identity': {'activity_id': 'run'}, 'candidates': [], 'selections': [],
                'decision': {'decisions': [], 'judged_at': datetime.now(UTC).isoformat(), 'state_status': 'invalid'},
                'decision_context': {'source_manifest': []}, 'lane_data': {}}
            assert (await lane.settle(state))['settlement']['state'] == 'invalid'
            monkeypatch.setattr(lane, 'observe_delivered', lambda: source_stage(db))
            assert (await lane.finalize(state))['result']['status'] == 'no_action'
    asyncio.run(scenario())
    assert engine.pool.checkedout() == 0
