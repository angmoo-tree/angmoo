import asyncio
from datetime import UTC, datetime
from sqlalchemy import select

from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.models.embedding import MemoryEmbeddingSetting
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.providers.contracts import MeasuredEmbeddingResponse, ProviderUsage
from app.runtime.memory import vector_projection
from memory.test_p8_l_h_canonical_recall import runtime_factory, _accept_chat_memory
from memory.test_sqlite_vec1 import index, A


def setup_projection_scope(runtime_factory, monkeypatch):
    scope, _, _, _, item_id = _accept_chat_memory(runtime_factory)
    with runtime_factory() as session:
        setting = session.scalar(select(MemoryScopeSettingModel))
        session.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=True, provider="google",
            model="gemini-embedding-2", profile=EMBEDDING_PROFILE, version=1))
        session.commit()
    material = CredentialMaterial("fixture", "google", "gemini-embedding-2", "revision-1",
        CredentialPurpose.MEMORY_EMBEDDING, "unused-fixture-secret")
    monkeypatch.setattr(vector_projection, "embedding_material", lambda *a: material)
    return item_id, material


def test_retry_budget_survives_restart_and_new_credential_can_retry(runtime_factory, index, monkeypatch):
    from dataclasses import replace
    item_id, material = setup_projection_scope(runtime_factory, monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(vector_projection, "time", lambda: clock[0])
    class Failure(Exception):
        retryable = True
        physical_attempts = 1
    class Provider:
        calls = 0
        async def embed_measured(self, request, *, timeout_seconds):
            self.calls += 1
            raise Failure()
    provider = Provider()
    for _ in range(3):
        projection = vector_projection.MemoryVectorProjection(runtime_factory, index, provider=provider)
        assert asyncio.run(projection.sync_item(item_id)) == "failed"
        assert asyncio.run(projection.sync_item(item_id)) == "attempts_exhausted"
        clock[0] += 300
    restarted = vector_projection.MemoryVectorProjection(runtime_factory, index, provider=provider)
    assert asyncio.run(restarted.sync_item(item_id)) == "attempts_exhausted"
    assert provider.calls == 3
    monkeypatch.setattr(vector_projection, "embedding_material", lambda *a: replace(material, fingerprint="revision-2"))
    assert asyncio.run(restarted.sync_item(item_id)) == "failed"
    assert provider.calls == 4


def test_deleted_item_during_embedding_cannot_install_late_vector(runtime_factory, index, monkeypatch):
    item_id, _ = setup_projection_scope(runtime_factory, monkeypatch)
    class Provider:
        async def embed_measured(self, request, *, timeout_seconds):
            with runtime_factory() as session:
                item = session.get(MemoryItem, item_id)
                item.status, item.deleted_at, item.version = "deleted", datetime.now(UTC), item.version+1
                session.commit()
            return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)
    projection = vector_projection.MemoryVectorProjection(runtime_factory, index, provider=Provider())
    assert asyncio.run(projection.sync_item(item_id)) == "changed"
    assert index.identity(f"memory-item:{item_id}") is None


def test_restart_pin_off_and_deleted_source_do_not_reembed_existing_content(runtime_factory, index, monkeypatch):
    scope, _, _, _, item_id = _accept_chat_memory(runtime_factory)
    with runtime_factory() as session:
        setting = session.scalar(select(MemoryScopeSettingModel))
        session.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=True, provider="google",
            model="gemini-embedding-2", profile=EMBEDDING_PROFILE, version=1))
        session.commit()
    material = CredentialMaterial("fixture", "google", "gemini-embedding-2", "fixture",
        CredentialPurpose.MEMORY_EMBEDDING, "unused-fixture-secret")
    monkeypatch.setattr(vector_projection, "embedding_material", lambda *a: material)
    class Provider:
        calls = 0
        async def embed_measured(self, request, *, timeout_seconds):
            self.calls += 1
            # No held write transaction blocks an independent reader while awaiting AI.
            with runtime_factory() as observer:
                assert observer.get(MemoryItem, item_id).status == "active"
            return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)
    provider = Provider()
    projection = vector_projection.MemoryVectorProjection(runtime_factory, index, provider=provider)
    assert asyncio.run(projection.sync_item(item_id)) == "indexed"
    with runtime_factory() as session:
        item = session.get(MemoryItem, item_id)
        item.pinned_at, item.version = datetime.now(UTC), item.version+1
        session.commit()
    restarted = vector_projection.MemoryVectorProjection(runtime_factory, index, provider=provider)
    assert asyncio.run(restarted.sync_item(item_id)) == "current"
    assert provider.calls == 1
    with runtime_factory() as session:
        session.scalar(select(MemoryEmbeddingSetting)).enabled = False
        session.commit()
    assert asyncio.run(restarted.sync_item(item_id)) == "disabled"
    assert index.identity(f"memory-item:{item_id}") is not None
    assert provider.calls == 1
    with runtime_factory() as session:
        item = session.get(MemoryItem, item_id)
        item.status, item.deleted_at = "deleted", datetime.now(UTC)
        session.commit()
    asyncio.run(restarted.tick())
    assert index.identity(f"memory-item:{item_id}") is None
    assert provider.calls == 1
