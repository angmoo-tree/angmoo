import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from social.test_recommendation_topics import scope
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.social.models.topics import RecommendationPreparation
from app.domains.social.schemas.recommendation import TopicDefinition, TopicGenerationResult
from app.domains.social.service.recommendation_topics import available_topics, replace_source_topics
from app.runtime.social import topic_preparation as service


def connected(scope, monkeypatch):
    db, world, character, wc = scope
    world.owner_user_id = character.owner_id
    db.commit()
    service.connect_key(db, world_id=world.id, owner_id=character.owner_id, world_character_id=wc.id)
    monkeypatch.setattr(service, "find_world_character_credential", lambda db, **kwargs: SimpleNamespace(id="test-key"))
    def resolve(credential, **kwargs):
        assert kwargs["owner_id"] == character.owner_id and kwargs["character_id"] == character.id
        return CredentialMaterial("test-key", "google", "gemini-3.5-flash-lite", None, CredentialPurpose.WORLD_CHARACTER_SETUP_LLM, "test-only")
    monkeypatch.setattr(service.CredentialResolver, "resolve_llm_credential", resolve)
    return db, world, character, wc


def result(name):
    return TopicGenerationResult(topics=[TopicDefinition(name=name, scope="world")])


def test_read_does_not_initialize_existing_world_and_foreign_key_is_rejected(scope):
    db, world, character, wc = scope
    assert service.read_topics(db, world_id=world.id, owner_id=world.owner_user_id)["state"] == "pending"
    assert not db.scalar(select(RecommendationPreparation))
    with pytest.raises(service.TopicPreparationError, match="character_not_owned"):
        service.connect_key(db, world_id=world.id, owner_id=world.owner_user_id, world_character_id=wc.id)
    assert not available_topics(db, world.id)


def test_generation_idempotence_and_failure_preserve_current(scope, monkeypatch):
    db, world, character, wc = connected(scope, monkeypatch)
    calls=[]
    async def generator(*args):
        calls.append(1)
        return result("마법")
    async def run():
        kwargs=dict(world_id=world.id, owner_id=character.owner_id, request_id="request-one", generator=generator)
        first=await service.regenerate(db, **kwargs)
        second=await service.regenerate(db, **kwargs)
        assert first["topics"] == second["topics"] and len(calls) == 1
        async def failed(*args):
            raise RuntimeError("private provider diagnostic")
        failure=await service.regenerate(db, world_id=world.id, owner_id=character.owner_id, request_id="request-two", generator=failed)
        assert failure["state"] == "failed" and failure["topics"] == first["topics"]
        assert failure["last_code"] == "generation_failed"
    asyncio.run(run())


def test_source_changed_during_generation_keeps_last_normal_topics(scope, monkeypatch):
    db, world, character, wc = connected(scope, monkeypatch)
    replace_source_topics(db, world_id=world.id, world_character_id=None, topics=[("기존 주제", "world")]); db.commit()
    async def generator(*args):
        world.name = "Changed world"; db.commit()
        return result("늦은 결과")
    response=asyncio.run(service.regenerate(db, world_id=world.id, owner_id=character.owner_id, request_id="request-stale", generator=generator))
    assert response["state"] == "stale"
    assert [t["name"] for t in response["topics"]] == ["기존 주제"]


def test_running_request_does_not_dispatch_second_generation(scope, monkeypatch):
    db, world, character, wc = connected(scope, monkeypatch)
    calls=[]
    async def generator(*args):
        calls.append(1)
        duplicate=await service.regenerate(db, world_id=world.id, owner_id=character.owner_id, request_id="request-other", generator=generator)
        assert duplicate["state"] == "running"
        return result("축구")
    response=asyncio.run(service.regenerate(db, world_id=world.id, owner_id=character.owner_id, request_id="request-start", generator=generator))
    assert response["state"] == "ready" and len(calls) == 1
