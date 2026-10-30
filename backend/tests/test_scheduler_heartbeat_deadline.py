"""Offline deadline/recovery regressions with real threads and temporary SQLite."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from threading import Event
from time import monotonic
from time import sleep as blocking_sleep
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from app.config import Settings
from app.core.sqlite_concurrency import run_sqlite_immediate
from app.domains.runtime.exceptions import SchedulerLeaseLostError
from app.exceptions import SqliteBusyRetryExhausted, SqliteWriteDeadlineExceeded
from app.runtime.persistence.lease_operation import current_lease_operation
from app.runtime.resident import scheduler
from app.runtime.resident.lease_errors import SchedulerHeartbeatDeadlineExceeded
from app.runtime.resident.lease_executor import SchedulerLeaseExecutor


def _proof(owner="owner", seconds=45, epoch=1):
    return SimpleNamespace(lease_owner_id=owner, fencing_epoch=epoch,
                          lease_expires_at=datetime.now(UTC) + timedelta(seconds=seconds))


def _config(tmp_path):
    return Settings().model_copy(update={"RESIDENT_TICK_READY_PATH": str(tmp_path / "ready"),
        "RESIDENT_TICK_PROCESS_LOCK_PATH": str(tmp_path / "lock")})


def test_deadline_before_sql_and_before_commit_rolls_back(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'deadline.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE effects(value INTEGER)")
    clock = [0.0]
    calls = []
    def write(connection):
        calls.append("write")
        connection.exec_driver_sql("INSERT INTO effects VALUES(1)")
        clock[0] = 2.0
    try:
        with pytest.raises(SqliteWriteDeadlineExceeded):
            run_sqlite_immediate(engine, write, deadline=0, monotonic=lambda: clock[0])
        assert not calls
        with pytest.raises(SqliteWriteDeadlineExceeded):
            run_sqlite_immediate(engine, write, deadline=1, monotonic=lambda: clock[0])
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT count(*) FROM effects").scalar() == 0
        assert run_sqlite_immediate(engine, lambda c: c.exec_driver_sql("INSERT INTO effects VALUES(2)").rowcount) == 1
    finally:
        engine.dispose()


def test_first_queue_and_writer_use_one_deadline_without_runtime_replay(tmp_path):
    contexts = []
    class Coordinator:
        def heartbeat(self, **_kwargs):
            contexts.append(current_lease_operation())
            raise SqliteBusyRetryExhausted("synthetic_busy")
    async def scenario():
        executor = SchedulerLeaseExecutor(Coordinator)
        started = monotonic()
        try:
            with pytest.raises(SqliteBusyRetryExhausted):
                await scheduler._heartbeat_with_budget(executor, owner_id="owner", fencing_epoch=1,
                    config=_config(tmp_path), proof=_proof())
            assert len(contexts) == 1
            assert started < contexts[0].deadline <= started + 2.1
            assert contexts[0].retry_policy.max_attempts == 12
            assert contexts[0].retry_policy.maximum_elapsed_seconds == 2
        finally:
            assert await executor.drain(1)
            executor.close()
    asyncio.run(scenario())


def test_deadline_wait_tracks_real_late_worker_and_logs_safe_result(tmp_path, caplog):
    entered, release = Event(), Event()
    class Coordinator:
        def heartbeat(self, **_kwargs):
            entered.set()
            assert release.wait(5)
            return _proof()
    async def scenario():
        executor = SchedulerLeaseExecutor(Coordinator)
        try:
            with pytest.raises(SchedulerHeartbeatDeadlineExceeded):
                await scheduler._heartbeat_with_budget(executor, owner_id="owner", fencing_epoch=1,
                    config=_config(tmp_path), proof=_proof())
            assert entered.is_set() and not await executor.drain(0.01)
            release.set()
            assert await executor.drain(1)
            assert "scheduler_lease_wait_cancelled" in caplog.text
            assert "late_success" in caplog.text
        finally:
            release.set()
            await executor.drain(1)
            executor.close()
    asyncio.run(scenario())


def test_unrelated_timeout_and_user_cancel_are_not_relabelled(tmp_path):
    original = TimeoutError("private original error")
    class Coordinator:
        def heartbeat(self, **_kwargs):
            raise original
    async def scenario():
        executor = SchedulerLeaseExecutor(Coordinator)
        try:
            with pytest.raises(TimeoutError) as result:
                await scheduler._heartbeat_with_budget(executor, owner_id="owner", fencing_epoch=1,
                    config=_config(tmp_path), proof=_proof())
            assert result.value is original
        finally:
            await executor.drain(1); executor.close()
        entered, release = Event(), Event()
        class Waiting:
            def heartbeat(self, **_kwargs):
                entered.set(); release.wait(3); return _proof()
        executor = SchedulerLeaseExecutor(Waiting)
        task = asyncio.create_task(scheduler._heartbeat_with_budget(executor, owner_id="owner", fencing_epoch=1,
            config=_config(tmp_path), proof=_proof()))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
        finally:
            release.set(); await executor.drain(1); executor.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("proof_args,expected", [({"seconds": -1}, SchedulerLeaseLostError),
    ({"owner": "other"}, SchedulerLeaseLostError),
    ({"seconds": 10}, SchedulerHeartbeatDeadlineExceeded)])
def test_unsafe_lease_does_not_submit_heartbeat(tmp_path, proof_args, expected):
    proof = _proof(**proof_args)
    class Coordinator:
        def heartbeat(self, **_kwargs): raise AssertionError("must not submit")
    with pytest.raises(expected):
        asyncio.run(scheduler._heartbeat_with_budget(Coordinator(), owner_id="owner", fencing_epoch=1,
            config=_config(tmp_path), proof=proof))


@pytest.mark.parametrize('outcome', ['on_time', 'late', 'expired', 'offset_expired', 'external_cancel'])
def test_worker_completion_and_loop_delivery_are_distinct(tmp_path, monkeypatch, outcome):
    entered = Event()
    class Coordinator:
        def heartbeat(self, **kwargs):
            entered.set()
            blocking_sleep(.16 if outcome == 'late' else .01)
            proof = _proof(seconds=-1 if outcome in {'expired', 'offset_expired'} else 45)
            if outcome == 'offset_expired':
                proof.lease_expires_at = proof.lease_expires_at.astimezone(timezone(timedelta(hours=9)))
            return proof

    monkeypatch.setattr(scheduler, '_lease_write_deadline', lambda **kwargs: monotonic() + .1)
    async def scenario():
        executor = SchedulerLeaseExecutor(Coordinator)
        task = asyncio.create_task(scheduler._heartbeat_with_budget(executor, owner_id='owner',
            fencing_epoch=1, config=_config(tmp_path), proof=_proof()))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            # Reproduce synchronous work delaying callback delivery. The actual
            # DB worker can finish while the asyncio loop cannot receive it.
            blocking_sleep(.25)
            if outcome == 'external_cancel':
                task.cancel()
            if outcome == 'on_time':
                assert (await task).lease_owner_id == 'owner'
            else:
                expected = {'late': SchedulerHeartbeatDeadlineExceeded,
                    'expired': SchedulerLeaseLostError, 'offset_expired': SchedulerLeaseLostError,
                    'external_cancel': asyncio.CancelledError}[outcome]
                with pytest.raises(expected):
                    await task
        finally:
            await executor.drain(1)
            executor.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("location", ["idle", "active"])
def test_timeout_recovers_same_runner_only_after_real_worker_drain(tmp_path, monkeypatch, location):
    entered, release = Event(), Event()
    states, calls = [], []
    config = _config(tmp_path)
    class Coordinator:
        def acquire(self, **kwargs): return _proof(kwargs["owner_id"])
        def heartbeat(self, **kwargs):
            calls.append("heartbeat")
            if calls.count("heartbeat") == 2:
                entered.set(); assert release.wait(6)
            return _proof(kwargs["owner_id"])
        def begin_tick(self, **_kwargs):
            calls.append("begin"); return SimpleNamespace(should_run=location == "active" and calls.count("begin") == 1)
        def finish_tick(self, **kwargs):
            calls.append("finish"); return _proof(kwargs["owner_id"])
        def release(self, **_kwargs): calls.append("release")
    async def scenario():
        stop = asyncio.Event()
        tick_started = asyncio.Event()
        tick_cancelled = asyncio.Event()
        async def tick():
            tick_started.set()
            try: await asyncio.Event().wait()
            finally: tick_cancelled.set()
        async def tick_sleep(_seconds):
            if location == "active": await tick_started.wait()
            await asyncio.sleep(0.01)
        async def idle(**kwargs):
            if location == "idle":
                await scheduler._heartbeat_with_budget(kwargs["coordinator"], owner_id=kwargs["owner_id"],
                    fencing_epoch=kwargs["fencing_epoch"], config=config)
            await stop.wait()
            return False
        monkeypatch.setattr(scheduler, "_sleep_until_next_tick_with_heartbeat", idle)
        task = asyncio.create_task(scheduler.run_resident_tick_scheduler(coordinator=Coordinator(),
            config=config, stop_event=stop, tick_runner=tick, sleep=tick_sleep, state_listener=states.append))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            limit = monotonic() + 4
            while "degraded" not in states:
                assert monotonic() < limit
                await asyncio.sleep(0.02)
            assert states[-1] == "degraded" and not scheduler.scheduler_is_ready(config)
            assert calls.count("begin") == 1
            if location == "active": assert tick_cancelled.is_set()
            release.set()
            limit = monotonic() + 3
            while states.count("ready") < 2:
                assert monotonic() < limit
                await asyncio.sleep(0.02)
            assert scheduler.scheduler_is_ready(config) and not task.done()
            assert "finish" not in calls  # The cancelled activity was not declared complete.
        finally:
            release.set(); stop.set(); await asyncio.wait_for(task, 3)
    asyncio.run(scenario())
