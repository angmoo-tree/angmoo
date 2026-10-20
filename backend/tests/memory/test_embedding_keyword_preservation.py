"""The unchanged recall path remains useful without a paid embedding binding."""
import asyncio
from memory.worker_test_support import worker_lifetime
from time import monotonic
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from memory.test_p8_l_h_canonical_recall import runtime_factory, _accept_chat_memory
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.repository.embedding import MemoryEmbeddingRepository
from app.domains.memory.repository.hybrid_recall import SqlAlchemyHybridCanonicalReader
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.hybrid_axes import FtsHybridAxis, VectorHybridAxis
from app.runtime.memory.recall_composition import recall_document_source, canonical_recall_repository
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.memory_embedding_provider import MemoryQueryEmbedder
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath


@pytest.mark.parametrize("enabled", [False, True])
def test_off_or_missing_key_keeps_real_fts_and_skips_provider_and_vec1(runtime_factory, tmp_path, monkeypatch, enabled, deny_external_network, worker_lifetime):
    scope, _, _, _, item_id = _accept_chat_memory(runtime_factory)
    with runtime_factory() as db:
        setting = db.scalar(select(MemoryScopeSettingModel))
        db.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=enabled, provider="google",
            model="gemini-embedding-2", profile=EMBEDDING_PROFILE, version=1))
        db.commit()
    provider = AsyncMock(side_effect=AssertionError("unexpected_external_embedding"))
    monkeypatch.setattr("app.providers.gemini.GeminiAdapter.embed_measured", provider)
    workers = type("UnusedVectorWorkers", (), {"search": AsyncMock(side_effect=AssertionError("unexpected_vec1_read"))})()
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "fts"))
    index.open(); index.rebuild(recall_document_source(runtime_factory).all_documents())
    fts_workers = FtsReadWorkers(database_path=index.database_path)
    worker_lifetime.track(fts_workers)
    canonical = SqlAlchemyHybridCanonicalReader(runtime_factory, source_reader_factory=source_evidence_reader,
        canonical=canonical_recall_repository(runtime_factory))
    service = HybridRecallService(fts=FtsHybridAxis(fts_workers),
        vector=VectorHybridAxis(workers, MemoryQueryEmbedder(runtime_factory,
            lambda db: MemoryEmbeddingRepository(db, memory_repository(db)))), canonical=canonical)
    request = HybridRecallRequest("synthetic-request", "synthetic-call", "b" * 64, scope, "폭우", EMBEDDING_PROFILE,
        (RecallDocumentKind.MEMORY_ITEM,))
    result = worker_lifetime.run(service.execute(request, deadline=monotonic() + 15))
    assert any(record.memory_item_id == item_id for record in result.records)
    assert result.embedding_usage.logical_calls == 0
    provider.assert_not_called(); workers.search.assert_not_called()
    assert fts_workers.busy_jobs == 0
