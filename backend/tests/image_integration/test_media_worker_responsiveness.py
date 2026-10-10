"""Actual SQLite checkout waits cannot block timers or cross Session threads."""
import asyncio
from threading import get_ident

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from image_integration.test_generation_lifecycle import configured, admit

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("operation", ["idle", "maintenance", "generation"])
def test_pool_release_timer_runs_while_media_waits_for_checkout(tmp_path, operation):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media) if operation == "generation" else None
    engine = create_engine(sessions.kw["bind"].url, pool_size=1, max_overflow=0,
        pool_timeout=0.25, connect_args={"check_same_thread": False})
    limited = sessionmaker(engine, expire_on_commit=False)
    media.sessions = media.worker.sessions = media.interpretation.sessions = limited
    held = engine.connect()
    loop_thread, checkout_threads = get_ident(), []
    @event.listens_for(engine, "checkout")
    def checkout(*args):
        checkout_threads.append(get_ident())
    async def exercise():
        if operation == "idle":
            task = asyncio.create_task(media.worker.tick())
        elif operation == "generation":
            task = asyncio.create_task(media.worker.process(job_id))
        else:
            task = asyncio.create_task(media._canonical_work.call(media._maintenance))
        try:
            await asyncio.sleep(0.03)
            assert not task.done(), "checkout wait returned before timer released the pool"
            held.close()
            await asyncio.wait_for(task, 3)
        finally:
            held.close()
            await media._canonical_work.drain()
    try:
        asyncio.run(exercise())
        assert checkout_threads and loop_thread not in checkout_threads
        assert provider.calls == (1 if operation == "generation" else 0)
    finally:
        held.close()
        media._canonical_work.close()
        engine.dispose()


def test_provider_remains_on_loop_but_every_local_phase_uses_owned_worker(tmp_path):
    sessions, media, provider = configured(tmp_path)
    job_id = admit(sessions, media)
    loop_thread, sql_threads = get_ident(), []
    generate = provider.generate
    async def provider_call(*args, **kwargs):
        assert get_ident() == loop_thread
        return await generate(*args, **kwargs)
    provider.generate = provider_call
    submit = media.submit
    async def diagnosed_submit(execution, **kwargs):
        await kwargs["on_diagnostic"]({"kind": "warning", "stage": "output", "messages": []})
        return await submit(execution, **kwargs)
    media.submit = diagnosed_submit
    def sql(*args): sql_threads.append(get_ident())
    engine = sessions.kw["bind"]
    event.listen(engine, "before_cursor_execute", sql)
    try:
        asyncio.run(media.worker.process(job_id))
        assert provider.calls == 1
        assert sql_threads and loop_thread not in sql_threads
    finally:
        event.remove(engine, "before_cursor_execute", sql)
        media._canonical_work.close()
