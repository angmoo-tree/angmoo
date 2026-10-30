"""Real isolated PG rollback/retry and no repeated external review requests."""
import time
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session, sessionmaker

from postgresql.test_activity_transactions import store, execute
from app.core.database_transactions import database_write, POSTGRES_UNIT_RETRY
from app.core.postgresql_concurrency import PostgresDeadlineExceeded, PostgresCommitOutcomeUnknown
from app.core.sqlite_concurrency import is_sqlite_contention
from app.core.result_journal import ResultJournal
from app.domains.memory.models.items import MemoryItem
from app.domains.relationships.models.personalization import RelationshipReviewWork
from app.domains.relationships.service.daily_review import plan_review, run_review_step
from app.runtime.world_deletion.worker import WorldDeletionWorker
from p7_graph_support import seed_projection_fixture
from test_relationship_daily_review import References, Provider


def test_empty_deletion_poll_tolerates_phone_latency_but_deadline_aborts(store, monkeypatch):
    engine, _, _ = store
    sessions = sessionmaker(engine, expire_on_commit=False)
    worker = WorldDeletionWorker(sessions, SimpleNamespace())
    def slow_read(connection, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT world_deletion_requests."):
            time.sleep(.3)
    event.listen(engine, "before_cursor_execute", slow_read)
    try:
        assert worker._claim() is None  # Old 250ms budget failed even with no request.
        import app.runtime.world_deletion.worker as module
        def short(db, operation, **kwargs):
            return database_write(db, operation, retry_policy=replace(POSTGRES_UNIT_RETRY, maximum_elapsed_seconds=.1), **kwargs)
        monkeypatch.setattr(module, "database_write", short)
        assert worker.tick() is False  # Deferred, not fatal or a deletion side effect.
    finally:
        event.remove(engine, "before_cursor_execute", slow_read)
        worker._work.close()


def test_deadline_rolls_back_changes_and_reports_phase_without_secrets(store):
    engine, _, _ = store
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE deadline_counter (value integer NOT NULL)"))
        connection.execute(text("INSERT INTO deadline_counter VALUES (0)"))
    events = []
    with Session(engine) as db:
        def write():
            db.execute(text("UPDATE deadline_counter SET value=1"))
            time.sleep(.08)
        with pytest.raises(PostgresDeadlineExceeded) as error:
            database_write(db, write, retry_policy=replace(POSTGRES_UNIT_RETRY, maximum_elapsed_seconds=.05), observer=events.append)
        assert is_sqlite_contention(error.value)
        assert not is_sqlite_contention(PostgresCommitOutcomeUnknown("private payload"))
        assert db.scalar(text("SELECT value FROM deadline_counter")) == 0
        terminal = [e for e in events if e['result']=='deadline_exhausted']
        assert len(terminal)==1 and terminal[0]['phase']=='operation'
        assert terminal[0]['elapsed_ms'] >= 50


@pytest.mark.parametrize('fault', ['deadline', 'serialization'])
def test_received_relationship_result_retries_storage_without_second_provider(store, monkeypatch, fault):
    engine, _, root = store
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as db:
        fixture = seed_projection_fixture(db, suffix='pg-review')
        item = MemoryItem(id='review-source',owner_id=fixture.owner.id,world_id=fixture.world.id,
            subject_world_character_id=fixture.actor_world_character.id,memory_kind='AUTOBIOGRAPHICAL_EVENT',
            summary='Saved experience',confidence=1,salience=1)
        db.add(item); db.flush()
        row = plan_review(db,world_id=fixture.world.id,actor_id=fixture.actor_world_character.id,
            target_id=fixture.target_world_character.id,period_key='2026-10-27',base={},
            memories=[dict(memory_id=item.id,summary=item.summary,digest='a'*64,source_refs=[],occurred_at=datetime.now(UTC).isoformat())])
        db.commit()
        identifier, world_id = row.id, fixture.world.id
    provider, received = Provider(), {}
    journal = ResultJournal(root/'received-results', 'relationship-review')
    import app.domains.relationships.service.review_delivery as delivery
    def short(db, operation, **kwargs):
        return database_write(db,operation,retry_policy=replace(POSTGRES_UNIT_RETRY,maximum_elapsed_seconds=.1),**kwargs)
    if fault=='deadline':monkeypatch.setattr(delivery,'database_write',short)
    injected=[]
    def interrupt(connection,cursor,statement,parameters,context,many):
        if injected or not (statement.startswith('UPDATE relationship_review_work SET ') and 'result=' in statement):
            return
        injected.append(True)
        if fault=='deadline':
            time.sleep(.15)
        else:
            # A real concurrent commit after the receipt was read causes 40001.
            with engine.begin() as other:
                other.execute(text("UPDATE relationship_review_work SET created_at=created_at+interval '1 second' WHERE id=:id"), {'id':identifier})
    event.listen(engine,'before_cursor_execute',interrupt)
    def run():
        return execute(run_review_step(sessions,work_id=identifier,references_factory=lambda db:References(),
            provider_factory=lambda base:provider,journal=journal,received=received))
    try:
        assert run()==('storage_retry_wait' if fault=='deadline' else 'ready')
    finally:event.remove(engine,'before_cursor_execute',interrupt)
    assert injected and len(provider.calls)==1
    if fault=='deadline':
        with sessions() as db:
            waiting=db.get(RelationshipReviewWork,identifier)
            assert waiting.error_code=='relationship_storage_retry_wait'
            assert waiting.maintenance['storage_rounds']==1 and waiting.next_attempt_at is not None
        assert journal.read(world_id,identifier) is not None
    monkeypatch.setattr(delivery,'database_write',database_write)
    assert run()=='ready'
    assert len(provider.calls)==1 and not received and journal.read(world_id,identifier) is None
    with sessions() as db:
        row=db.get(RelationshipReviewWork,identifier)
        assert row.status=='ready' and row.attempts==1


@pytest.mark.parametrize('boundary', ['routine_rejected', 'world_rejected', 'world_cancelled'])
def test_rejected_manual_request_releases_admission_before_async_teardown(store, boundary):
    import asyncio
    from app.domains.identity.models import InstallationIdentity
    from app.domains.routines.exceptions import RunNowCooldownError
    from app.domains.routines.service.manual_activity import run_agent_now
    from app.runtime.world_characters.manual_activity import run_world_character_now

    engine, _, _ = store
    with Session(engine) as db:
        fixture = seed_projection_fixture(db, suffix='admission-release')
        owner = SimpleNamespace(id=fixture.owner.id)
        db.add(InstallationIdentity(singleton_key='local-installation', installation_id='admission-test',
            owner_user_id=owner.id, bootstrap_state='claimed', claimed_at=datetime.now(UTC)))
        db.commit()

    error = asyncio.CancelledError() if boundary == 'world_cancelled' else RunNowCooldownError(datetime.now(UTC))
    def reject(*args, **kwargs):
        raise error

    async def exercise():
        # Keep the first request session open, as FastAPI does until its
        # asynchronous dependency teardown. The second request must not wait.
        with Session(engine) as first:
            if boundary == 'routine_rejected':
                with pytest.raises(type(error)):
                    await run_agent_now(first, owner, 'actor', workflows=SimpleNamespace(get_owned_character=reject))
            else:
                service = SimpleNamespace(db=first, _owned_role=reject)
                with pytest.raises(type(error)):
                    await run_world_character_now(service, world_id='world', world_character_id='actor',
                        user=owner, data=SimpleNamespace(expected_revision=1), workflows=None)
            assert not first.in_transaction()
            with Session(engine) as second:
                assert second.scalar(select(InstallationIdentity.installation_id).with_for_update(nowait=True)) == 'admission-test'
    execute(exercise())
