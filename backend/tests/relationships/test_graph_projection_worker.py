from __future__ import annotations

from datetime import UTC, datetime, timedelta
import threading
import time
import pytest

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError as PoolCheckoutTimeout
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.models import Base
from app.domains.relationships.contracts.projection import (RelationshipProjectionBackendError)
from app.domains.relationships.contracts.outbox import OutboxCapacityError
from app.runtime.graph_projection.worker import GraphProjectionWorker
from p7_graph_support import seed_projection_fixture, sqlite_engine


class RecordingStore:
    def __init__(self, *, failure: str | None = None) -> None:
        self.failure = failure
        self.commands = []

    def apply(self, command, *, timeout_seconds: float = 5.0) -> str:
        self.commands.append(command)
        if self.failure:
            raise RelationshipProjectionBackendError(self.failure)
        return "applied"


def _session_factory(engine):
    return lambda: Session(engine, expire_on_commit=False)


def test_pending_row_is_claimed_once_and_succeeds() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db)
        outbox_id = fixture.outbox.id
    store = RecordingStore()
    first = GraphProjectionWorker(
        session_factory=_session_factory(engine), store=store, worker_id="worker-a"
    ).process_batch()
    second = GraphProjectionWorker(
        session_factory=_session_factory(engine), store=store, worker_id="worker-b"
    ).process_batch()
    with Session(engine) as db:
        row = db.get(models.GraphProjectionOutbox, outbox_id)
        assert row is not None
        assert row.status == "succeeded"
        assert row.attempt_count == 1
    assert first.succeeded == 1
    assert second.claimed == 0
    assert len(store.commands) == 1


def test_transient_failure_retries_without_losing_row() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="retry")
        outbox_id = fixture.outbox.id
    failing = RecordingStore(failure="ladybug_unavailable")
    result = GraphProjectionWorker(
        session_factory=_session_factory(engine), store=failing, worker_id="worker-a"
    ).process_batch()
    with Session(engine) as db:
        row = db.get(models.GraphProjectionOutbox, outbox_id)
        assert row is not None
        assert row.status == "pending"
        assert row.next_attempt_at is not None
        assert row.last_error_class == "ladybug_unavailable"
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    recovered = RecordingStore()
    recovery = GraphProjectionWorker(
        session_factory=_session_factory(engine), store=recovered, worker_id="worker-b"
    ).process_batch()
    assert result.retried == 1
    assert result.graph_degraded is True
    assert recovery.succeeded == 1
    assert recovery.graph_degraded is False


def test_repeated_graph_failures_still_exhaust_eight_attempts() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="exhausted")
        outbox_id = fixture.outbox.id
    store = RecordingStore(failure="ladybug_unavailable")
    worker = GraphProjectionWorker(
        session_factory=_session_factory(engine), store=store, worker_id="worker-a"
    )
    for attempt in range(1, 9):
        result = worker.process_batch()
        with Session(engine) as db:
            row = db.get(models.GraphProjectionOutbox, outbox_id)
            assert row.attempt_count == attempt
            assert row.status == ("dead" if attempt == 8 else "pending")
            assert row.last_error_class == "ladybug_unavailable"
            if attempt < 8:
                assert result.retried == 1
                row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
                db.commit()
            else:
                assert result.dead == 1
    assert worker.process_batch().claimed == 0
    assert len(store.commands) == 8
    engine.dispose()


def test_poison_payload_is_dead_without_store_call() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="poison")
        row = db.get(models.GraphProjectionOutbox, fixture.outbox.id)
        assert row is not None
        row.source_signature = "0" * 64
        db.commit()
    store = RecordingStore()
    result = GraphProjectionWorker(
        session_factory=_session_factory(engine), store=store, worker_id="worker-a"
    ).process_batch()
    with Session(engine) as db:
        row = db.scalar(select(models.GraphProjectionOutbox))
        assert row is not None
        assert row.status == "dead"
        assert row.last_error_class == "signature_mismatch"
    assert result.dead == 1
    assert store.commands == []


class BlockingStore:
    def __init__(self, *, expected_started: int) -> None:
        self.expected_started = expected_started
        self.started = 0
        self.started_event = threading.Event()
        self.release_event = threading.Event()
        self._lock = threading.Lock()

    def apply(self, command, *, timeout_seconds: float = 5.0) -> str:
        with self._lock:
            self.started += 1
            if self.started >= self.expected_started:
                self.started_event.set()
        assert self.release_event.wait(timeout=timeout_seconds)
        return "applied"


def test_shutdown_drains_inflight_and_returns_unstarted_claims_to_pending() -> None:
    engine = sqlite_engine()
    outbox_ids: list[str] = []
    with Session(engine, expire_on_commit=False) as db:
        for index in range(4):
            fixture = seed_projection_fixture(db, suffix=f"shutdown-{index}")
            outbox_ids.append(fixture.outbox.id)
    # The shared in-memory SQLite fixture exposes one physical connection and
    # therefore cannot model concurrent transaction commits safely. Keep this
    # shutdown-order test single-worker; PostgreSQL concurrency is covered by
    # test_graph_projection_postgres_concurrency.py.
    store = BlockingStore(expected_started=1)
    stop = threading.Event()
    worker = GraphProjectionWorker(
        session_factory=_session_factory(engine),
        store=store,
        worker_id="worker-drain",
        batch_size=4,
        concurrency=1,
        command_timeout_seconds=2.0,
        shutdown_drain_seconds=2.0,
    )
    result_holder = []

    thread = threading.Thread(
        target=lambda: result_holder.append(worker.process_batch(stop_event=stop))
    )
    thread.start()
    assert store.started_event.wait(timeout=2.0)
    stop.set()
    time.sleep(0.05)
    store.release_event.set()
    thread.join(timeout=3.0)

    assert not thread.is_alive()
    result = result_holder[0]
    assert result.claimed == 4
    assert result.succeeded == 1
    assert result.retried == 3
    with Session(engine) as db:
        rows = list(
            db.scalars(
                select(models.GraphProjectionOutbox).where(
                    models.GraphProjectionOutbox.id.in_(outbox_ids)
                )
            )
        )
        assert sum(row.status == "succeeded" for row in rows) == 1
        pending = [row for row in rows if row.status == "pending"]
        assert len(pending) == 3
        assert all(row.last_error_class == "shutdown_interrupted" for row in pending)
        assert all(row.lease_owner is None for row in pending)
        assert all(row.lease_expires_at is None for row in pending)


def test_idle_connectivity_failure_marks_projector_degraded_without_exiting() -> None:
    engine = sqlite_engine()
    states: list[str] = []
    stop = threading.Event()

    def probe() -> None:
        stop.set()
        raise RelationshipProjectionBackendError("ladybug_unavailable")

    GraphProjectionWorker(
        session_factory=_session_factory(engine),
        store=RecordingStore(),
        worker_id="worker-degraded",
    ).run_loop(
        poll_interval_seconds=1.0,
        stop_event=stop,
        connectivity_probe=probe,
        state_listener=states.append,
    )

    assert states == ["degraded"]


def test_pool_exhaustion_recovers_in_same_loop_and_projects_once(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'projector.sqlite3'}",
        pool_size=1, max_overflow=0, pool_timeout=0.02)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="checkout")
        outbox_id = fixture.outbox.id
    held = engine.connect()
    stop, states = threading.Event(), []
    store = RecordingStore()
    def observe(state):
        states.append(state)
        if state == "degraded":
            held.close()
        elif state == "ready":
            stop.set()
    try:
        GraphProjectionWorker(session_factory=_session_factory(engine), store=store,
            worker_id="checkout-recovery").run_loop(stop_event=stop, state_listener=observe)
        assert states == ["degraded", "ready"]
        assert len(store.commands) == 1
        with Session(engine) as db:
            row = db.get(models.GraphProjectionOutbox, outbox_id)
            assert row.status == "succeeded" and row.attempt_count == 1
    finally:
        held.close()
        engine.dispose()


def test_repeated_checkout_timeouts_back_off_and_never_report_ready(monkeypatch) -> None:
    states, delays = [], []
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, delay):
            delays.append(delay)
            self.stopped = len(delays) == 6
    worker = GraphProjectionWorker(session_factory=lambda: None, store=RecordingStore(), worker_id="backoff")
    def unavailable(**kwargs): raise OutboxCapacityError("synthetic checkout timeout")
    monkeypatch.setattr(worker, "process_batch", unavailable)
    worker.run_loop(stop_event=Stop(), state_listener=states.append)
    assert states == ["degraded"] * 6
    assert delays == [2, 4, 8, 16, 30, 30]


@pytest.mark.parametrize("adapter", ("sqlalchemy", "sqlite"))
@pytest.mark.parametrize("operation", ("claim", "load_command", "finalize_success", "finalize_failure"))
def test_outbox_adapters_translate_checkout_pressure_to_the_port(monkeypatch, adapter, operation):
    from app.runtime.graph_projection.sqlalchemy_outbox import SqlAlchemyProjectionOutbox, SqliteProjectionOutbox
    failure = PoolCheckoutTimeout("synthetic canonical capacity")
    def unavailable(*args, **kwargs):
        raise failure
    engine = create_engine("sqlite://")
    monkeypatch.setattr(engine, "connect", unavailable)
    outbox = SqlAlchemyProjectionOutbox(unavailable) if adapter == "sqlalchemy" else SqliteProjectionOutbox(engine)
    arguments = {"worker_id": "port-worker", "now": datetime.now(UTC)}
    if operation == "claim":
        arguments["batch_size"] = 1
    elif operation == "load_command":
        arguments = {"outbox_id": "owned-outbox"}
    else:
        arguments["outbox_id"] = "owned-outbox"
        if operation == "finalize_failure":
            arguments.update(error_class="synthetic", terminal=False)
    reason = "canonical_write_capacity" if adapter == "sqlite" and operation != "load_command" else "canonical_checkout_timeout"
    with pytest.raises(OutboxCapacityError, match=reason) as caught:
        getattr(outbox, operation)(**arguments)
    if adapter == "sqlite" and operation != "load_command":
        from app.exceptions import SqliteTaskQueueFull
        assert isinstance(caught.value.__cause__, SqliteTaskQueueFull)
        assert caught.value.__cause__.__cause__ is failure
    else:
        assert caught.value.__cause__ is failure
    engine.dispose()


def test_outbox_adapter_does_not_disguise_other_failures_as_capacity():
    from app.runtime.graph_projection.sqlalchemy_outbox import SqlAlchemyProjectionOutbox
    def unavailable():
        raise ValueError("synthetic different failure")
    with pytest.raises(ValueError, match="different failure"):
        SqlAlchemyProjectionOutbox(unavailable).claim(worker_id="port-worker", now=datetime.now(UTC), batch_size=1)
