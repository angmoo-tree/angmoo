"""Real temporary SQLite locks; fake activity effects, never provider calls."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import sqlite3
from threading import Event, Thread, get_ident
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from app.config import Settings
from app.core.sqlite_concurrency import run_sqlite_immediate, _is_busy_error
from app.domains.runtime.exceptions import SchedulerLeaseLostError
from app.exceptions import SqliteBusyRetryExhausted, SqliteTaskQueueFull
from app.runtime.resident.lease_executor import SchedulerLeaseExecutor
from app.runtime.resident import scheduler
from test_l3_er2_sqlite_concurrency import _database, _seed_installation, MutableClock, NOW
from app.runtime.persistence.sqlite_scheduler_lease import SqliteSchedulerLeaseRepository


@pytest.mark.parametrize("operation", ["acquire", "heartbeat", "begin_tick", "finish_tick", "release"])
def test_all_lease_writes_survive_a_short_real_lock(tmp_path, operation):
    database = _database(tmp_path); _seed_installation(database)
    repo = SqliteSchedulerLeaseRepository(database.engine)
    lease = repo.acquire(owner_id="test-owner", ttl_seconds=30)
    if operation == "finish_tick":
        permit = repo.begin_tick(owner_id="test-owner", fencing_epoch=lease.fencing_epoch, ttl_seconds=30, interval_seconds=60)
    locked, unlock = Event(), Event()
    def holder():
        with sqlite3.connect(database.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE"); locked.set()
            unlock.wait(2); connection.rollback()
    thread = Thread(target=holder); thread.start(); assert locked.wait(2)
    releaser = Thread(target=lambda: (sleep(0.075), unlock.set())); releaser.start()
    kwargs = {"owner_id": "test-owner", "ttl_seconds": 30}
    if operation != "acquire": kwargs["fencing_epoch"] = lease.fencing_epoch
    if operation == "begin_tick": kwargs["interval_seconds"] = 60
    if operation in {"finish_tick", "release"}: kwargs.pop("ttl_seconds")
    if operation == "finish_tick":
        kwargs.update(result=scheduler.SchedulerTickResult.SUCCESS, expected_tick=permit.logical_window_at, finished_at=datetime.now(UTC))
    try:
        result = getattr(repo, operation)(**kwargs)
        assert result is not None
    finally:
        unlock.set(); thread.join(2); releaser.join(2); database.close()


def test_busy_budget_rollback_timeout_restoration_and_error_classification(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'budget.db'}", connect_args={"timeout": 5})
    with engine.begin() as connection: connection.exec_driver_sql("CREATE TABLE effects(value INTEGER)")
    lock = sqlite3.connect(tmp_path / "budget.db"); lock.execute("BEGIN IMMEDIATE")
    facts = []; started = monotonic()
    try:
        with pytest.raises(SqliteBusyRetryExhausted) as failure:
            run_sqlite_immediate(engine, lambda c: c.exec_driver_sql("INSERT INTO effects VALUES(1)"), observer=facts.append)
        assert failure.value.sqlite_errorcode & 255 == sqlite3.SQLITE_BUSY
        assert monotonic() - started < 0.45
        assert 1 <= len([fact for fact in facts if fact["result"] == "busy"]) <= 4
        with engine.connect() as connection: assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
    finally: lock.rollback(); lock.close()
    def invalid(connection):
        connection.exec_driver_sql("INSERT INTO effects VALUES(2)"); raise ValueError("abort")
    with pytest.raises(ValueError): run_sqlite_immediate(engine, invalid)
    with engine.connect() as connection: assert connection.exec_driver_sql("SELECT count(*) FROM effects").scalar() == 0
    for code in (sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_IOERR, sqlite3.SQLITE_FULL):
        error = sqlite3.OperationalError("database is locked"); error.sqlite_errorcode = code
        assert not _is_busy_error(error)
    error = sqlite3.OperationalError("snapshot"); error.sqlite_errorcode = sqlite3.SQLITE_BUSY_SNAPSHOT
    assert _is_busy_error(error)
    assert _is_busy_error(sqlite3.OperationalError("database is locked"))
    assert not _is_busy_error(RuntimeError("database is locked"))
    engine.dispose()


def test_same_expired_owner_requires_new_epoch(tmp_path):
    database = _database(tmp_path); _seed_installation(database)
    clock = MutableClock(NOW); repo = SqliteSchedulerLeaseRepository(database.engine, clock=clock)
    old = repo.acquire(owner_id="owner", ttl_seconds=2); clock.advance(seconds=3)
    new = repo.acquire(owner_id="owner", ttl_seconds=30)
    assert new.fencing_epoch == old.fencing_epoch + 1
    with pytest.raises(SchedulerLeaseLostError): repo.heartbeat(owner_id="owner", fencing_epoch=old.fencing_epoch, ttl_seconds=30)
    database.close()


def test_bounded_checkout_uses_actual_runtime_engine(tmp_path):
    database = _database(tmp_path); _seed_installation(database)
    assert database.engine.pool.timeout() == 0.05
    connections = [database.engine.connect() for _ in range(15)]
    try:
        started = monotonic()
        with pytest.raises(SqliteTaskQueueFull): run_sqlite_immediate(database.engine, lambda _c: None)
        assert monotonic() - started < 0.2
    finally:
        for connection in connections: connection.close()
        database.close()


def test_queue_capacity_cancelled_waiter_and_real_worker_lifetime():
    worker_started, release = Event(), Event(); thread_ids = []
    class Coordinator:
        def acquire(self, **_kwargs):
            thread_ids.append(get_ident()); worker_started.set(); release.wait(2); return "settled"
    async def scenario():
        executor = SchedulerLeaseExecutor(Coordinator)
        jobs = [asyncio.create_task(executor.call("acquire")) for _ in range(4)]
        await asyncio.to_thread(worker_started.wait, 1)
        with pytest.raises(SqliteTaskQueueFull): await executor.call("acquire")
        probes = 0
        for _ in range(5): await asyncio.sleep(0.01); probes += 1
        jobs[0].cancel()
        with pytest.raises(asyncio.CancelledError): await jobs[0]
        assert not await executor.drain(0.01)
        assert probes == 5 and thread_ids[0] != get_ident()
        release.set(); assert await executor.drain(1)
        await asyncio.gather(*jobs, return_exceptions=True); executor.close()
    try: asyncio.run(scenario())
    finally: release.set()


def test_runtime_adapter_recovers_on_same_loop_with_live_proof(tmp_path, monkeypatch):
    database = _database(tmp_path); _seed_installation(database)
    # Keep this recovery inside one logical window, even when the runner pauses
    # across a wall-clock boundary. Lease reads and health share the same clock.
    clock = MutableClock(NOW + timedelta(seconds=9, microseconds=900_000))
    finish_entered, allow_finish = Event(), Event()
    class ClockedRepository(SqliteSchedulerLeaseRepository):
        def __init__(self, engine):
            super().__init__(engine, clock=clock)
        def finish_tick(self, **kwargs):
            finish_entered.set()
            assert allow_finish.wait(3), "test did not release the finish operation"
            return super().finish_tick(**kwargs)
    monkeypatch.setattr(scheduler, "SqliteSchedulerLeaseRepository", ClockedRepository)
    monkeypatch.setattr(scheduler, "datetime", SimpleNamespace(now=lambda _tz=None: clock()))
    probe = SqliteSchedulerLeaseRepository(database.engine, clock=clock)
    config = Settings().model_copy(update={"RESIDENT_TICK_INTERVAL_SECONDS": 10,
        "RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS": 1, "RESIDENT_TICK_LEASE_TTL_SECONDS": 6,
        "RESIDENT_TICK_SHUTDOWN_DRAIN_SECONDS": 1,
        "RESIDENT_TICK_READY_PATH": str(tmp_path / "ready"), "RESIDENT_TICK_PROCESS_LOCK_PATH": str(tmp_path / "lock")})
    states = []; effects = []; ticks = asyncio.Event()
    async def tick(): effects.append("one"); ticks.set(); return SimpleNamespace(started_count=1)
    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(scheduler.run_resident_tick_scheduler(config=config,
            session_factory=database.session_factory, tick_runner=tick, stop_event=stop, state_listener=states.append))
        try:
            await asyncio.wait_for(ticks.wait(), 3)
            assert await asyncio.to_thread(finish_entered.wait, 3)
            # The callback is deliberately complete before its durable receipt.
            assert (await asyncio.to_thread(probe.read)).last_tick_finished_at is None
            allow_finish.set()
            deadline = monotonic() + 3
            while True:
                receipt = await asyncio.to_thread(probe.read)
                if receipt.last_tick_finished_at is not None: break
                assert monotonic() < deadline, "first tick did not commit its receipt"
                await asyncio.sleep(0.01)
            assert receipt.last_tick_result is scheduler.SchedulerTickResult.SUCCESS
            assert scheduler.scheduler_is_ready(config)
            with sqlite3.connect(database.database_path) as holder:
                holder.execute("BEGIN IMMEDIATE")
                deadline = monotonic() + 3
                while "degraded" not in states and monotonic() < deadline: await asyncio.sleep(0.05)
                assert states[-1] == "degraded" and not scheduler.scheduler_is_ready(config)
                holder.rollback()
            deadline = monotonic() + 3
            while states[-1] != "ready" and monotonic() < deadline: await asyncio.sleep(0.05)
            assert states[-1] == "ready" and scheduler.scheduler_is_ready(config)
            assert effects == ["one"]  # A committed logical window was not replayed.
        finally:
            allow_finish.set(); stop.set(); await asyncio.wait_for(task, 3)
        assert not scheduler.scheduler_is_ready(config)
    try: asyncio.run(scenario())
    finally: allow_finish.set(); database.close()


def test_health_rejects_registry_ready_without_a_live_proof(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.main import runtime_health
    from app.domains.runtime.service.components import component_observations
    from app.domains.runtime.contracts.status import RuntimeComponentState
    from contextlib import contextmanager
    from app.runtime import component_workers
    config = Settings().model_copy(update={"RESIDENT_TICK_READY_PATH": "test-health-only"})
    @contextmanager
    def session(): yield SimpleNamespace(execute=lambda _q: SimpleNamespace(scalar_one=lambda: 1))
    app = FastAPI(); app.state.runtime_composition = SimpleNamespace(session_factory=session, settings=config)
    app.state.runtime_config = SimpleNamespace(profile=SimpleNamespace(value="public"))
    app.add_api_route("/health", runtime_health)
    monkeypatch.setattr(component_workers, "borrow_runtime_graph_client", lambda _c: SimpleNamespace(verify_connectivity=lambda: None))
    component_observations.reset()
    for name in ("scheduler", "projector"): component_observations.update(name, RuntimeComponentState.READY)
    client = TestClient(app)
    try:
        assert client.get("/health").status_code == 503
        scheduler._record_proof(config, SimpleNamespace(lease_expires_at=datetime.now(UTC) + timedelta(seconds=3)))
        assert client.get("/health").status_code == 200
        component_observations.update("scheduler", RuntimeComponentState.DEGRADED)
        assert client.get("/health").status_code == 503
    finally: scheduler._clear_proof(config); component_observations.reset()


def test_queue_deadline_does_not_execute_an_expired_queued_write():
    entered, release = Event(), Event(); executions = []
    class Coordinator:
        def acquire(self, **kwargs):
            executions.append(kwargs["owner_id"])
            if kwargs["owner_id"] == "first": entered.set(); release.wait(3)
            return True
    async def scenario():
        executor = SchedulerLeaseExecutor(Coordinator)
        first = asyncio.create_task(executor.call("acquire", owner_id="first"))
        await asyncio.to_thread(entered.wait, 1)
        queued = asyncio.create_task(executor.call("acquire", owner_id="expired"))
        await asyncio.sleep(1.1); release.set(); await first
        with pytest.raises(SqliteTaskQueueFull, match="queue_deadline"): await queued
        assert executions == ["first"]
        assert await executor.drain(1); executor.close()
    try: asyncio.run(scenario())
    finally: release.set()


@pytest.mark.parametrize("failure_type", [SchedulerLeaseLostError, ValueError])
def test_unsettled_children_keep_primary_error_and_are_not_restarted(failure_type):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def stubborn():
            entered.set()
            try: await release.wait()
            except asyncio.CancelledError: await release.wait()
            return SimpleNamespace(started_count=0)
        original = failure_type("safe_primary_failure")
        class Coordinator:
            def heartbeat(self, **_kwargs): raise original
        async def fast_sleep(_seconds): await entered.wait()
        with pytest.raises(failure_type) as failure:
            await scheduler._run_fenced_tick_with_heartbeat(coordinator=Coordinator(), owner_id="synthetic", fencing_epoch=1,
                tick_runner=stubborn, sleep=fast_sleep, drain_timeout_seconds=0.1)
        assert failure.value is original and len(original.pending_tasks) == 1
        release.set(); await asyncio.gather(*original.pending_tasks)
    asyncio.run(scenario())


def test_expired_proof_fails_readiness_without_another_database_call():
    config = Settings().model_copy(update={"RESIDENT_TICK_READY_PATH": "expired-proof-only"})
    try:
        scheduler._record_proof(config, SimpleNamespace(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
        assert not scheduler.scheduler_is_ready(config)
    finally: scheduler._clear_proof(config)


def test_failed_finish_with_real_lock_does_not_replay_completed_effect(tmp_path):
    database = _database(tmp_path); _seed_installation(database)
    holder = sqlite3.connect(database.database_path, check_same_thread=False)
    config = Settings().model_copy(update={"RESIDENT_TICK_INTERVAL_SECONDS": 60, "RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS": 1,
        "RESIDENT_TICK_LEASE_TTL_SECONDS": 6, "RESIDENT_TICK_SHUTDOWN_DRAIN_SECONDS": 1,
        "RESIDENT_TICK_READY_PATH": str(tmp_path / "ready"), "RESIDENT_TICK_PROCESS_LOCK_PATH": str(tmp_path / "lock")})
    states, effects = [], []
    async def scenario():
        stop = asyncio.Event()
        async def tick():
            effects.append("committed_effect"); holder.execute("BEGIN IMMEDIATE")
            return SimpleNamespace(started_count=1)
        task = asyncio.create_task(scheduler.run_resident_tick_scheduler(config=config, session_factory=database.session_factory,
            tick_runner=tick, stop_event=stop, state_listener=states.append))
        deadline = monotonic() + 3
        while "degraded" not in states and monotonic() < deadline: await asyncio.sleep(0.05)
        assert states[-1] == "degraded"; holder.rollback()
        deadline = monotonic() + 3
        while states[-1] != "ready" and monotonic() < deadline: await asyncio.sleep(0.05)
        assert states[-1] == "ready" and effects == ["committed_effect"]
        stop.set(); await asyncio.wait_for(task, 3)
    try: asyncio.run(scenario())
    finally: holder.rollback(); holder.close(); database.close()


def test_primary_start_failure_survives_actual_locked_release(tmp_path, caplog):
    database = _database(tmp_path); _seed_installation(database)
    holder = sqlite3.connect(database.database_path, check_same_thread=False)
    original = ValueError("private conversation body must not enter logs")
    repo = SqliteSchedulerLeaseRepository(database.engine)
    class Coordinator:
        def acquire(self, **kwargs): return repo.acquire(ttl_seconds=30, **kwargs)
        def heartbeat(self, **kwargs): return repo.heartbeat(ttl_seconds=30, **kwargs)
        def begin_tick(self, **_kwargs): holder.execute("BEGIN IMMEDIATE"); raise original
        def release(self, **kwargs): return repo.release(**kwargs)
    config = Settings().model_copy(update={"RESIDENT_TICK_READY_PATH": str(tmp_path / "ready"), "RESIDENT_TICK_PROCESS_LOCK_PATH": str(tmp_path / "lock")})
    async def scenario():
        with pytest.raises(ValueError) as failure:
            await scheduler.run_resident_tick_scheduler(config=config, coordinator=Coordinator())
        assert failure.value is original and not scheduler.scheduler_is_ready(config)
    try:
        asyncio.run(scenario()); assert "private conversation" not in caplog.text
        assert "scheduler_cleanup_failed" in caplog.text
    finally: holder.rollback(); holder.close(); database.close()


def test_non_lease_primary_with_live_child_never_finishes_or_restarts(tmp_path, monkeypatch):
    calls, states = [], []
    config = Settings().model_copy(update={"RESIDENT_TICK_READY_PATH": str(tmp_path / "ready"),
        "RESIDENT_TICK_PROCESS_LOCK_PATH": str(tmp_path / "lock")})
    lease = SimpleNamespace(fencing_epoch=1, lease_expires_at=datetime.now(UTC) + timedelta(seconds=30))
    class Coordinator:
        def acquire(self, **kwargs):
            calls.append("acquire"); lease.lease_owner_id = kwargs["owner_id"]; return lease
        def heartbeat(self, **_kwargs): return lease
        def begin_tick(self, **_kwargs): calls.append("begin"); return SimpleNamespace(should_run=True)
        def finish_tick(self, **_kwargs): calls.append("finish"); return lease
        def release(self, **_kwargs): calls.append("release")
    async def scenario():
        release = asyncio.Event()
        child = asyncio.create_task(release.wait())
        primary = ValueError("safe_primary_failure")
        primary.pending_tasks = (child,)
        async def failed_tick(**_kwargs): raise primary
        monkeypatch.setattr(scheduler, "_run_fenced_tick_with_heartbeat", failed_tick)
        with pytest.raises(ValueError) as failure:
            await scheduler.run_resident_tick_scheduler(config=config, coordinator=Coordinator(),
                state_listener=states.append, drain_timeout_seconds=0.05)
        assert failure.value is primary and calls == ["acquire", "begin"]
        assert states[-1] == "failed" and not scheduler.scheduler_is_ready(config)
        release.set(); await child
    asyncio.run(scenario())
