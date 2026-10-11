"""Production runtime factory, real FTS child and file SQLite; no provider keys."""
import asyncio
from hashlib import sha256
from time import monotonic
from types import SimpleNamespace
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from memory.test_activity_situation_contract import NOW
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_application import real_source, receipt, apply
from app.runtime.persistence.model_registration import register_models
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest, RecallAxisStatus
from app.domains.memory.contracts.recall import MemoryRecallDocument, RecallDocumentKind
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.memory.hybrid_runtime import MemoryHybridRuntime
from app.contracts.retrieval_observation import Observation, current
from app.contracts.search_diagnostics import trace_payload


def test_actual_runtime_uses_async_canonical_fresh_hydration_and_owned_cleanup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canonical.db'}", pool_timeout=.05)
    event.listen(engine, "connect", lambda db, _: db.execute("PRAGMA foreign_keys=ON"))
    register_models().create_all(engine)
    with Session(engine) as db:
        scope, setting, _, memory, *_ = _stack(db)
        post = real_source(db, scope)
        admitted = receipt(db, scope, post)
        apply(db, setting, memory)
        item = db.get(MemoryItem, admitted.applied_item_id)
        document = MemoryRecallDocument(f"memory-item:{item.id}", item.id, scope.owner_id, scope.world_id,
            scope.subject_world_character_id, RecallDocumentKind.MEMORY_ITEM, item.id, item.summary,
            occurred_at=NOW, metadata={"item_version": str(item.version),
                "document_content_hash": sha256(item.summary.encode()).hexdigest()})
        post_id = post.id
        db.commit()
    paths = SimpleNamespace(search=tmp_path / "search")
    index = SqliteMemoryRecallIndex(SimpleNamespace(resolve=lambda: paths))
    index.open()
    index.replace_memory_item(memory_item_id=document.memory_item_id, documents=(document,))
    runtime = MemoryHybridRuntime(sessionmaker(engine), index, paths, episode_only=True)
    observation = Observation(detailed=True)
    token = current.set(observation)
    async def run():
        assert runtime.service._canonical is runtime.canonical_worker
        request = HybridRecallRequest("runtime-request", "runtime-call", "0"*64, scope,
            "평범한", "fixture", (RecallDocumentKind.MEMORY_ITEM,))
        result = await runtime.service.execute(request, deadline=monotonic()+30)
        assert result.status is RecallAxisStatus.PARTIAL  # vector unavailable, real FTS ready
        assert len(result.records) == 1 and result.validation_snapshot is not None
        rows = trace_payload()["canonical_reads"]
        assert [row["stage"] for row in rows] == ["revalidate", "hydrate"]
        assert all(row["cleaned"] and row["sql_count"] > 0 and row["unique_nodes"] == 1 for row in rows)
        assert all(row["memo_hits"] == 0 for row in rows)
        with Session(engine) as db:
            from app.domains.social.models.posts import Post
            db.get(Post, post_id).report_hidden_at = NOW
            db.commit()
        blocked = await runtime.service.execute(request, deadline=monotonic()+30)
        assert blocked.records == ()  # next operation cannot reuse the previous ACL decision
    async def owned():
        try:
            await run()
        finally:
            await runtime.stop()
        assert engine.pool.checkedout() == 0
    try:
        asyncio.run(owned())
    finally:
        current.reset(token)
        index.close()
        engine.dispose()
