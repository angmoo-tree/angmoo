"""Finite native-process lifecycle, without AI or application database writes."""
import asyncio
import os
import time
from time import monotonic

import pytest

from app.runtime.memory.search_worker_pool import SearchReadWorkers
from app.contracts.search_diagnostics import SearchSummaryCollector, summary_current


def echo_child(pipe, query, deadline):
    if isinstance(query, tuple) and query[0] == "delay":
        time.sleep(query[1])
    if query == "slow":
        from app.runtime.memory.worker_diagnostics import phase
        with phase("fts_search"):
            time.sleep(60)
    pipe.send((True, (os.getpid(), query)))
    pipe.close()


class EchoWorkers(SearchReadWorkers):
    _axis = "fts"
    _child_target = staticmethod(echo_child)

    def __init__(self, concurrency=1):
        super().__init__(arguments=(), concurrency=concurrency)


def test_demand_preparation_reuse_request_isolation_and_stop():
    async def run():
        workers = EchoWorkers()
        assert not workers.active_processes
        assert workers.preparation_status()["status"] == "not_started"
        workers.request_preparation()
        assert workers.request_preparation()["status"] == "preparing"
        first = await workers.search("first", deadline=monotonic() + 15)
        for index in range(100):
            result = await workers.search(index, deadline=monotonic() + 2)
            assert result == (first[0], index)
            assert workers.busy_jobs == 0
            assert len(workers.active_processes) == 1
        await workers.stop()
        assert not workers.active_processes
    asyncio.run(run())


def test_cancel_waiter_keeps_shared_preparation():
    async def run():
        workers = EchoWorkers()
        pending = asyncio.create_task(workers.search("cancel", deadline=monotonic() + 15))
        await asyncio.sleep(.01)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        result = await workers.search("next", deadline=monotonic() + 15)
        assert result[1] == "next"
        await workers.stop()
    asyncio.run(run())


def test_busy_deadline_reaps_only_its_worker_and_reports_cleanup():
    async def run():
        workers = EchoWorkers()
        await workers.search("ready", deadline=monotonic() + 15)
        summary = SearchSummaryCollector()
        token = summary_current.set(summary)
        try:
            with pytest.raises(TimeoutError):
                await workers.search("slow", deadline=monotonic() + 1)
            row = summary.payload()["axes"][0]
            assert row["joined"] and row["worker_state_after"] == "retired"
            assert row["last_observed_stage"] == "fts_search"
            assert not row["request_cleanup_complete"]
            assert not workers.active_processes
        finally:
            summary_current.reset(token)
            await workers.stop()
    asyncio.run(run())


def test_fifo_queue_bound_and_cancelled_waiter_does_not_take_a_slot():
    from app.runtime.memory.search_worker_pool import SearchWorkerUnavailable
    async def run():
        workers = EchoWorkers()
        done = []
        async def query(value):
            result = await workers.search(value, deadline=monotonic() + 10)
            done.append(value)
            return result
        try:
            await workers.search("warm", deadline=monotonic() + 15)
            busy = asyncio.create_task(query(("delay", .5)))
            while not workers.busy_jobs:
                await asyncio.sleep(.001)
            waiting = [asyncio.create_task(query(i)) for i in range(8)]
            while len(workers._waiters) != 8:
                await asyncio.sleep(.001)
            with pytest.raises(SearchWorkerUnavailable, match="queue_full"):
                await workers.search("overflow", deadline=monotonic() + 10)
            waiting[2].cancel()
            await asyncio.gather(busy, *waiting, return_exceptions=True)
            assert done == [("delay", .5), 0, 1, 3, 4, 5, 6, 7]
            assert not workers._waiters and not workers.busy_jobs
            assert len(workers.active_processes) == 1
        finally:
            await workers.stop()
    asyncio.run(run())


def test_uncertain_exit_holds_capacity_until_confirmed(monkeypatch):
    async def run():
        workers = EchoWorkers()
        await workers.search("warm", deadline=monotonic() + 15)
        slot = workers._workers[0]
        try:
            # Real terminate still runs. Only the OS-exit observation is delayed.
            with monkeypatch.context() as patcher:
                patcher.setattr(slot.process, "is_alive", lambda: True)
                await workers._retire(slot)
                assert slot.state == "quarantined" and not slot.joined
                workers.request_preparation()
                assert workers._workers == [slot], "unknown process exit must consume capacity"
            await workers.stop()
            assert slot.joined and not workers.active_processes
        finally:
            await workers.stop()
    asyncio.run(run())


def test_stop_owns_preparation_and_expired_request_never_spawns():
    async def run():
        workers = EchoWorkers()
        with pytest.raises(TimeoutError):
            await workers.search("expired", deadline=monotonic() - 1)
        assert workers._round is None and not workers.active_processes
        await workers._control.preparation_slots.acquire()
        await workers._control.preparation_slots.acquire()
        workers.request_preparation()
        await asyncio.sleep(.01)
        await workers.stop()
        assert not workers._workers
        assert workers.preparation_status()["status"] == "unavailable"
    asyncio.run(run())
