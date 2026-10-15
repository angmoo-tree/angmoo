"""Contention at real SQLite boundaries and cancellation of owned workers."""
import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import threading
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.domains.identity.router.local import synchronize_environment
from app.domains.identity.service.environment import read_environment
from app.domains.identity.models_environment import LocalEnvironment
from app.runtime.graph_projection.worker import GraphProjectionWorker
from app.runtime.single_backend_components import SingleBackendRuntimeComponents
from identity.test_local_environment import database, report, NOW
from runtime.test_activity_settlement_sqlite import _fixture
from model_fixture_support import models


def test_environment_rollback_busy_maps_to_retryable_503_and_recovers(database, monkeypatch):
    db = database
    engine = db.get_bind()
    with engine.connect() as writer:
        writer.exec_driver_sql("PRAGMA journal_mode=WAL")
        writer.exec_driver_sql("BEGIN IMMEDIATE")
        monkeypatch.setattr("app.domains.identity.router.local.browser_session.require_local_frontend_request", lambda *a, **kw: None)
        context = SimpleNamespace(user=SimpleNamespace(id="owner"), session=SimpleNamespace(token_hash="synthetic"))
        with pytest.raises(HTTPException) as error:
            synchronize_environment(report(), None, db, context)
        assert (error.value.status_code, error.value.detail, error.value.headers) == (
            503, "environment_temporarily_busy", {"Retry-After": "1"})
        assert not db.in_transaction()
        assert db.get(LocalEnvironment, "owner") is None
        db.rollback()
        writer.rollback()
    result = synchronize_environment(report(), None, db, context)
    assert result.environment_revision == 1
    assert read_environment(db, "owner").environment_revision == 1


def test_graph_effect_ack_busy_retains_lease_and_replay_does_not_spend_poison_attempt(tmp_path):
    engine, _, _ = _fixture(tmp_path)
    held, applied = [], set()
    class Store:
        calls = 0
        def apply(self, command, **kwargs):
            self.calls += 1
            applied.add(repr(command))
            if self.calls == 1:
                connection = engine.connect(); connection.exec_driver_sql("BEGIN IMMEDIATE"); held.append(connection)
            return "applied"
    store = Store()
    worker = GraphProjectionWorker(session_factory=lambda: Session(engine), store=store,
        worker_id="test-worker", concurrency=1, batch_size=1)
    first = worker.process_batch()
    assert first.canonical_busy == 1 and first.succeeded == first.dead == 0
    held[0].rollback(); held[0].close()
    with Session(engine) as db:
        row = db.scalar(select(models.GraphProjectionOutbox).where(models.GraphProjectionOutbox.status == "processing"))
        identifier, attempts = row.id, row.attempt_count
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert worker.process_batch().succeeded == 1
    with Session(engine) as db:
        row = db.get(models.GraphProjectionOutbox, identifier)
        assert row.status == "succeeded" and row.attempt_count == attempts
    assert store.calls == 2 and len(applied) == 1
    engine.dispose()


def test_cancelled_shutdown_still_owns_projector_until_its_future_finishes():
    started, release = threading.Event(), threading.Event()
    async def scheduler(stop, listener):
        listener("ready")
        await stop.wait()
    def projector(stop, listener):
        listener("ready")
        started.set()
        assert release.wait(5)
        listener("stopped")
    async def run():
        runtime = SingleBackendRuntimeComponents(scheduler_runner=scheduler, projector_runner=projector,
            startup_timeout_seconds=2, shutdown_timeout_seconds=.1)
        await runtime.start()
        assert started.is_set()
        task = asyncio.create_task(runtime.stop())
        await asyncio.sleep(.15)
        task.cancel()
        await asyncio.sleep(.02)
        assert not task.done() and runtime._projector_work is not None
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime._projector_work is None and runtime._projector_task is None
    asyncio.run(run())
