"""Durable mutation/lease/snapshot invariants using isolated real SQLite files."""
import asyncio
from datetime import UTC, datetime, timedelta
from time import time
import threading
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import event, select, text
from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.projection_fixture import index, A
from memory.test_vector_projection_lifecycle import setup_projection_scope
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.vector_work import MemoryVectorWork, MemoryVectorChange, MemoryVectorMaintenance
from app.domains.memory.repository import vector_queue as queue
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.runtime.memory.vector_delivery import prepare, persist, PreparedVector
from app.runtime.memory.vector_changes import expand_page
from app.providers.contracts import MeasuredEmbeddingResponse, ProviderUsage


class Provider:
    calls = 0
    async def embed_measured(self, request, *, timeout_seconds):
        self.calls += 1
        return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)


def counts(factory):
    with factory() as session:
        return tuple(session.execute(text("SELECT count(*),coalesce(max(sequence),0) FROM memory_vector_changes")).one())


def test_atomic_bulk_noop_rollback_and_epoch_without_self_events(runtime_factory, monkeypatch):
    item_id, _ = setup_projection_scope(runtime_factory, monkeypatch)
    before = counts(runtime_factory)
    with runtime_factory() as session:
        session.execute(text("UPDATE memory_items SET version=version WHERE id=:id"), {"id": item_id})
        session.commit()
    assert counts(runtime_factory) == before
    with runtime_factory() as session:
        session.execute(text("UPDATE memory_items SET version=version+1 WHERE id=:id"), {"id": item_id})
        assert session.scalar(select(MemoryVectorChange.sequence).order_by(MemoryVectorChange.sequence.desc()).limit(1)) > before[1]
        session.rollback()
    assert counts(runtime_factory) == before
    with runtime_factory() as session:
        session.execute(text("UPDATE memory_items SET version=version+1 WHERE id=:id"), {"id": item_id})
        session.commit()
    assert counts(runtime_factory)[1] > before[1]
    before = counts(runtime_factory)
    with runtime_factory() as session:
        queue.enqueue(session, "v1", item_id, "recall-world")
        session.commit()
    assert counts(runtime_factory) == before


def test_claim_lease_reclaim_duplicate_and_stale_ack(runtime_factory):
    with runtime_factory() as session:
        queue.enqueue(session, "v1", "test", "world", change=1)
        first = queue.claim(session, "v1", ("test",), now=time())[0]
        assert not queue.claim(session, "v1", ("test",))
        session.commit()
    with runtime_factory() as session:
        queue.enqueue(session, "v1", "test", "world", change=1)
        assert queue.owns(session, first)
        queue.enqueue(session, "v1", "test", "world", change=2)
        assert not queue.finish(session, first, "indexed")
        second = queue.claim(session, "v1", ("test",))[0]
        session.commit()
    with runtime_factory() as session:
        session.get(MemoryVectorWork, ("v1", "test")).due_at = 0
        session.get(MemoryVectorWork, ("v1", "test")).lease_until = 0
        third = queue.claim(session, "v1", ("test",))[0]
        assert not queue.finish(session, second, "indexed")
        assert queue.finish(session, third, "current")
        session.commit()
        assert queue.due_ids(session, "v1") == ()
        row = session.get(MemoryVectorWork, ("v1", "test"))
        assert row.applied_revision == row.desired_revision == 2


def test_idle_2112_completed_rows_never_hydrates_or_writes(runtime_factory, index, monkeypatch):
    item_id, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    assert asyncio.run(projection.sync_item(item_id)) == "indexed"
    with runtime_factory() as session:
        session.execute(text("DELETE FROM memory_vector_changes"))
        session.add(MemoryVectorMaintenance(generation="v1", phase="ready", due_at=time()+86400))
        session.add_all(MemoryVectorWork(generation="v1", item_id=f"completed-{i}", world_id="recall-world",
            state="done", desired_revision=1, applied_revision=1) for i in range(2112))
        session.commit()
    calls = []
    def record(conn, cursor, statement, params, context, many):
        calls.append(statement)
    engine = runtime_factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", record)
    monkeypatch.setattr(projection._source, "documents_for_item_ids", lambda *a, **k: (_ for _ in ()).throw(AssertionError("idle source validation")))
    try:
        for _ in range(3):
            asyncio.run(projection.tick())
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert not any(sql.lstrip().upper().startswith(("BEGIN", "UPDATE", "INSERT", "DELETE")) for sql in calls)
    assert not any("FROM memory_vector_eligibility" in sql for sql in calls)
    assert projection._provider.calls == 1


def test_snapshot_preparation_allows_wal_writer_and_rejects_changed_proof(runtime_factory, index, monkeypatch):
    item_id, _ = setup_projection_scope(runtime_factory, monkeypatch)
    engine = runtime_factory.kw["bind"]
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    entered, release = threading.Event(), threading.Event()
    original = projection._source.documents_for_item_ids
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(projection._source, "documents_for_item_ids", slow)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(prepare, projection, item_id, (), None)
        assert entered.wait(10)
        try:
            from app.core.sqlite_concurrency import run_sqlite_session_immediate
            with runtime_factory() as session:
                def delete():
                    row = session.get(MemoryItem, item_id)
                    row.status, row.deleted_at = "deleted", datetime.now(UTC)
                run_sqlite_session_immediate(session, delete, require_clean=True)
        finally:
            release.set()
        assert future.result() == "changed"
    assert index.identity(f"memory-item:{item_id}") is None
    assert projection._provider.calls == 0


def test_expiry_reschedules_without_a_new_mutation(runtime_factory, index, monkeypatch):
    item_id, _ = setup_projection_scope(runtime_factory, monkeypatch)
    with runtime_factory() as session:
        row = session.get(MemoryItem, item_id)
        row.valid_until = datetime.now(UTC) + timedelta(hours=1)
        session.commit()
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    prepared = prepare(projection, item_id, (), None)
    assert isinstance(prepared, PreparedVector)
    with runtime_factory() as session:
        queue.enqueue(session, "v1", item_id, "recall-world")
        claim = queue.claim(session, "v1", (item_id,))[0]
        assert queue.finish(session, claim, "indexed", next_boundary=prepared.proof.next_boundary)
        session.commit()
        assert queue.due_ids(session, "v1") == ()
        assert queue.due_ids(session, "v1", now=prepared.proof.next_boundary+1) == (item_id,)


def test_source_event_wakes_restart_and_frontier_cycle_terminates(runtime_factory, index, monkeypatch):
    item_id, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    assert asyncio.run(projection.sync_item(item_id)) == "indexed"
    with runtime_factory() as session:
        session.execute(text("DELETE FROM memory_vector_changes"))
        session.execute(text("INSERT OR IGNORE INTO memory_vector_dependencies VALUES (:id,'memory',:id)"), {"id": item_id})
        session.execute(text("UPDATE memory_items SET version=version+1 WHERE id=:id"), {"id": item_id})
        session.commit()
    restarted = MemoryVectorProjection(runtime_factory, index, provider=projection._provider)
    for _ in range(10):
        if not expand_page(restarted):
            break
    else:
        raise AssertionError("frontier cycle did not drain")
    with runtime_factory() as session:
        assert queue.due_ids(session, "v1") == (item_id,)
    asyncio.run(restarted.tick())
    assert restarted._provider.calls == 1
    with runtime_factory() as session:
        row = session.get(MemoryVectorWork, ("v1", item_id))
        assert row.state in {"done", "scheduled"}
        assert row.applied_revision == row.desired_revision


def test_after_commit_hint_works_with_bound_connection_and_detaches(runtime_factory, index, monkeypatch):
    from app.runtime.memory.vector_wakeup import VectorWakeup
    from app.core.sqlite_concurrency import run_sqlite_session_immediate
    item_id, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    async def exercise():
        listener = VectorWakeup(projection, asyncio.get_running_loop())
        try:
            with runtime_factory() as session:
                def write():
                    session.get(MemoryItem, item_id).version += 1
                run_sqlite_session_immediate(session, write, require_clean=True)
            await asyncio.sleep(0)
            assert projection._wake.is_set()
            projection._wake.clear()
            with runtime_factory() as session:
                session.get(MemoryItem, item_id).version += 1
                session.flush()
                session.rollback()
            await asyncio.sleep(0)
            assert not projection._wake.is_set()
        finally:
            listener.close()
        from sqlalchemy.orm import Session
        assert all(not event.contains(Session, name, callback) for name, callback in listener.listeners)
    asyncio.run(exercise())
