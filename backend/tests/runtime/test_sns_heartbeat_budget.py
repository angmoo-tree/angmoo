import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.exceptions import SqliteBusyRetryExhausted
from app.runtime.resident import scheduler
from app.runtime.resident.lease_executor import SchedulerLeaseExecutor


@pytest.mark.parametrize("failures,expiry,calls", [(1, 45, 2), (2, 45, 3), (3, 45, 3), (1, 20, 1)])
def test_only_busy_retries_with_committed_expiry_margin(failures, expiry, calls):
    config = SimpleNamespace(RESIDENT_TICK_READY_PATH="test-budget", resident_tick_shutdown_drain_seconds=20)
    snapshot = SimpleNamespace(lease_owner_id="owner", fencing_epoch=3, lease_expires_at=datetime.now(UTC) + timedelta(seconds=expiry))
    scheduler._record_proof(config, snapshot)
    class Coordinator:
        count = 0
        def heartbeat(self, **kwargs):
            self.count += 1
            assert kwargs == {"owner_id": "owner", "fencing_epoch": 3}
            if self.count <= failures:
                raise SqliteBusyRetryExhausted("test_busy")
            return snapshot
    owner = Coordinator()
    async def run():
        if failures >= calls:
            with pytest.raises(SqliteBusyRetryExhausted):
                await scheduler._heartbeat_with_budget(owner, owner_id="owner", fencing_epoch=3, config=config)
        else:
            assert await scheduler._heartbeat_with_budget(owner, owner_id="owner", fencing_epoch=3, config=config) is snapshot
    try:
        asyncio.run(run())
        assert owner.count == calls
    finally:
        scheduler._clear_proof(config)


def test_real_sqlite_busy_release_recovers_same_epoch(tmp_path):
    import sqlite3
    from threading import Timer
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from model_fixture_support import models
    from app.runtime.persistence.sqlite_scheduler_lease import SqliteSchedulerLeaseRepository
    from app.domains.runtime.service.lease_coordinator import SchedulerLeaseCoordinator
    path = tmp_path / "lease.sqlite"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 0.01})
    for model in (models.User, models.InstallationIdentity, models.RuntimeSchedulerLease):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(models.InstallationIdentity(singleton_key="local-installation", installation_id="busy-budget", bootstrap_state="unclaimed"))
        db.commit()
    coordinator = SchedulerLeaseCoordinator(SqliteSchedulerLeaseRepository(engine), ttl_seconds=45, interval_seconds=60)
    proof = coordinator.acquire(owner_id="owner")
    config = SimpleNamespace(RESIDENT_TICK_READY_PATH="test-real-budget", resident_tick_shutdown_drain_seconds=20)
    scheduler._record_proof(config, proof)
    writer = sqlite3.connect(path, check_same_thread=False)
    writer.execute("BEGIN IMMEDIATE")
    timer = Timer(0.32, writer.rollback)
    timer.start()
    async def run():
        executor = SchedulerLeaseExecutor(lambda: coordinator)
        try:
            result = await scheduler._heartbeat_with_budget(executor, owner_id="owner", fencing_epoch=proof.fencing_epoch, config=config)
            assert result.fencing_epoch == proof.fencing_epoch
            assert result.lease_expires_at >= proof.lease_expires_at
        finally:
            assert await executor.drain(20)
            executor.close()
    try:
        asyncio.run(run())
    finally:
        timer.join()
        writer.close()
        engine.dispose()
        scheduler._clear_proof(config)
