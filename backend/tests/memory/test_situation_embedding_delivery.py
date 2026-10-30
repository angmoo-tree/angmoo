"""Manual admission -> per-receipt commits -> durable worker -> real SDK HTTP.

Only HTTP is mocked. Eager vector ticks after every producer commit reproduce
the former fragmentation even when all receipts were admitted together.
"""
import asyncio
import json
from datetime import UTC, datetime
from sqlalchemy import select, text
import pytest

from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_application import real_source
from memory.test_activity_situation_contract import values, NOW
from memory.test_embedding_batch_transport import transport
from memory.projection_fixture import index
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE, embedding_text
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.activity_situation import MemorySituationApplyRun
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run
from app.runtime.memory.situation_application_sources import PreparedSituationSources
from app.runtime.memory.batch_runtime import MemoryBatchRuntime
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.providers.gemini import GeminiAdapter
from dataclasses import replace


def seed_run(factory, count, *, length=0):
    with factory() as session:
        scope, setting, *_ = _stack(session)
        post = real_source(session, scope)
        get_or_create_settings(session, setting.id, timezone="UTC", now=NOW)
        session.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=True,
            provider="google", model="gemini-embedding-2", profile=EMBEDDING_PROFILE, version=1))
        world_credentials.save(session, owner_id=scope.owner_id, world_id=scope.world_id,
            world_character_id=scope.subject_world_character_id, purpose="embedding",
            data=WorldCredentialWrite(expected_revision=0, provider="google", model="gemini-embedding-2", api_key="synthetic"))
        for number in range(count):
            manifest, draft, result = values(session, scope, target=post.id,
                logical=f"activity-{number}", call=f"call-{number}")
            source = PreparedSituationSources(session).describe(scope, kind="POST", identifier=post.id,
                delivered=post.body, path="/target/body", role="core", ordinal=0, target=post.id)
            admit(session, manifest=replace(manifest, sources=(source,)),
                draft=replace(draft, description=f"Independent memory {number}. " + "🙂" * length), result=result, now=NOW)
        request = request_run(session, setting, trigger="manual", request_key="manual-embedding-group",
            expected_version=1, now=NOW)
        session.commit()
        session.execute(text("CREATE TABLE test_writer_turns (turn INTEGER PRIMARY KEY)"))
        session.commit()
        return request.run_id


async def drive(factory, projection, run_id, monkeypatch):
    runtime = MemoryBatchRuntime(factory, lambda: None, generation_policy="activity_situation")
    call = runtime._canonical.call
    pages, briefs = [], []
    async def interleave(function, *args, **kwargs):
        result = await call(function, *args, **kwargs)
        if function == runtime._situation_tick and result == "situation_page_applied":
            with factory() as session:
                count = session.get(MemorySituationApplyRun, run_id).applied_count
                pages.append(count)
                # A genuinely separate writer can enter between receipts.
                session.execute(text("INSERT INTO test_writer_turns VALUES (:turn)"), {"turn": len(pages)})
                session.commit()
            await projection.tick()
        elif function == runtime._rebuild_situation_brief:
            briefs.append(len(pages))
        return result
    monkeypatch.setattr(runtime._canonical, "call", interleave)
    try:
        for _ in range(8):
            await runtime.tick()
            with factory() as session:
                if session.get(MemorySituationApplyRun, run_id).state == "completed":
                    break
        else:
            pytest.fail("manual run failed to finish")
        # Outbox fanout is independently bounded; wait for its real queue to
        # reach every applied receipt, not an assumed number of worker ticks.
        with factory() as session:
            items = tuple(session.scalars(select(MemoryItem.id)))
        for _ in range(256):
            await projection.tick()
            if all(projection.index.identity(f"memory-item:{item}") is not None for item in items
                   if _live(factory, item)):
                break
        else:
            pytest.fail("vector work did not reach all live applied memories")
    finally:
        await runtime.stop()
    return pages, briefs


def _live(factory, item_id):
    with factory() as session:
        item = session.get(MemoryItem, item_id)
        return item is not None and item.deleted_at is None and item.status == "active"


@pytest.mark.parametrize("count,expected", [(1, [1]), (2, [2]), (4, [4]),
    (20, [20]), (21, [20, 1]), (33, [20, 13])])
def test_manual_run_coalesces_eager_worker_and_maps_each_vector(runtime_factory, index, transport, monkeypatch, count, expected):
    run_id = seed_run(runtime_factory, count)
    saved = {}
    upsert = index.upsert
    def capture(documents):
        for document in documents:
            saved[document.memory_item_id] = document.vector
        return upsert(documents)
    monkeypatch.setattr(index, "upsert", capture)
    projection = MemoryVectorProjection(runtime_factory, index, provider=GeminiAdapter())
    async def run():
        try:
            return await drive(runtime_factory, projection, run_id, monkeypatch)
        finally:
            await projection.stop()
    pages, briefs = asyncio.run(run())
    assert pages == list(range(1, count + 1))
    assert briefs == [count]  # The character's ready run now drains continuously.
    bodies = [json.loads(request.content)["requests"] for request in transport[0]]
    assert [len(body) for body in bodies] == expected
    with runtime_factory() as session:
        items = list(session.scalars(select(MemoryItem)))
        assert len(items) == len(saved) == count
        by_text = {embedding_text(item.summary, query=False): item.id for item in items}
        for body in bodies:
            for position, entry in enumerate(body, 1):
                item_id = by_text[entry["content"]["parts"][0]["text"]]
                assert saved[item_id][0] == position
                assert index.identity(f"memory-item:{item_id}") is not None
        assert session.execute(text("SELECT count(*) FROM test_writer_turns")).scalar_one() == count
        run_row = session.get(MemorySituationApplyRun, run_id)
        assert run_row.applied_count == count and run_row.blocked_count == 0


def test_model_without_batch_method_keeps_single_delivery(runtime_factory, index, transport, monkeypatch):
    run_id = seed_run(runtime_factory, 4)
    class SingleProvider:
        async def embed_measured(self, request, *, timeout_seconds):
            return await GeminiAdapter().embed_measured(request, timeout_seconds=timeout_seconds)
    projection = MemoryVectorProjection(runtime_factory, index, provider=SingleProvider())
    async def run():
        try:
            await drive(runtime_factory, projection, run_id, monkeypatch)
        finally:
            await projection.stop()
    asyncio.run(run())
    assert [len(json.loads(request.content)["requests"]) for request in transport[0]] == [1, 1, 1, 1]


def test_completed_group_splits_by_bytes(runtime_factory, index, transport, monkeypatch):
    run_id = seed_run(runtime_factory, 20, length=900)
    projection = MemoryVectorProjection(runtime_factory, index, provider=GeminiAdapter())
    async def run():
        try:
            await drive(runtime_factory, projection, run_id, monkeypatch)
        finally:
            await projection.stop()
    asyncio.run(run())
    bodies = [json.loads(request.content)["requests"] for request in transport[0]]
    # The conservative wire budget includes JSON escaping and per-item envelope.
    assert [len(body) for body in bodies] == [5, 5, 5, 5]
    assert all(len(json.dumps([row["content"]["parts"][0]["text"] for row in body], ensure_ascii=True).encode())
        + 256 * len(body) <= 64 * 1024 for body in bodies)


def test_model_declared_smaller_limit_is_used_by_preparation_and_transport(runtime_factory, index, transport, monkeypatch):
    from app.providers.registry import get_model_spec
    spec = get_model_spec("google", "gemini-embedding-2")
    limited = replace(spec, embedding_batch_limits=replace(spec.embedding_batch_limits, max_items=3))
    for module in ("vector_situation_batches", "vector_batches"):
        monkeypatch.setattr(f"app.runtime.memory.{module}.get_model_spec", lambda *_: limited)
    run_id = seed_run(runtime_factory, 4)
    projection = MemoryVectorProjection(runtime_factory, index, provider=GeminiAdapter())
    async def run():
        try:
            await drive(runtime_factory, projection, run_id, monkeypatch)
        finally:
            await projection.stop()
    asyncio.run(run())
    assert [len(json.loads(request.content)["requests"]) for request in transport[0]] == [3, 1]


def test_partial_producer_failure_releases_prepared_members(runtime_factory, index, transport, monkeypatch):
    from app.runtime.memory import situation_runtime
    from app.domains.memory.exceptions import MemoryCapacityReached
    run_id = seed_run(runtime_factory, 4)
    original = situation_runtime.apply_page
    def stop_third(session, *args, **kwargs):
        if session.get(MemorySituationApplyRun, run_id).applied_count == 2:
            raise MemoryCapacityReached()
        return original(session, *args, **kwargs)
    monkeypatch.setattr(situation_runtime, "apply_page", stop_third)
    projection = MemoryVectorProjection(runtime_factory, index, provider=GeminiAdapter())
    runtime = MemoryBatchRuntime(runtime_factory, lambda: None, generation_policy="activity_situation")
    async def run():
        try:
            assert await runtime.tick() == "memory_capacity_reached"
            await projection.tick()
        finally:
            await runtime.stop()
            await projection.stop()
    asyncio.run(run())
    assert [len(json.loads(request.content)["requests"]) for request in transport[0]] == [2]
    with runtime_factory() as session:
        assert session.get(MemorySituationApplyRun, run_id).state == "error"
        assert len(tuple(session.scalars(select(MemoryItem)))) == 2


def test_deletion_after_group_response_cannot_restore_memory(runtime_factory, index, transport, monkeypatch):
    run_id = seed_run(runtime_factory, 2)
    deleted = []
    class DeleteDuringResponse(GeminiAdapter):
        async def embed_batch_measured(self, request, *, timeout_seconds):
            response = await super().embed_batch_measured(request, timeout_seconds=timeout_seconds)
            with runtime_factory() as session:
                item = session.scalar(select(MemoryItem).order_by(MemoryItem.summary))
                deleted.append(item.id)
                item.deleted_at, item.status, item.version = datetime.now(UTC), "deleted", item.version + 1
                session.commit()
            return response
    projection = MemoryVectorProjection(runtime_factory, index, provider=DeleteDuringResponse())
    async def run():
        try:
            await drive(runtime_factory, projection, run_id, monkeypatch)
        finally:
            await projection.stop()
    asyncio.run(run())
    assert len(transport[0]) == 1
    assert index.identity(f"memory-item:{deleted[0]}") is None
    with runtime_factory() as session:
        rows = list(session.scalars(select(MemoryItem)))
        assert session.get(MemoryItem, deleted[0]).status == "deleted"
        assert all(index.identity(f"memory-item:{row.id}") is not None for row in rows if row.id != deleted[0])


def test_busy_after_group_response_recovers_without_another_http(runtime_factory, index, transport, monkeypatch):
    from app.core.sqlite_concurrency import is_sqlite_contention
    from app.domains.memory.models.vector_work import MemoryVectorWork
    run_id = seed_run(runtime_factory, 2)
    engine = runtime_factory.kw["bind"]
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    held = []
    class BusyDuringResponse(GeminiAdapter):
        async def embed_batch_measured(self, request, *, timeout_seconds):
            response = await super().embed_batch_measured(request, timeout_seconds=timeout_seconds)
            connection = engine.connect()
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            held.append(connection)
            return response
    runtime = MemoryBatchRuntime(runtime_factory, lambda: None, generation_policy="activity_situation")
    first = MemoryVectorProjection(runtime_factory, index, provider=BusyDuringResponse())
    async def run():
        try:
            await runtime.tick()
            try:
                await first.tick()
            except Exception as exc:
                # ACK shares the busy writer; the durable claim remains owned.
                assert is_sqlite_contention(exc)
            assert len(transport[0]) == 1
            assert len(first._received) == 2
        finally:
            for connection in held:
                connection.rollback()
                connection.close()
            await first.stop()
            await runtime.stop()
        with runtime_factory() as session:
            items = tuple(session.scalars(select(MemoryItem.id)))
            assert all(index.identity(f"memory-item:{item}") is None for item in items)
            # Deterministically advance the expired-lease/retry boundary.
            for row in session.scalars(select(MemoryVectorWork)):
                row.due_at, row.lease_until = 0, 0
            session.commit()
        restarted = MemoryVectorProjection(runtime_factory, index, provider=GeminiAdapter())
        try:
            await restarted.tick()
            assert all(index.identity(f"memory-item:{item}") is not None for item in items)
        finally:
            await restarted.stop()
    asyncio.run(run())
    assert len(transport[0]) == 1


def test_foreground_chat_still_defers_application_and_brief(runtime_factory, index, monkeypatch):
    run_id = seed_run(runtime_factory, 2)
    monkeypatch.setattr("app.runtime.memory.foreground_priority.chat_is_active", lambda *a, **k: True)
    runtime = MemoryBatchRuntime(runtime_factory, lambda: None, generation_policy="activity_situation")
    def unexpected_brief():
        raise AssertionError("foreground chat must not run the slow brief rebuild")
    monkeypatch.setattr(runtime, "_rebuild_situation_brief", unexpected_brief)
    async def run():
        try:
            assert await runtime.tick() == "memory_foreground_deferred"
        finally:
            await runtime.stop()
    asyncio.run(run())
    with runtime_factory() as session:
        assert session.get(MemorySituationApplyRun, run_id).applied_count == 0


def test_prior_attempt_bypasses_wait_for_unfinished_producer(runtime_factory, index):
    from app.runtime.memory.situation_runtime import SituationRuntime
    from app.runtime.memory.vector_changes import bootstrap_page
    from app.runtime.memory.vector_situation_batches import ready_page
    from app.domains.memory.models.vector_work import MemoryVectorAttempt
    run_id = seed_run(runtime_factory, 3)
    assert SituationRuntime(runtime_factory).tick() == "situation_page_applied"
    projection = MemoryVectorProjection(runtime_factory, index, provider=GeminiAdapter())
    try:
        bootstrap_page(projection)
        with runtime_factory() as session:
            item = session.scalar(select(MemoryItem.id))
            assert session.get(MemorySituationApplyRun, run_id).state == "deferred"
            assert ready_page(projection, session)[0] == ()
            session.add(MemoryVectorAttempt(item_id=item, profile=EMBEDDING_PROFILE,
                content_hash="prior-hash", credential_revision="prior-revision", attempts=1, retry_after=0))
            session.commit()
        with runtime_factory() as session:
            assert ready_page(projection, session)[0] == (item,)
    finally:
        asyncio.run(projection.stop())
