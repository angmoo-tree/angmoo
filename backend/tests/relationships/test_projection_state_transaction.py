from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.models import Base
from app.domains.relationships.service import projection_state
from p7_graph_support import seed_projection_fixture


def test_sqlalchemy_lease_and_retry_remain_in_the_caller_transaction(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'projection.sqlite3'}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db)
        original_attempts = fixture.outbox.attempt_count
        assert projection_state.claim_batch(db, worker_id="owner", now=now, batch_size=1) == [fixture.outbox.id]
        assert fixture.outbox.lease_owner == "owner"
        assert fixture.outbox.attempt_count == original_attempts + 1
        with Session(engine) as observer:
            original = observer.get(models.GraphProjectionOutbox, fixture.outbox.id)
            assert original.status == "pending"
            assert original.attempt_count == original_attempts
        assert projection_state.finalize_failure(
            db, outbox_id=fixture.outbox.id, worker_id="stale-owner", now=now,
            error_class="temporary", terminal=False,
        ) == "lease_lost"
        assert fixture.outbox.status == "processing"
        assert fixture.outbox.lease_owner == "owner"
        assert projection_state.finalize_failure(
            db, outbox_id=fixture.outbox.id, worker_id="owner", now=now,
            error_class="temporary", terminal=False,
        ) == "pending"
        assert fixture.outbox.next_attempt_at == now + timedelta(seconds=5)
        assert fixture.outbox.lease_owner is None
        assert fixture.outbox.completed_at is None
        db.rollback()
        assert fixture.outbox.status == "pending"
        assert fixture.outbox.attempt_count == original_attempts
        assert fixture.outbox.next_attempt_at is None
        assert fixture.outbox.last_error_class is None
    engine.dispose()
