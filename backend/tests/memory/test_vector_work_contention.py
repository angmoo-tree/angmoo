"""Actual file WAL, scheduler heartbeat, deep lineage and the real Vec1 DLL."""
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from statistics import median

from sqlalchemy import event, select, text

from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.test_sqlite_vec1 import index
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_lineage_validation_cost import lineage
from memory.test_vector_pending_work import Provider
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.repository.vector_eligibility import register_content
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.runtime.memory import vector_delivery


def test_large_shared_lineage_keeps_writer_free_and_final_effect_short(runtime_factory, index, monkeypatch):
    engine = runtime_factory.kw["bind"]
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    with runtime_factory() as db:
        scope, setting, _, memory, *_ = _stack(db)
        _, _, _, nodes, _ = lineage((db, scope, setting, memory), levels=32)
        db.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=True, provider="google",
            model="gemini-embedding-2", profile=EMBEDDING_PROFILE, version=1))
        world_credentials.save(db, owner_id=scope.owner_id, world_id=scope.world_id,
            world_character_id=scope.subject_world_character_id, purpose="embedding",
            data=WorldCredentialWrite(expected_revision=0, provider="google", model="gemini-embedding-2", api_key="synthetic-only"))
        for item in nodes:
            item.valid_until = None
        db.flush()
        register_content(db, nodes[-1], now=datetime.now(UTC))
        db.commit()
        item = nodes[-1].id
        from app.domains.identity.models import InstallationIdentity
        from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
        db.add(InstallationIdentity(singleton_key=LOCAL_INSTALLATION_KEY, installation_id="vector-contention-fixture", bootstrap_state="unclaimed"))
        db.commit()
    from app.runtime.persistence.sqlite_scheduler_lease import SqliteSchedulerLeaseRepository
    scheduler = SqliteSchedulerLeaseRepository(engine)
    lease = scheduler.acquire(owner_id="fixture-scheduler", ttl_seconds=30)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider(), episode_only=True)
    from app.domains.memory.repository import vector_queue as queue
    with runtime_factory() as db:
        queue.enqueue(db, projection.generation, item, scope.world_id)
        claim = queue.claim(db, projection.generation, (item,))[0]
        db.commit()
    projection._claims[item] = claim
    entered, release = Event(), Event()
    original = projection._source.documents_for_item_ids
    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(projection._source, "documents_for_item_ids", paused)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(vector_delivery.prepare, projection, item, (), None)
        assert entered.wait(10)
        try:
            assert scheduler.heartbeat(owner_id="fixture-scheduler", fencing_epoch=lease.fencing_epoch, ttl_seconds=30)
        finally:
            release.set()
        prepared = future.result()
    assert isinstance(prepared, vector_delivery.PreparedVector)
    monkeypatch.setattr(projection._source, "documents_for_item_ids", original)
    # Snapshot migration retains the legacy DAG's owned-memory dependencies.
    # It does not re-query original posts while preparing vectors.
    with runtime_factory() as db:
        prior_edges = db.execute(text("SELECT item_id,source_key FROM memory_vector_dependencies WHERE source_kind='memory' AND item_id!=source_key")).all()
        assert len(prior_edges) <= 2 * len(nodes)
        assert {target for source, target in prior_edges if source == item and target.startswith("lineage-")} == {
            node.id for node in nodes[:-2]
        }
    assert asyncio.run(projection.sync_item(item)) == "indexed"
    # Compare the same source/fixture inside the former critical-section shape
    # with the new final-only fence; no timing threshold or sleep is asserted.
    old_facts, final_facts, old_sql, final_sql = [], [], [], []
    statements = []
    def record(conn, cursor, statement, params, context, many):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", record)
    original_writer = vector_delivery.run_sqlite_session_immediate
    def measured(session, operation, **kwargs):
        return original_writer(session, operation, observer=final_facts.append, **kwargs)
    monkeypatch.setattr(vector_delivery, "run_sqlite_session_immediate", measured)
    try:
        for _ in range(20):
            statements.clear()
            with runtime_factory() as db:
                documents = run_sqlite_session_immediate(db,
                    lambda: original((item,), session=db), observer=old_facts.append, require_clean=True)
                assert documents[item]
            old_sql.append(len(statements))
            prepared = vector_delivery.prepare(projection, item, (), None)
            statements.clear()
            assert vector_delivery.refresh_current(projection, prepared) == "current"
            final_sql.append(len(statements))
            assert not any("memory_episode_restrictions" in sql or "FROM posts" in sql for sql in statements)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    def stats(values):
        values = sorted(float(row["transaction_ms"]) for row in values if row["result"] == "committed")
        return {"n": len(values), "p50_ms": median(values), "p95_ms": values[int(.95*(len(values)-1))], "max_ms": max(values)}
    report = {"fixture": "64 memory items, shared two-wide prior DAG, actual Vec1", "old_shape": stats(old_facts),
        "new_final": stats(final_facts), "old_sql_per_fence": old_sql, "new_sql_per_fence": final_sql,
        "heartbeat_during_snapshot": "passed", "provider_calls": projection._provider.calls}
    if destination := os.environ.get("ANGMOO_VECTOR_METRICS_PATH"):
        Path(destination).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    assert projection._provider.calls == 1


def test_real_vec1_busy_preserves_receipt_and_releases_canonical_writer(runtime_factory, index, monkeypatch):
    from memory.test_vector_projection_lifecycle import setup_projection_scope
    from memory.projection_fixture import A
    from app.core.sqlite_concurrency import run_sqlite_immediate
    item, _ = setup_projection_scope(runtime_factory, monkeypatch)
    projection = MemoryVectorProjection(runtime_factory, index, provider=Provider())
    prepared = vector_delivery.prepare(projection, item, (), None)
    receipt = {"binding": prepared.binding, "vector": A, "receipt_id": "busy-recovery"}
    with index._connect() as held:
        held.execute("BEGIN IMMEDIATE")
        assert vector_delivery.persist(projection, prepared, receipt) == "local_result_pending"
        engine = runtime_factory.kw["bind"]
        assert run_sqlite_immediate(engine, lambda connection: connection.exec_driver_sql("SELECT 1").scalar_one()) == 1
        assert projection.journal.read(prepared.work[0].world_id, item) == receipt
        held.rollback()
    restarted = MemoryVectorProjection(runtime_factory, index, provider=projection._provider)
    assert asyncio.run(restarted.sync_item(item)) == "indexed"
    assert restarted._provider.calls == 0
