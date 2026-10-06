"""Real admission and fake execution consume the frozen World settings revision."""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.chat import models, schemas
from app.domains.chat.contracts import GenerationFence, ResponseRequestState, ResponseTerminalReason
from app.domains.chat.exceptions import MessageValidationError
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.identity.contracts import CredentialMaterial
from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
from app.domains.world_characters.models import WorldCharacter
from chat.test_world_chat_delete import chat_delete_fixture, _accept
from chat.test_p8_l_d_world_chat_api import FRONTEND_HEADERS
from app.domains.characters.models import Character


def _fail(db, request_id):
    repository = SqlAlchemyResponseLifecycleRepository(db)
    now = datetime.now(UTC)
    record = repository.acquire_lease(request_id=request_id, lease_token="synthetic-config-lease",
        now=now, lease_expires_at=now + timedelta(seconds=30))
    repository.mark_terminal(GenerationFence(request_id=record.request_id, thread_id=record.thread_id,
        request_scope_hash=record.request_scope_hash, generation_id=record.generation_id,
        attempt_number=record.attempt_number, lease_generation=record.lease_generation, expected_prior_state=record.state),
        target=ResponseRequestState.FAILED, reason=ResponseTerminalReason.PROVIDER_FAILURE,
        failure_class="synthetic_provider_failure", retryable=True, now=now)
    db.commit()


def _fake_execution(monkeypatch, generation):
    inputs = []
    material = CredentialMaterial(credential_id="synthetic-credential", provider="google",
        model="gemini-3.1-flash-lite", thinking_level="high", fingerprint="synthetic-fingerprint",
        purpose="message", _secret="synthetic-secret-only")
    monkeypatch.setattr(generation.settings_service, "resolve_message_credential_material", lambda *_: (None, material))

    class Workflow:
        async def run(self, command):
            inputs.append(command)
            if False:
                yield None

    monkeypatch.setattr(generation.workflows, "build", lambda *_, **__: SimpleNamespace(workflow=Workflow(), character_labels={}))
    monkeypatch.setattr(generation.workflows, "today_reader", lambda *_: (_ for _ in ()).throw(ValueError("synthetic_no_today")))
    return inputs


def _run(generation, db, owner, thread_id, request_id):
    async def collect():
        return [event async for event in generation.stream_world_response(db, owner, "world-a", thread_id,
            request_id, memory_recall_service=object())]
    return asyncio.run(collect())


def test_world_persona_model_and_revision_are_frozen_at_accept_and_retry(chat_delete_fixture, monkeypatch):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    generation = client.app.state.chat_generation_service
    inputs = _fake_execution(monkeypatch, generation)
    with Session(engine) as db:
        stored = db.get(WorldCharacterConfiguration, "wc-responding")
        stored.profile = {**stored.profile, "display_name": "World A Person", "intro": "World A intro"}
        stored.settings = {**stored.settings, "personality": "World A calm", "speech_style": "World A voice",
            "worldview": "World A history", "generation_model": "gemini-3.1-flash-lite"}
        db.get(WorldCharacter, "wc-responding").version = 7
        db.commit()
        accepted = _accept(client.app, db, owner, thread_id, "configuration")
        row = db.get(models.ChatResponseRequest, accepted.response_request.request_id)
        original = json.loads(row.node_state_json)["_world_configuration"]
        assert original["revision"] == 7 and original["world_id"] == "world-a"
        assert row.selected_model == "gemini-3.1-flash-lite"
        stored.settings = {**stored.settings, "personality": "Later World edit", "generation_model": "gemini-3.5-flash-lite"}
        stored.profile = {**stored.profile, "display_name": "Later World name"}
        db.get(WorldCharacter, "wc-responding").version = 8
        db.commit()
        _run(generation, db, owner, thread_id, row.request_id)
        assert inputs[-1].profile.personality == "World A calm"
        assert inputs[-1].profile.name == "World A Person"
        assert inputs[-1].profile.worldview == "World A history"
        _fail(db, row.request_id)
        retry = generation.retry_world_response(db, owner, "world-a", thread_id,
            schemas.WorldChatRetryCreate(failed_request_id=row.request_id, idempotency_key="configuration-retry-key"))
        retried = db.get(models.ChatResponseRequest, retry.response_request.request_id)
        assert json.loads(retried.node_state_json)["_world_configuration"] == original
        assert retried.selected_model == row.selected_model
        assert retry.user_message.id == accepted.user_message.id
        _run(generation, db, owner, thread_id, retried.request_id)
        assert inputs[-1].profile == inputs[0].profile


def test_thread_override_remains_explicit_and_missing_configuration_cannot_accept(chat_delete_fixture):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    generation = client.app.state.chat_generation_service
    with Session(engine) as db:
        thread = db.get(models.MessageThread, thread_id)
        configuration = db.get(WorldCharacterConfiguration, "wc-responding")
        configuration.settings = {**configuration.settings, "generation_model": "gemini-3.1-flash-lite"}
        thread.model_binding_mode = "thread_override"
        thread.selected_model = "gemini-3.5-flash-lite"
        db.commit()
        accepted = _accept(client.app, db, owner, thread_id, "explicit-model")
        assert db.get(models.ChatResponseRequest, accepted.response_request.request_id).selected_model == "gemini-3.5-flash-lite"
        _fail(db, accepted.response_request.request_id)
        db.delete(configuration)
        db.commit()
        before = db.scalar(select(func.count(models.MessageMessage.id)))
        with pytest.raises(MessageValidationError, match="world_configuration_missing"):
            _accept(client.app, db, owner, thread_id, "missing-configuration")
        db.rollback()
        assert db.scalar(select(func.count(models.MessageMessage.id))) == before
        assert db.get(WorldCharacterConfiguration, "wc-responding") is None
    entry = client.get("/api/v1/worlds/world-a/world-characters/wc-responding/chat-entry", headers=FRONTEND_HEADERS)
    assert entry.status_code == 404 and entry.json()["detail"] == "target_profile_unavailable"
    detail = client.get(f"/api/v1/worlds/world-a/chat/threads/{thread_id}")
    assert detail.status_code == 409 and detail.json()["detail"] == "world_configuration_missing"
    created = client.post("/api/v1/worlds/world-a/chat/threads", headers=FRONTEND_HEADERS,
        json={"responding_world_character_id": "wc-responding"})
    assert created.status_code == 422 and created.json()["detail"] == "world_configuration_missing"
    assert client.get("/api/v1/worlds/world-a/chat/threads").json()["items"] == []
    with Session(engine) as db:
        assert db.get(WorldCharacterConfiguration, "wc-responding") is None
        assert db.scalar(select(func.count(models.MessageMessage.id))) == before


def test_world_thread_entry_create_list_and_detail_use_world_profile_without_mutating_actor(chat_delete_fixture):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    with Session(engine) as db:
        actor = db.get(Character, "responding-character")
        before_actor = (actor.name, actor.handle, actor.avatar_url, actor.banner_url)
        original_requester = dict(db.get(WorldCharacterConfiguration, "wc-requester").profile)
        configuration = db.get(WorldCharacterConfiguration, "wc-responding")
        configuration.profile = {**configuration.profile, "display_name": "World A profile",
            "handle": "world-a-profile", "avatar_url": "/media/synthetic-world-a-avatar.webp",
            "banner_url": "/media/synthetic-world-a-banner.webp"}
        db.get(WorldCharacter, "wc-responding").version += 1
        db.commit()
    responses = [
        client.get(f"/api/v1/worlds/world-a/world-characters/wc-responding/chat-entry", headers=FRONTEND_HEADERS),
        client.post("/api/v1/worlds/world-a/chat/threads", headers=FRONTEND_HEADERS,
                    json={"responding_world_character_id": "wc-responding"}),
        client.get("/api/v1/worlds/world-a/chat/threads"),
        client.get(f"/api/v1/worlds/world-a/chat/threads/{thread_id}"),
    ]
    assert all(response.status_code == 200 for response in responses)
    projections = [responses[0].json()["responding"], responses[1].json()["thread"]["responding"],
                   responses[2].json()["items"][0]["responding"], responses[3].json()["responding"]]
    for projection in projections:
        assert projection["display_name"] == "World A profile"
        assert projection["handle"] == "world-a-profile"
        assert projection["avatar_url"] == "/media/synthetic-world-a-avatar.webp"
        assert projection["banner_url"] == "/media/synthetic-world-a-banner.webp"
        assert projection["world_character_id"] == "wc-responding"
    with Session(engine) as db:
        actor = db.get(Character, "responding-character")
        assert (actor.name, actor.handle, actor.avatar_url, actor.banner_url) == before_actor
        assert db.get(WorldCharacterConfiguration, "wc-requester").profile == original_requester
        assert db.get(WorldCharacter, "wc-responding").world_id == "world-a"
        assert db.get(models.MessageThread, thread_id).world_id == "world-a"


def test_legacy_retry_does_not_insert_world_snapshot_or_read_edited_world_persona(chat_delete_fixture, monkeypatch):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    generation = client.app.state.chat_generation_service
    inputs = _fake_execution(monkeypatch, generation)
    with Session(engine) as db:
        accepted = _accept(client.app, db, owner, thread_id, "legacy-input")
        row = db.get(models.ChatResponseRequest, accepted.response_request.request_id)
        metadata = json.loads(row.node_state_json)
        metadata.pop("_world_configuration")
        row.node_state_json = json.dumps(metadata)
        db.commit()
        _fail(db, row.request_id)
        configuration = db.get(WorldCharacterConfiguration, "wc-responding")
        configuration.settings = {**configuration.settings, "personality": "New World settings should not leak",
            "generation_model": "gemini-3.5-flash-lite"}
        configuration.profile = {**configuration.profile, "display_name": "Renamed after historical admission"}
        db.commit()
        retried = generation.retry_world_response(db, owner, "world-a", thread_id,
            schemas.WorldChatRetryCreate(failed_request_id=row.request_id, idempotency_key="legacy-config-retry-key"))
        retry_row = db.get(models.ChatResponseRequest, retried.response_request.request_id)
        retry_metadata = json.loads(retry_row.node_state_json)
        assert "_world_configuration" not in retry_metadata
        assert retry_metadata["name_binding"] == metadata["name_binding"]
        assert retry_row.selected_model == row.selected_model
        _run(generation, db, owner, thread_id, retry_row.request_id)
        assert inputs[-1].profile.personality == "calm"


@pytest.mark.parametrize("damage", ["other_world", "invalid_payload"])
def test_damaged_request_snapshot_fails_before_provider_execution(chat_delete_fixture, monkeypatch, damage):
    client, engine, _principal, owner, _outsider, thread_id = chat_delete_fixture
    generation = client.app.state.chat_generation_service
    inputs = _fake_execution(monkeypatch, generation)
    with Session(engine) as db:
        accepted = _accept(client.app, db, owner, thread_id, f"damaged-{damage}")
        row = db.get(models.ChatResponseRequest, accepted.response_request.request_id)
        metadata = json.loads(row.node_state_json)
        if damage == "other_world":
            metadata["_world_configuration"]["world_id"] = "other-world"
        else:
            metadata["_world_configuration"] = None
        row.node_state_json = json.dumps(metadata)
        db.commit()
        _run(generation, db, owner, thread_id, row.request_id)
        db.refresh(row)
        assert row.state == "failed" and row.retryable is False
        assert json.loads(row.node_state_json)["failure_class"] == "world_configuration_snapshot_invalid"
        assert inputs == []
