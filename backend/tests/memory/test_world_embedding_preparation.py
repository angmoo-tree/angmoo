"""Explicit preparation uses one actor and an immutable, revocable key revision."""
import asyncio
from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from memory.test_p8_l_h_canonical_recall import runtime_factory, _accept_chat_memory
from memory.projection_fixture import index, A
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.models.activity_configuration import MemoryIndexPreparation
from app.domains.memory.models.embedding import MemoryEmbeddingSetting, MemoryVectorEligibility
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.repository import index_preparation
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.vector_projection import MemoryVectorProjection
from app.providers.contracts import MeasuredEmbeddingResponse, ProviderUsage


def configured(factory):
    scope, _, _, _, item = _accept_chat_memory(factory)
    args = dict(owner_id=scope.owner_id, world_id=scope.world_id,
        world_character_id=scope.subject_world_character_id, purpose="embedding")
    with factory() as db:
        setting = db.scalar(select(MemoryScopeSettingModel))
        world_credentials.save(db, **args, data=WorldCredentialWrite(expected_revision=0,
            provider="google", model="gemini-embedding-2", api_key="synthetic-explicit-embedding"))
        db.add(MemoryEmbeddingSetting(scope_setting_id=setting.id, enabled=True, provider="google",
            model="gemini-embedding-2", profile=EMBEDDING_PROFILE, version=1))
        index_preparation.mark_needed(db, setting, EMBEDDING_PROFILE)
        db.commit()
        return scope, item, args, setting.id


class Embeddings:
    def __init__(self, during=None):
        self.requests, self.during = [], during
    async def embed_measured(self, request, *, timeout_seconds):
        self.requests.append(request)
        if self.during:
            self.during()
        return MeasuredEmbeddingResponse(tuple(A), ProviderUsage(), 1)


@pytest.mark.parametrize("change", [None, "rotate", "revoke"])
def test_save_on_and_get_do_not_prepare_but_explicit_job_is_fenced(runtime_factory, index, change, deny_external_network):
    scope, item, args, setting_id = configured(runtime_factory)
    def change_key():
        with runtime_factory() as db:
            if change == "rotate":
                world_credentials.save(db, **args, data=WorldCredentialWrite(expected_revision=1,
                    provider="google", model="gemini-embedding-2", api_key="synthetic-rotated-embedding"))
            elif change == "revoke":
                world_credentials.delete(db, **args, expected_revision=1)
            db.commit()
    provider = Embeddings(change_key if change else None)
    projection = MemoryVectorProjection(runtime_factory, index, provider=provider)
    # Existing registrations are not enrolled by ON, GET or a regular tick.
    with runtime_factory() as db:
        assert db.get(MemoryVectorEligibility, item).registration_revision == "memory-vector.v1"
        assert index_preparation.status(db, setting_id)["state"] == "needs_preparation"
    asyncio.run(projection.tick())
    assert provider.requests == [] and index.identity(f"memory-item:{item}") is None
    with runtime_factory() as db:
        started = index_preparation.start(db, memory_repository(db), scope,
            expected_revision=1, credential_revision=1, now=datetime.now(UTC))
        db.commit()
        replay = index_preparation.start(db, memory_repository(db), scope,
            expected_revision=started["revision"], credential_revision=1, now=datetime.now(UTC))
        assert replay == started
        db.commit()
    asyncio.run(projection._prepare_page())
    assert len(provider.requests) == 1
    assert provider.requests[0].api_key == "synthetic-explicit-embedding"
    with runtime_factory() as db:
        row = db.get(MemoryIndexPreparation, setting_id)
        assert row.credential_revision == 1
        assert row.state == ("error" if change == "revoke" else "ready")
    assert (index.identity(f"memory-item:{item}") is None) == (change == "revoke")
