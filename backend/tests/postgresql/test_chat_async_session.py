"""Real PG stage ownership, cancellation draining and post-commit boundaries."""
import asyncio
from threading import Event, get_ident

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.async_session import session_call
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork
from postgresql.test_activity_transactions import store


def test_chat_stage_yields_loop_and_cancellation_drains_before_session_reuse(store):
    engine, _, _ = store
    started, release, finished = Event(), Event(), Event()
    with engine.begin() as c:
        c.execute(text('CREATE TABLE chat_async_effect(value integer)'))
        c.execute(text('INSERT INTO chat_async_effect VALUES (0)'))
    async def scenario():
        loop_thread = get_ident()
        with Session(engine) as db:
            def work():
                assert get_ident() != loop_thread
                started.set()
                assert release.wait(3)
                db.execute(text('UPDATE chat_async_effect SET value=value+1'))
                db.commit()
                finished.set()
            task = asyncio.create_task(session_call(db, work))
            for _ in range(100):
                if started.is_set(): break
                await asyncio.sleep(.005)
            assert started.is_set()
            with pytest.raises(RuntimeError, match='database_session_concurrent_stage'):
                await session_call(db, lambda: None)
            task.cancel()
            await asyncio.sleep(.02)
            task.cancel()
            await asyncio.sleep(.02)
            assert not task.done() and not finished.is_set()
            release.set()
            with pytest.raises(asyncio.CancelledError): await task
            assert finished.is_set()
            assert await session_call(db, lambda: db.scalar(text('SELECT value FROM chat_async_effect'))) == 1
    asyncio.run(scenario())
    assert engine.pool.checkedout() == 0


def test_progress_checkpoints_do_not_scan_unrelated_pending_relationships(store, monkeypatch):
    engine, _, _ = store
    calls = []
    monkeypatch.setattr('app.runtime.relationships.experience_metrics.apply_pending_metrics',
        lambda db, **kw: calls.append(kw))
    async def scenario():
        with Session(engine) as db:
            uow = SqlAlchemyResponseWorkflowUnitOfWork(db, relationship_world_id='world')
            await uow.async_database_unit(lambda: 1)
            await uow.async_checkpoint()
            assert calls == []
            await uow.call(lambda: uow.response_committed('request-specific'))
    asyncio.run(scenario())
    assert calls == [dict(world_id='world', source_kind='chat_message', decision_key='request-specific')]


def test_async_transaction_retries_the_database_not_the_received_provider_result(store):
    engine, _, _ = store
    attempts = []
    with engine.begin() as c:
        c.execute(text('CREATE TABLE chat_async_retry(value integer)'))
        c.execute(text('INSERT INTO chat_async_retry VALUES (0)'))
    async def scenario():
        with Session(engine) as db:
            uow = SqlAlchemyResponseWorkflowUnitOfWork(db)
            def save():
                attempts.append(1)
                db.execute(text('UPDATE chat_async_retry SET value=value+1'))
                if len(attempts) == 1:
                    db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'retry' USING ERRCODE='40001'; END $$"))
                return 'already received'
            assert await uow.async_database_unit(save) == 'already received'
        with engine.connect() as c:
            assert c.scalar(text('SELECT value FROM chat_async_retry')) == 1
    asyncio.run(scenario())
    assert len(attempts) == 2
