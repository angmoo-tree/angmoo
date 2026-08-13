from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
    assert recovery.succeeded == 1


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
