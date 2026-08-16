from __future__ import annotations

from datetime import UTC, datetime, timedelta
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.integrations.neo4j import GraphClientError
from app.services.graph_projection_worker import GraphProjectionWorker
from p7_graph_support import seed_projection_fixture, sqlite_engine


class RecordingStore:
    def __init__(self, *, failure: str | None = None) -> None:
        self.failure = failure
        self.commands = []

    def apply(self, command, *, timeout_seconds: float = 5.0) -> str:
        self.commands.append(command)
        if self.failure:
            raise GraphClientError(self.failure)
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
    failing = RecordingStore(failure="neo4j_unavailable")
    result = GraphProjectionWorker(
        session_factory=_session_factory(engine), store=failing, worker_id="worker-a"
    ).process_batch()
    with Session(engine) as db:
        row = db.get(models.GraphProjectionOutbox, outbox_id)
        assert row is not None
        assert row.status == "pending"
        assert row.next_attempt_at is not None
        assert row.last_error_class == "neo4j_unavailable"
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
        raise GraphClientError("neo4j_unavailable")

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
