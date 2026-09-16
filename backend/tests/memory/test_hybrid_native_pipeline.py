import asyncio
from dataclasses import replace
from datetime import UTC
import hashlib
import pytest
from time import monotonic

from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument
from app.domains.memory.repository.hybrid_recall import SqlAlchemyHybridCanonicalReader
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.providers.contracts import MeasuredEmbeddingResponse, ProviderUsage
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.memory.hybrid_axes import FtsHybridAxis, VectorHybridAxis
from app.runtime.memory.recall_composition import recall_document_source, canonical_recall_repository
from app.runtime.memory.source_composition import source_evidence_reader
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from memory.test_p8_l_h_canonical_recall import runtime_factory, _accept_chat_memory
from memory.test_sqlite_vec1 import index, A


@pytest.mark.parametrize("lexical_policy", ["legacy_strict_v1", "group_or_v1"])
@pytest.mark.parametrize("revocation", ["blocked", "deleted_source", "memory_off"])
def test_real_fts_vec1_fusion_hydrates_authorized_sources_and_rejects_stale_version(runtime_factory, index, tmp_path, revocation, lexical_policy):
    scope, counterpart, thread, message, item_id = _accept_chat_memory(runtime_factory)
    source = recall_document_source(runtime_factory)
    documents = source.all_documents()
    summary = next(doc for doc in documents if doc.kind is RecallDocumentKind.MEMORY_ITEM)
    fts = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "fts"))
    fts.open()
    fts.rebuild(documents)
    vector = MemoryVectorDocument(summary.document_id, item_id, scope,
        int(summary.metadata["item_version"]), hashlib.sha256(summary.text.encode()).hexdigest(),
        EMBEDDING_PROFILE, A, summary.occurred_at.replace(tzinfo=UTC), summary.counterpart_world_character_id, summary.thread_id)
    index.upsert((vector,))
    class Embedder:
        calls = 0
        async def query(self, request, *, deadline):
            self.calls += 1
            return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)
    embedder = Embedder()
    fts_workers = FtsReadWorkers(database_path=fts.database_path)
    vec_workers = VectorReadWorkers(database_path=index.database_path, extension_path=index._extension,
        extension_sha256=hashlib.sha256(index._extension.read_bytes()).hexdigest())
    canonical = SqlAlchemyHybridCanonicalReader(runtime_factory, source_reader_factory=source_evidence_reader,
        canonical=canonical_recall_repository(runtime_factory))
    service = HybridRecallService(fts=FtsHybridAxis(fts_workers, lexical_policy=lexical_policy), vector=VectorHybridAxis(vec_workers, embedder), canonical=canonical)
    request = HybridRecallRequest("test-request", "test-call", "b"*64, scope, "폭우", EMBEDDING_PROFILE,
        (RecallDocumentKind.MEMORY_ITEM, RecallDocumentKind.OWNER_MEMORY_REQUEST))
    result = asyncio.run(service.execute(request, deadline=monotonic()+15))
    assert {axis.status.value for axis in result.axes} == {"ready"}
    assert all(axis.candidate_count > 0 for axis in result.axes)
    assert result.records[0].memory_item_id == item_id
    assert result.sources and all(receipt.record_count == 1 for receipt in result.sources)
    assert len(result.records) >= 2
    assert embedder.calls == 1
    assert not fts_workers.active_processes and not vec_workers.active_processes
    index.upsert((replace(vector, version=vector.version+1),))
    stale = asyncio.run(service.execute(request, deadline=monotonic()+15))
    assert stale.excluded_count >= 1
    assert stale.status.value == "partial"
    # Unresolved natural-language subjects cannot bypass current source policy,
    # even if the vector index still contains a previously authorized record.
    index.upsert((vector,))
    from model_fixture_support import models
    from app.runtime.memory.composition import memory_repository
    from app.domains.memory.service.scope import MemoryScopeService
    with runtime_factory() as session:
        if revocation == "blocked":
            session.add(models.WorldCharacterBlock(id="hybrid-test-block", world_id=scope.world_id,
                blocker_world_character_id=scope.subject_world_character_id,
                blocked_world_character_id=counterpart))
        elif revocation == "deleted_source":
            session.delete(session.get(models.MessageMessage, message))
        else:
            repository = memory_repository(session)
            setting = repository.get_scope_setting(scope)
            MemoryScopeService(repository).update(scope, expected_version=setting.version,
                enabled=False, retention_days=setting.retention_days)
        session.commit()
    revoked = asyncio.run(service.execute(replace(request, search_text="미등록별명과 겪은 사건"), deadline=monotonic()+15))
    assert revoked.records == ()
    assert not fts_workers.active_processes and not vec_workers.active_processes
