import asyncio
import threading
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from postgresql.test_activity_transactions import store
from postgresql.test_scheduler_transactions import repository
from app.runtime.resident.db_stage import run_slot_db_stage
from app.runtime.resident import execution
from app.domains.routines.schemas import ResidentSlotTickCreate
from app.runtime.persistence.scheduler_fence import scheduler_fence
from app.contracts.activity_cancellation import cancellation_scope, CancellationIntent, CancellationReason
from app.domains.routines.models import AgentSlot


@pytest.mark.parametrize('superseded', [False, True])
def test_cancelled_preparation_releases_only_exact_pending_claim_and_drains_cleanup(store, superseded, monkeypatch):
    engine, _, _ = store
    repo = repository(engine)
    proof = repo.acquire(owner_id='cancel-owner', ttl_seconds=45)
    due = datetime.now(UTC) - timedelta(minutes=1)
    with Session(engine) as db:
        db.add(AgentSlot(agent_id='pending-test', status='assigned_idle', next_tick_at=due))
        db.commit()
    entered, release_prepare = threading.Event(), threading.Event()
    cleanup_entered, release_cleanup = threading.Event(), threading.Event()
    async def wait_for(event):
        for _ in range(200):
            if event.is_set(): return
            await asyncio.sleep(.01)
        raise AssertionError('worker did not enter bounded stage')
    async def scenario():
        with Session(engine) as source:
            def prepare(db, data):
                slot = db.get(AgentSlot, 'pending-test')
                slot.status = 'running'
                slot.locked_by_run_id = 'pending:pending-test:1'
                slot.lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
                db.commit()
                entered.set()
                assert release_prepare.wait(5)
                return 1, [('pending-test','pending:pending-test:1')]
            original_cleanup = execution._release_prepared_slot_claims
            def cleanup(db, value):
                cleanup_entered.set()
                assert release_cleanup.wait(5)
                original_cleanup(db, value)
            monkeypatch.setattr(execution, '_prepare_resident_tick', prepare)
            monkeypatch.setattr(execution, '_release_prepared_slot_claims', cleanup)
            intent = CancellationIntent(CancellationReason.SHUTDOWN)
            with cancellation_scope(intent), scheduler_fence(owner_id='cancel-owner', fencing_epoch=proof.fencing_epoch):
                task=asyncio.create_task(execution.tick_resident_slots(source,ResidentSlotTickCreate(max_runs=1)))
                try:
                    await wait_for(entered)
                    if superseded:
                        with Session(engine) as other:
                            other.execute(update(AgentSlot).where(AgentSlot.agent_id=='pending-test').values(locked_by_run_id='actual-started-run'))
                            other.commit()
                    task.cancel()
                    await asyncio.sleep(.02)
                    release_prepare.set()
                    await wait_for(cleanup_entered)
                    task.cancel()
                    await asyncio.sleep(.02)
                    assert not task.done()
                finally:
                    release_prepare.set(); release_cleanup.set()
                with pytest.raises(asyncio.CancelledError): await task
        assert engine.pool.checkedout()==0
    asyncio.run(scenario())
    with Session(engine) as check:
        row=check.get(AgentSlot,'pending-test')
        assert row.next_tick_at==due and row.last_run_at is None
        assert row.status==('running' if superseded else 'assigned_idle')
        assert row.locked_by_run_id==('actual-started-run' if superseded else None)
        if not superseded:
            assert row.lease_expires_at is None and row.last_error=='runtime_shutdown'
