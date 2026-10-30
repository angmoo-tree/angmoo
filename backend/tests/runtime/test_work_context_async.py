"""Async labels span awaited work and always restore the caller's context."""
import asyncio

import pytest

from app.core import work_observation as observation


@pytest.mark.parametrize("ending", ["complete", "cancel", "failure"])
def test_contextual_coroutine_preserves_worker_labels_and_restores_scope(ending):
    rows = []
    remove = observation.install(rows.append)

    @observation.contextual(chat_stage="cancel_or_failure")
    async def work():
        observation.emit("before_await")
        await asyncio.sleep(0)
        await asyncio.to_thread(observation.emit, "worker")
        try:
            if ending == "cancel":
                raise asyncio.CancelledError()
            if ending == "failure":
                raise ValueError("synthetic")
            return "completed"
        finally:
            observation.emit("cleanup")

    async def run():
        with observation.scope(chat_stage="caller"):
            if ending == "complete":
                assert await work() == "completed"
            else:
                error = asyncio.CancelledError if ending == "cancel" else ValueError
                with pytest.raises(error):
                    await work()
            assert observation.facts()["chat_stage"] == "caller"
        assert "chat_stage" not in observation.facts()

    try:
        asyncio.run(run())
        assert [row["event"] for row in rows] == ["before_await", "worker", "cleanup"]
        assert all(row["chat_stage"] == "cancel_or_failure" for row in rows)
    finally:
        remove()
