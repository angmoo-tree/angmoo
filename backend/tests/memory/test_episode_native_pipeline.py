"""Actual SQLite/FTS5/Vec1 workers; deterministic embedding and episode output."""

import asyncio
from dataclasses import replace
from hashlib import sha256
import json
from time import monotonic

from sqlalchemy.orm import sessionmaker

from app.domains.memory.contracts.episode import EpisodeProposal, EpisodeSelection
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument
from app.domains.memory.repository.episode_apply import SqlAlchemyEpisodeApply
from app.domains.memory.repository.episode_hybrid_recall import SqlAlchemyEpisodeHybridReader
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.providers.contracts import MeasuredEmbeddingResponse, ProviderUsage
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_revalidation import revalidate_episode_bundle
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.hybrid_axes import FtsHybridAxis, VectorHybridAxis
from app.runtime.memory.recall_composition import recall_document_source
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex, MemoryRecallIndexSettings
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from memory.test_episode_chat_pipeline import setup, response_session
from memory.test_sqlite_vec1 import index, A


def test_successful_chat_thought_episode_projection_native_fusion_and_hydration(response_session, index, tmp_path):
    db = response_session
    scope, memory, bundle, done, now = setup(db)
    ids = SqlAlchemyEpisodeApply(db, memory).apply(bundle=bundle,
        selection=EpisodeSelection((EpisodeProposal("사용자와 대화하며 도움을 주고 싶다고 생각했다.", ("S1",)),), ()),
        setting=memory.get_scope_setting(scope), now=now,
        revalidate=lambda value: revalidate_episode_bundle(db, value), job_fence=lambda: None)
    db.commit()
    factory = sessionmaker(db.bind)
    documents = recall_document_source(factory, now_factory=lambda: now, episode_only=True).all_documents()
    assert len(documents) == 1
    document = documents[0]
    assert document.kind is RecallDocumentKind.MEMORY_ITEM
    assert document.memory_item_id == ids[0]
    assert bundle.new_units[0].thought.text not in document.text
    fts = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "fts"),
        settings=MemoryRecallIndexSettings(generation="memory-episode-v1"))
    fts.open()
    fts.rebuild(documents)
    index.upsert((MemoryVectorDocument(document.document_id, ids[0], scope, int(document.metadata["item_version"]),
        sha256(document.text.encode()).hexdigest(), EMBEDDING_PROFILE, A, document.occurred_at,
        document.counterpart_world_character_id, document.thread_id),))
    class Embedder:
        calls = 0
        async def query(self, request, *, deadline):
            self.calls += 1
            return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)
    embedder = Embedder()
    fts_workers = FtsReadWorkers(database_path=fts.database_path, settings=fts.settings)
    vector_workers = VectorReadWorkers(database_path=index.database_path, extension_path=index._extension,
        extension_sha256=sha256(index._extension.read_bytes()).hexdigest())
    service = HybridRecallService(fts=FtsHybridAxis(fts_workers, lexical_policy="group_or_v1"),
        vector=VectorHybridAxis(vector_workers, embedder),
        canonical=SqlAlchemyEpisodeHybridReader(factory, detail_reader_factory=RuntimeEpisodeDetailReader, clock=lambda: now))
    request = HybridRecallRequest("test", "call", "a" * 64, scope, "사용자 도움", EMBEDDING_PROFILE,
        (RecallDocumentKind.MEMORY_ITEM,), result_limit=12)
    result = asyncio.run(service.execute(request, deadline=monotonic() + 20))
    assert all(axis.candidate_count == 1 and axis.status.value == "ready" for axis in result.axes)
    assert result.fused_count == 1 and len(result.records) == 1
    packet = json.loads(result.records[0].text)
    assert packet["partial"] is False
    assert packet["units"][0]["thought"]["text"] == bundle.new_units[0].thought.text
    assert len(packet["units"][0]["sources"]) == 2
    assert ids[0] not in result.records[0].text
    assert embedder.calls == 1
    assert not fts_workers.active_processes and not vector_workers.active_processes
    # Memory OFF revokes the whole package even while stale projections remain.
    from app.domains.memory.models.items import MemoryScopeSettingModel
    setting = db.get(MemoryScopeSettingModel, memory.get_scope_setting(scope).id)
    setting.enabled = False
    db.commit()
    result = asyncio.run(service.execute(request, deadline=monotonic() + 20))
    assert result.records == ()
    assert not fts_workers.active_processes and not vector_workers.active_processes
    fts.close()
