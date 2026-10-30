"""HTTP-style level cancellation and repeated task cancellation settle in PG."""
import asyncio
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace

import anyio
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.chat import models
from app.domains.chat.contracts import CreateResponseRequest, RetrievalRoute, build_request_scope_hash
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.runtime.chat.generation_workflows import SqlAlchemyResponseWorkflowUnitOfWork
from chat import test_p8_l_p_evidence_response_streaming as fixture
from postgresql.test_activity_transactions import store
from postgresql.test_chat_storage import prepare


@pytest.mark.parametrize("cancel_style", ["anyio_scope", "repeated_task"])
def test_disconnect_finishes_cancel_record_before_releasing_session(store, cancel_style):
    engine, _, _ = store
    prepare(engine)
    entered, cleanup_started, release = Event(), Event(), Event()

    async def wait_for(signal):
        for _ in range(300):
            if signal.is_set():
                return
            await asyncio.sleep(.01)
        raise AssertionError("expected controlled stage was not reached")

    async def run():
        with Session(engine) as db:
            message = models.MessageMessage(thread_id="chat-one", role="user", content="synthetic cancellation", status="ok")
            db.add(message); db.flush()
            scope = dict(owner_id="social-uow-owner", world_id="social-uow-world", thread_id="chat-one",
                requester_world_character_id="social-uow-owner-actor", responding_world_character_id="social-uow-autonomous-actor")
            lifecycle = SqlAlchemyResponseLifecycleRepository(db)
            record = lifecycle.accept(CreateResponseRequest(request_id="cancel-request", thread_id="chat-one",
                user_message_id=message.id, response_slot_id="cancel-slot",
                request_scope_hash=build_request_scope_hash(**scope, user_message_id=message.id),
                idempotency_key="cancel-idempotency-key", generation_id="cancel-generation", attempt_number=1,
                selected_model="fixture-model", deadline_at=datetime.now(UTC)+timedelta(minutes=2)))
            db.commit()
            command = fixture.ResponseWorkflowCommand(request=record,
                preflight=fixture.RetrievalPreflightCommand(request_id=record.request_id,
                    **scope, user_message="synthetic cancellation"),
                profile=fixture.CharacterResponseProfile(name="Synthetic", handle="synthetic", one_liner="fixture",
                    personality="calm", speech_style="short", worldview="fixture", topic_preferences="chat", safety_rules="safe"),
                router_context=(), response_context=(), character_labels={})

            async def waiting_router(*args, **kwargs):
                entered.set()
                await anyio.sleep_forever()

            workflow = fixture._workflow(db, RetrievalRoute.CURRENT_CONTEXT, fixture._Generator(),
                router=SimpleNamespace(route=waiting_router))
            uow = SqlAlchemyResponseWorkflowUnitOfWork(db)
            original = uow.rollback
            def rollback():
                cleanup_started.set()
                assert release.wait(3)
                original()
            uow.rollback = rollback
            workflow._unit_of_work = uow
            scopes = []
            async def consume():
                with anyio.CancelScope() as cancellation:
                    scopes.append(cancellation)
                    async for _ in workflow.run(command):
                        pass
            task = asyncio.create_task(consume())
            try:
                await wait_for(entered)
                if cancel_style == "anyio_scope":
                    scopes[0].cancel()
                else:
                    task.cancel()
                await wait_for(cleanup_started)
                if cancel_style == "repeated_task":
                    task.cancel()
                await asyncio.sleep(.02)
                assert not task.done()
                release.set()
                if cancel_style == "repeated_task":
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    await task
                saved = lifecycle.get_request(record.request_id)
                assert saved.state.value == "cancelled"
                assert saved.lease_token is None and saved.committed_assistant_message_id is None
                assert db.scalar(select(func.count()).select_from(models.MessageMessage).where(models.MessageMessage.role == "assistant")) == 0
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
    asyncio.run(run())
    assert engine.pool.checkedout() == 0
