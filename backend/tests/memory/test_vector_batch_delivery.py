"""Real canonical SQLite, synthetic provider and durable projection delivery."""
import asyncio
from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from app.core.result_journal import ResultJournalError
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence
from app.domains.memory.repository.vector_eligibility import register_content
from app.providers.contracts import MeasuredEmbeddingResponse, MeasuredEmbeddingBatchResponse, ProviderUsage
from app.runtime.memory.vector_projection import MemoryVectorProjection
from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.test_vector_projection_lifecycle import setup_projection_scope
from memory.projection_fixture import index, A


def populate(factory, monkeypatch, count):
    first, _ = setup_projection_scope(factory, monkeypatch)
    identifiers = [first]
    with factory() as db:
        original = db.get(MemoryItem, first)
        evidence = list(db.scalars(select(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id == first)))
        for n in range(1, count):
            values = {column.key: getattr(original, column.key) for column in MemoryItem.__table__.columns}
            values.update(id=f"batch-item-{n:03}", summary=f"{original.summary} {n}")
            row = MemoryItem(**values)
            db.add(row); db.flush()
            for j, source in enumerate(evidence):
                props = {column.key: getattr(source, column.key) for column in MemoryItemEvidence.__table__.columns}
                props.update(id=f"batch-evidence-{n}-{j}", memory_item_id=row.id)
                db.add(MemoryItemEvidence(**props))
            register_content(db, row, now=datetime.now(UTC))
            identifiers.append(row.id)
        db.commit()
    return tuple(identifiers)


class Provider:
    def __init__(self, on_response=lambda: None):
        self.calls = []
        self.on_response = on_response

    async def embed_measured(self, request, *, timeout_seconds):
        self.calls.append((request.text,))
        self.on_response()
        return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)

    async def embed_batch_measured(self, request, *, timeout_seconds):
        self.calls.append(request.texts)
        self.on_response()
        return MeasuredEmbeddingBatchResponse(tuple(tuple(A) for _ in request.texts), ProviderUsage(), 1)


@pytest.mark.parametrize("count,expected", [(0, []), (1, [1]), (10, [10]), (20, [20]), (21, [20, 1])])
def test_pending_only_requests_and_current_vectors_do_not_call_provider(runtime_factory, index, monkeypatch, count, expected):
    ids = populate(runtime_factory, monkeypatch, max(1, count))[:count]
    provider = Provider()
    projection = MemoryVectorProjection(runtime_factory, index, provider=provider)
    async def run():
        assert set((await projection.sync_items(ids)).values()) <= {"indexed"}
        assert set((await projection.sync_items(ids)).values()) <= {"current"}
        await projection.stop()
    asyncio.run(run())
    assert [len(call) for call in provider.calls] == expected
    assert projection.logical_calls == projection.physical_attempts == len(expected)
    assert all(index.identity(f"memory-item:{item}") is not None for item in ids)


def test_received_batch_survives_busy_and_restart_without_additional_provider_calls(runtime_factory, index, monkeypatch):
    ids = populate(runtime_factory, monkeypatch, 10)
    engine = runtime_factory.kw["bind"]
    with engine.connect() as db:
        db.exec_driver_sql("PRAGMA journal_mode=WAL")
    held = []
    def busy():
        db = engine.connect(); db.exec_driver_sql("BEGIN IMMEDIATE"); held.append(db)
    provider = Provider(busy)
    first = MemoryVectorProjection(runtime_factory, index, provider=provider)
    async def receive():
        assert set((await first.sync_items(ids)).values()) == {"local_result_pending"}
        await first.stop()
    asyncio.run(receive())
    assert len(provider.calls) == 1
    held[0].rollback(); held[0].close()
    second = MemoryVectorProjection(runtime_factory, index, provider=provider)
    async def restore():
        assert set((await second.sync_items(ids)).values()) == {"indexed"}
        await second.stop()
    asyncio.run(restore())
    assert len(provider.calls) == 1


def test_individual_privacy_erasure_prevents_late_journal_publication(tmp_path):
    from app.core.result_journal import ResultJournal
    journal = ResultJournal(tmp_path, "memory-embedding")
    journal.write("w", "item", {"vector": A})
    journal.close_item("item")
    with pytest.raises(ResultJournalError, match="item_closed"):
        journal.write("w", "item", {"vector": A})
    assert journal.read("w", "item") is None
    journal.write("w", "unrelated", {"vector": A})
    assert journal.read("w", "unrelated") is not None


def test_single_only_adapter_and_other_writer_progress(runtime_factory, index, monkeypatch):
    ids = populate(runtime_factory, monkeypatch, 3)
    writes = []
    class SingleProvider:
        async def embed_measured(self, request, *, timeout_seconds):
            # A real competing writer can enter while the HTTP coroutine owns
            # no canonical connection. A batch method is intentionally absent.
            with runtime_factory.kw["bind"].connect() as db:
                db.exec_driver_sql("PRAGMA busy_timeout=0")
                db.exec_driver_sql("BEGIN IMMEDIATE")
                db.exec_driver_sql("UPDATE memory_items SET salience=salience WHERE id=:id", {"id": ids[0]})
                db.commit()
            writes.append(request.text)
            return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)
    projection = MemoryVectorProjection(runtime_factory, index, provider=SingleProvider())
    async def run():
        assert set((await projection.sync_items(ids)).values()) == {"indexed"}
        await projection.stop()
    asyncio.run(run())
    assert len(writes) == projection.physical_attempts == 3


def test_privacy_fence_without_any_retained_vector_generation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.runtime.memory.hybrid_runtime import MemoryHybridRuntime
    from app.runtime.received_results import result_journal
    monkeypatch.setattr("app.config.settings.MEDIA_ROOT", str(tmp_path))
    journal = result_journal("memory-embedding")
    journal.write("w", "orphan", {"vector": A})
    runtime = object.__new__(MemoryHybridRuntime)
    runtime._generations = SimpleNamespace(root=tmp_path / "absent")
    runtime.erase_items(("orphan",))
    assert journal.read("w", "orphan") is None
    with pytest.raises(ResultJournalError, match="item_closed"):
        journal.write("w", "orphan", {"vector": A})


def test_corrupt_receipt_does_not_resubmit_or_starve_other_items(runtime_factory, index, monkeypatch):
    ids = populate(runtime_factory, monkeypatch, 2)
    provider = Provider()
    projection = MemoryVectorProjection(runtime_factory, index, provider=provider)
    with runtime_factory() as db:
        world = db.get(MemoryItem, ids[0]).world_id
    projection.journal.write(world, ids[0], {"vector": A})
    path = projection.journal.root/projection.journal._key(world)/(projection.journal._key(ids[0])+".json")
    path.write_text("corrupt")
    async def run():
        outcomes = await projection.sync_items(ids)
        assert outcomes == {ids[0]: "local_result_invalid", ids[1]: "indexed"}
        await projection.stop()
    asyncio.run(run())
    assert len(provider.calls) == 1 and len(provider.calls[0]) == 1


def test_projection_admission_busy_does_not_spend_batch_attempts(runtime_factory, index, monkeypatch):
    ids = populate(runtime_factory, monkeypatch, 2)
    provider = Provider()
    projection = MemoryVectorProjection(runtime_factory, index, provider=provider)
    projection._prepare_attempts()
    async def run():
        with index._connect() as held:
            held.execute("BEGIN IMMEDIATE")
            assert set((await projection.sync_items(ids)).values()) == {"deferred"}
            assert held.execute("SELECT count(*) FROM embedding_attempts_v2").fetchone()[0] == 0
            assert provider.calls == []
            held.rollback()
        assert set((await projection.sync_items(ids)).values()) == {"indexed"}
        await projection.stop()
    asyncio.run(run())
    assert len(provider.calls) == 1
