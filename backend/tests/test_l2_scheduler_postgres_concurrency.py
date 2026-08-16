from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import os

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.domains.runtime.public import (
    SchedulerLeaseHeldError,
    SqlAlchemySchedulerLeaseRepository,
)


DATABASE_URL = os.getenv("L2_SCHEDULER_POSTGRES_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="L2_SCHEDULER_POSTGRES_DATABASE_URL is required",
)


def test_two_scheduler_claims_have_exactly_one_active_owner() -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with Session(engine) as db:
        db.execute(delete(models.RuntimeSchedulerLease))
        db.commit()

    def claim(owner_id: str):
        repository = SqlAlchemySchedulerLeaseRepository(factory)
        try:
            return repository.acquire(owner_id=owner_id, ttl_seconds=30)
        except SchedulerLeaseHeldError:
            return None

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(claim, ("scheduler-a", "scheduler-b")))
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        assert winners[0].fencing_epoch == 1

        with Session(engine) as db:
            row = db.get(models.RuntimeSchedulerLease, "resident-tick-scheduler")
            assert row is not None
            row.lease_expires_at = datetime(2000, 1, 1, tzinfo=UTC)
            db.commit()
        takeover = claim("scheduler-c")
        assert takeover is not None
        assert takeover.fencing_epoch == 2
    finally:
        with Session(engine) as db:
            db.execute(delete(models.RuntimeSchedulerLease))
            db.commit()
        engine.dispose()
