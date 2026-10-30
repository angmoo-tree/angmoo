import asyncio
from dataclasses import dataclass
import sys
from threading import Event, get_ident
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker, object_session
from postgresql.test_activity_transactions import store
from social.test_l4_social_write_uow import _seed
from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter
from app.runtime.autonomous_activity.db_stage import run_db_stage


@dataclass(frozen=True)
class Context:
    db: Session
    character: Character


def test_worker_owns_session_while_loop_and_other_queries_continue(store):
    engine, _, _ = store
    _seed(sessionmaker(engine, expire_on_commit=False))
    seen = []
    began, release = Event(), Event()
    class Lane:
        def stage(self, state):
            self.claim_validator()
            seen.append((get_ident(), object_session(self.actor) is self.ctx.db,
                         object_session(self.ctx.character) is self.ctx.db))
            assert self.ctx.db.scalar(text('SELECT 1')) == 1
            began.set()
            assert release.wait(5)
            return {'candidates': [state]}
    async def scenario():
        with Session(engine) as db:
            lane = Lane()
            lane.ctx = Context(db, db.get(Character, 'social-uow-autonomous-character'))
            lane.actor = db.get(WorldCharacter, 'social-uow-autonomous-actor')
            def parent_claim():
                pytest.fail('parent Session claim used by worker')
            def bind(ctx,actor):
                def validate():
                    assert object_session(actor) is ctx.db
                    assert ctx.db is not db
                return validate
            parent_claim.bind_context=bind
            lane.claim_validator=parent_claim
            task = asyncio.create_task(run_db_stage(lane, 'stage', 'plain'))
            for _ in range(100):
                if began.is_set():break
                await asyncio.sleep(.01)
            assert began.is_set() and not task.done()
            assert not db.in_transaction()
            task.cancel()
            await asyncio.sleep(.03)
            assert not task.done(), 'cancellation must drain the worker-owned transaction'
            task.cancel()
            await asyncio.sleep(.03)
            assert not task.done(), 'repeated cancellation must not abandon the worker'
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert engine.pool.checkedout() == 0
    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else None)
    assert seen == [(seen[0][0], True, True)] and seen[0][0] != get_ident()


def test_combined_feed_override_dispatches_its_atomic_preparation_off_loop(store):
    from app.runtime.autonomous_activity.combined_lanes import CombinedFeedLane
    engine, _, _ = store
    _seed(sessionmaker(engine, expire_on_commit=False))
    seen = []
    class Lane(CombinedFeedLane):
        def reconcile_deliveries(self):
            seen.append(get_ident())
        def prepare_candidates(self, state):
            assert object_session(self.actor) is self.ctx.db
            assert self.ctx.db.scalar(text('SELECT 1')) == 1
            return {'candidates': [state]}
    async def scenario():
        with Session(engine) as db:
            lane = Lane.__new__(Lane)
            lane.ctx = Context(db, db.get(Character, 'social-uow-autonomous-character'))
            lane.actor = db.get(WorldCharacter, 'social-uow-autonomous-actor')
            assert await lane.load('plain') == {'candidates': ['plain']}
            assert not db.in_transaction()
        assert engine.pool.checkedout() == 0
    asyncio.run(scenario(), loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else None)
    assert len(seen) == 1 and seen[0] != get_ident()
