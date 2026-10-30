import asyncio
import threading
from types import SimpleNamespace
import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker
from postgresql.test_activity_transactions import store
from app.core.committed_queue_wakeup import CommittedQueueWakeup
from app.domains.routines.models import AgentSlot


def test_queue_hint_waits_for_outer_commit_handles_bulk_cross_thread_and_rollback(store):
    engine, _, _ = store
    sessions = sessionmaker(engine)
    async def scenario():
        wake = CommittedQueueWakeup(sessions, {AgentSlot.__tablename__})
        try:
            with sessions() as db:
                db.add(AgentSlot(agent_id='wake-test', status='empty'))
                db.flush()
                await asyncio.sleep(.01)
                assert not wake.wake.is_set()
                db.rollback()
                db.commit()
                await asyncio.sleep(.01)
                assert not wake.wake.is_set()
                db.add(AgentSlot(agent_id='wake-test', status='empty'))
                db.commit()
            await asyncio.wait_for(wake.wait(5), .5)
            assert wake.wake.is_set()
            wake.begin_poll()
            def bulk():
                with sessions() as db:
                    db.execute(update(AgentSlot).where(AgentSlot.agent_id=='wake-test').values(last_error='test'))
                    db.commit()
            await asyncio.to_thread(bulk)
            # This commit happened during the poll, before the wait starts.
            await asyncio.wait_for(wake.wait(5), .5)
            assert wake.wake.is_set()
            wake.begin_poll()
            with sessions() as db:
                db.get(AgentSlot,'wake-test').last_error='outer'
                db.flush()
                with db.begin_nested():
                    db.get(AgentSlot,'wake-test').last_error='nested'
                await asyncio.sleep(.01)
                assert not wake.wake.is_set()
                db.commit()
            await asyncio.wait_for(wake.wait(5), .5)
            assert wake.wake.is_set()
            wake.begin_poll()
            started=asyncio.get_running_loop().time()
            await wake.wait(.03)
            assert asyncio.get_running_loop().time()-started>=.02
            assert not wake.wake.is_set()
        finally:
            wake.close()
        wake.begin_poll()
        with sessions() as db:
            db.get(AgentSlot,'wake-test').last_error='closed'
            db.commit()
        await asyncio.sleep(.01)
        assert not wake.wake.is_set()
        assert engine.pool.checkedout()==0
    asyncio.run(scenario())


def test_postgres_image_admission_commit_wakes_worker_and_attaches_once(store, tmp_path, monkeypatch):
    from sqlalchemy import select, func
    from social.test_l4_social_write_uow import _seed
    from image_integration import test_generation_lifecycle as fixture
    from app.domains.social.models.posts import PostImageGenerationJob, PostMedia
    from app.domains.social.models.image_intents import ImageGenerationAttempt
    engine, _, _=store
    sessions=sessionmaker(engine,expire_on_commit=False)
    _seed(sessions)
    monkeypatch.setattr(fixture,'_session_factory',lambda _:sessions)
    _,media,provider=fixture.configured(tmp_path)
    async def scenario():
        await media.worker.start()
        try:
            # The first empty poll can finish before admission; only a commit
            # notification or the bounded fallback can discover the new job.
            await asyncio.sleep(.05)
            identity=await asyncio.to_thread(fixture.admit,sessions,media)
            assert identity is not None
            assert await asyncio.to_thread(fixture.admit,sessions,media)==identity
            def state():
                with sessions() as db:
                    return db.get(PostImageGenerationJob,identity).status
            for _ in range(200):
                if await asyncio.to_thread(state)=='succeeded':break
                await asyncio.sleep(.05)
            else:raise AssertionError('committed image job did not complete')
            assert provider.calls==1
            with sessions() as db:
                assert db.scalar(select(func.count()).select_from(ImageGenerationAttempt))==1
                assert db.scalar(select(PostMedia)).source_kind=='generated'
        finally:
            await media.worker.stop()
            await media._canonical_work.drain()
            media._canonical_work.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('kind',['deletion','image'])
def test_idle_workers_wake_during_poll_and_stop_promptly_without_busy_loop(store, tmp_path, kind):
    engine, _, _=store
    sessions=sessionmaker(engine)
    if kind=='deletion':
        from app.runtime.world_deletion.worker import WorldDeletionWorker
        worker=WorldDeletionWorker(sessions,SimpleNamespace())
    else:
        from app.domains.social.service.image_intent_generation import GenerationWorker
        worker=GenerationWorker(sessions,None,None,spool=tmp_path)
    calls=[]
    entered,release=threading.Event(),threading.Event()
    def poll():
        calls.append(1)
        if len(calls)==1:
            entered.set()
            assert release.wait(2)
        return False
    if kind=='deletion':
        worker.tick=poll
    else:
        async def image_poll():
            return await asyncio.to_thread(poll)
        worker.tick=image_poll
    async def scenario():
        await worker.start()
        try:
            assert await asyncio.to_thread(entered.wait,2)
            worker._queue_wakeup.notify()
            release.set()
            for _ in range(100):
                if len(calls)>=2: break
                await asyncio.sleep(.01)
            assert len(calls)==2
            await asyncio.sleep(.15)
            assert len(calls)==2
        finally:
            release.set()
            await asyncio.wait_for(worker.stop(), .5)
        # A new lifetime reattaches listeners and scans persisted work immediately.
        await worker.start()
        for _ in range(100):
            if len(calls)>=3: break
            await asyncio.sleep(.01)
        assert len(calls)==3
        await asyncio.wait_for(worker.stop(), .5)
        assert engine.pool.checkedout()==0
    asyncio.run(scenario())
