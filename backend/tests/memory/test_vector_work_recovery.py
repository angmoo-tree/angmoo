"""Failure windows, finite repair, and privacy with durable intent."""
import asyncio
from datetime import UTC, datetime
from time import time

from sqlalchemy import select, text, update

from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.projection_fixture import index, DurableIndex
from memory.test_vector_projection_lifecycle import setup_projection_scope
from memory.test_vector_pending_work import Provider
from app.domains.memory.models.items import MemoryItem
from app.domains.chat.models import MessageThread
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.vector_work import MemoryVectorMaintenance, MemoryVectorWork, MemoryVectorDependency
from app.domains.memory.repository import vector_queue as queue
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.runtime.memory.vector_queue_worker import audit_page, acknowledge
from app.runtime.memory.vector_changes import bootstrap_page, expand_page
from app.runtime.memory.vector_delivery import prepare, persist


def ready(factory, projection):
    with factory() as session:
        session.execute(text("DELETE FROM memory_vector_changes"))
        session.merge(MemoryVectorMaintenance(generation=projection.generation, phase="ready", cursor="", due_at=time()+86400))
        session.commit()


def test_vector_commit_before_budget_or_ack_failure_reuses_receipt(runtime_factory, index, monkeypatch):
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    provider = Provider()
    projection = MemoryVectorProjection(runtime_factory, index, provider=provider)
    monkeypatch.setattr(projection, "_finish_attempt", lambda *a, **k: (_ for _ in ()).throw(OSError("injected storage failure")))
    assert asyncio.run(projection.sync_item(item)) == "local_result_pending"
    assert index.identity(f"memory-item:{item}") is not None
    restarted = MemoryVectorProjection(runtime_factory, index, provider=provider)
    assert asyncio.run(restarted.sync_item(item)) == "indexed"
    assert provider.calls == 1
    # An older completion must never unlink a replacement receipt.
    prepared = prepare(restarted, item, (), None)
    old, new = {"receipt_id": "old"}, {"receipt_id": "new"}
    restarted.journal.write(prepared.work[0].world_id, item, old)
    restarted.journal.write(prepared.work[0].world_id, item, new)
    assert not restarted.journal.remove(prepared.work[0].world_id, item, expected_payload=old)
    assert restarted.journal.read(prepared.work[0].world_id, item) == new


def test_off_still_removes_revoked_source_from_all_retained_generations(runtime_factory, index, monkeypatch, tmp_path):
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    second = DurableIndex(tmp_path / "retained.sqlite3")
    second.generation = "g-" + "a" * 32
    provider = Provider()
    for target in (index, second):
        assert asyncio.run(MemoryVectorProjection(runtime_factory, target, provider=provider).sync_item(item)) == "indexed"
    with runtime_factory() as session:
        session.scalar(select(MemoryEmbeddingSetting)).enabled = False
        session.commit()
    projection = MemoryVectorProjection(runtime_factory, index, provider=provider, retained_indexes=lambda: (index, second))
    assert asyncio.run(projection.sync_item(item)) == "disabled"
    with runtime_factory() as session:
        session.execute(update(MessageThread).values(deleted_at=datetime.now(UTC)))
        session.commit()
    assert asyncio.run(projection.sync_item(item)) == "source_unavailable"
    assert all(target.identity(f"memory-item:{item}") is None for target in (index, second))
    assert provider.calls == 2


def test_audit_is_finite_noop_and_enqueues_missing_vector(runtime_factory, index, monkeypatch):
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    assert asyncio.run(projection.sync_item(item)) == "indexed"
    ready(runtime_factory, projection)
    with runtime_factory() as session:
        queue.enqueue(session, "v1", item, "recall-world")
        claim = queue.claim(session, "v1", (item,))[0]
        queue.finish(session, claim, "indexed")
        session.get(MemoryVectorMaintenance, "v1").due_at = 0
        session.commit()
    monkeypatch.setattr(projection._source, "documents_for_item_ids", lambda *a, **k: (_ for _ in ()).throw(AssertionError("audit hydrated sources")))
    assert audit_page(projection)
    assert audit_page(projection)
    assert not audit_page(projection)
    with runtime_factory() as session:
        assert queue.due_ids(session, "v1") == ()
        session.get(MemoryVectorMaintenance, "v1").due_at = 0
        session.commit()
    index.delete(f"memory-item:{item}")
    assert audit_page(projection)
    with runtime_factory() as session:
        assert queue.due_ids(session, "v1") == (item,)
    assert projection._provider.calls == 1


def test_promotion_resumes_after_sql_barrier_and_old_claim_is_retired(runtime_factory, index, monkeypatch):
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    assert asyncio.run(projection.sync_item(item)) == "indexed"
    with runtime_factory() as session:
        session.add(MemoryVectorMaintenance(generation="old", phase="ready"))
        queue.enqueue(session, "old", item, "recall-world")
        old = queue.claim(session, "old", (item,))[0]
        session.commit()
    bootstrap_page(projection)
    with runtime_factory() as session:
        assert not queue.owns(session, old)
    # Simulate committed completion then a process stop before pointer promotion.
    ready(runtime_factory, projection)
    with runtime_factory() as session:
        session.execute(text("DELETE FROM memory_vector_work WHERE generation='v1'"))
        session.commit()
    promoted = []
    projection._on_clean_cycle = lambda target: promoted.append(target.generation)
    asyncio.run(projection.tick())
    asyncio.run(projection.tick())
    assert promoted == ["v1"]
    with runtime_factory() as session:
        assert session.get(MemoryVectorWork, ("old", item)) is None


def test_deleted_item_cleans_intent_dependencies_and_budget(runtime_factory, index, monkeypatch):
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    assert asyncio.run(projection.sync_item(item)) == "indexed"
    with runtime_factory() as session:
        row = session.get(MemoryItem, item)
        row.status, row.deleted_at = "deleted", datetime.now(UTC)
        session.commit()
        queue.enqueue(session, "v1", item, "recall-world")
        claim = queue.claim(session, "v1", (item,))[0]
        session.commit()
    projection._claims[item] = claim
    assert asyncio.run(projection.sync_item(item)) == "ineligible"
    assert acknowledge(projection, claim, "ineligible")
    with runtime_factory() as session:
        assert session.get(MemoryVectorWork, ("v1", item)) is None
        assert session.scalar(select(MemoryVectorDependency).where(MemoryVectorDependency.item_id == item)) is None
    assert index.identity(f"memory-item:{item}") is None


def test_dependency_frontier_bounds_fanout_and_terminates_diamond_cycle(runtime_factory, index):
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    with runtime_factory() as session:
        session.execute(text("DELETE FROM memory_vector_changes"))
        session.add(MemoryVectorMaintenance(generation="v1", phase="ready"))
        for i in range(150):
            session.add(MemoryVectorDependency(item_id=f"item-{i:03}", source_kind="posts", source_key="shared"))
        session.add(MemoryVectorDependency(item_id="item-000", source_kind="memory", source_key="item-001"))
        session.add(MemoryVectorDependency(item_id="item-001", source_kind="memory", source_key="item-000"))
        session.execute(text("INSERT INTO memory_vector_changes(source_kind,source_key) VALUES ('posts','shared')"))
        session.commit()
    assert expand_page(projection)
    with runtime_factory() as session:
        assert session.execute(text("SELECT count(*) FROM memory_vector_work")).scalar_one() == 64
    for _ in range(160):
        if not expand_page(projection):
            break
    else:
        raise AssertionError("fanout did not terminate")
    with runtime_factory() as session:
        assert session.execute(text("SELECT count(*) FROM memory_vector_work")).scalar_one() == 150
        assert session.execute(text("SELECT max(desired_revision) FROM memory_vector_work")).scalar_one() == 1


def test_legacy_budgets_from_retained_generation_remain_terminal(runtime_factory, index, monkeypatch, tmp_path):
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    provider = Provider()
    old = MemoryVectorProjection(runtime_factory, index, provider=provider)
    prepared = prepare(old, item, (), None)
    old._prepare_attempts()
    with index._connect() as connection:
        connection.execute("INSERT INTO embedding_attempts_v2 VALUES (?,?,?,?,3,'terminal',0)",
            (f"memory-item:{item}", prepared.work[1].profile, prepared.work[2], prepared.attempt_revision))
        connection.commit()
    rebuilt = DurableIndex(tmp_path / "rebuild.sqlite3")
    rebuilt.generation = "g-" + "b" * 32
    projection = MemoryVectorProjection(runtime_factory, rebuilt, provider=provider, retained_indexes=lambda: (index, rebuilt))
    assert asyncio.run(projection.sync_item(item)) == "attempts_exhausted"
    # Removing the old file after its budget handoff must not reset that budget.
    restarted = MemoryVectorProjection(runtime_factory, rebuilt, provider=provider)
    assert asyncio.run(restarted.sync_item(item)) == "attempts_exhausted"
    assert provider.calls == 0


def test_world_erasure_admission_rejects_old_proof_and_new_paid_work(runtime_factory, index, monkeypatch):
    from app.domains.worlds.models_deletion import WorldDeletionRequest
    from memory.projection_fixture import A
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    prepared = prepare(projection, item, (), None)
    scope = prepared.work[0]
    with runtime_factory() as session:
        session.add(WorldDeletionRequest(id="erasure-request", world_id=scope.world_id, owner_id=scope.owner_id,
            idempotency_key="synthetic-request", confirmation_digest="0"*64))
        session.commit()
    receipt = {"binding": prepared.binding, "vector": A, "receipt_id": "late"}
    assert persist(projection, prepared, receipt) == "changed"
    assert asyncio.run(projection.sync_item(item)) == "world_closed"
    assert index.identity(f"memory-item:{item}") is None
    assert projection._provider.calls == 0
    bootstrap_page(projection)
    with runtime_factory() as session:
        assert session.get(MemoryVectorWork, ("v1", item)) is None


def test_bootstrap_checkpoint_does_not_enroll_history_or_lose_new_ids(runtime_factory, index, monkeypatch):
    from app.domains.memory.models.embedding import MemoryVectorEligibility
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    with runtime_factory() as session:
        original = session.get(MemoryItem, item)
        values = {column.name: getattr(original, column.name) for column in MemoryItem.__table__.columns}
        registration = session.get(MemoryVectorEligibility, item)
        eligibility = {column.name: getattr(registration, column.name) for column in MemoryVectorEligibility.__table__.columns}
        for number in range(130):
            identifier = f"seed-{number:03}"
            session.add(MemoryItem(**{**values, "id": identifier}))
            session.flush()
            session.add(MemoryVectorEligibility(**{**eligibility, "memory_item_id": identifier}))
        session.add(MemoryItem(**{**values, "id": "old-unregistered"}))
        session.commit()
        session.execute(text("DELETE FROM memory_vector_changes"))
        session.commit()
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    assert bootstrap_page(projection)
    with runtime_factory() as session:
        cursor = session.get(MemoryVectorMaintenance, "v1").cursor
        assert cursor and session.execute(text("SELECT count(*) FROM memory_vector_work")).scalar_one() == 64
        for identifier in ("000-new-before-cursor", "zzz-new-after-cutoff"):
            session.add(MemoryItem(**{**values, "id": identifier}))
            session.flush()
            session.add(MemoryVectorEligibility(**{**eligibility, "memory_item_id": identifier}))
        session.commit()
    restarted = MemoryVectorProjection(runtime_factory, index, provider=projection._provider)
    for _ in range(4):
        bootstrap_page(restarted)
    for _ in range(20):
        if not expand_page(restarted):
            break
    with runtime_factory() as session:
        identifiers = set(session.scalars(select(MemoryVectorWork.item_id)))
        assert len(identifiers) == 133
        assert "old-unregistered" not in identifiers
        assert {"000-new-before-cursor", "zzz-new-after-cutoff"} <= identifiers
        assert session.get(MemoryVectorMaintenance, "v1").phase == "settling"
    assert projection._provider.calls == 0
