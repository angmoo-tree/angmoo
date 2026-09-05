from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import schemas
from app.cruds import agent_runs as agent_run_crud
from app.runtime.characters import management as agent_service


def test_agent_google_models_are_allowed_in_agent_model_schemas():
    for model in (
        "gemma-4-26b-a4b-it",
        "gemma-4-31b-it",
        "gemini-3.1-flash-lite",
    ):
        create = schemas.AgentCreate(
            name="Gemma Bird",
            personality="curious",
            model=model,
            api_key="test-key",
        )
        draft = schemas.AgentCreationDraftCreate(
            model=model,
            api_key="test-key",
        )
        credential = schemas.CredentialUpsert(model=model)

        assert create.model == model
        assert draft.model == model
        assert credential.model == model
        assert credential.api_key is None


@pytest.mark.parametrize(
    "model",
    [
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ],
)
def test_agent_model_schemas_reject_removed_or_message_only_models(model):
    with pytest.raises(ValidationError):
        schemas.AgentCreate(
            name="Gemma Bird",
            personality="curious",
            model=model,
            api_key="test-key",
        )
    with pytest.raises(ValidationError):
        schemas.AgentCreationDraftCreate(model=model, api_key="test-key")
    with pytest.raises(ValidationError):
        schemas.CredentialUpsert(model=model)


def test_message_model_schemas_allow_gemini25_models():
    for model in (
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
        "gemma-4-26b-a4b-it",
        "gemma-4-31b-it",
    ):
        settings = schemas.MessageSettingsUpdate(default_model=model)
        create = schemas.MessageThreadCreate(character_id="char-1", selected_model=model)
        update = schemas.MessageThreadUpdate(selected_model=model)

        assert settings.default_model == model
        assert create.selected_model == model
        assert update.selected_model == model


def test_message_model_schemas_reject_gemini35_flash():
    with pytest.raises(ValidationError):
        schemas.MessageSettingsUpdate(default_model="gemini-3.5-flash")
    with pytest.raises(ValidationError):
        schemas.MessageThreadCreate(
            character_id="char-1",
            selected_model="gemini-3.5-flash",
        )
    with pytest.raises(ValidationError):
        schemas.MessageThreadUpdate(selected_model="gemini-3.5-flash")


def test_unknown_google_model_is_rejected():
    with pytest.raises(ValidationError):
        schemas.CredentialUpsert(model="unknown-google-model")


def test_model_only_credential_update_preserves_existing_key(monkeypatch):
    class FakeDb:
        def __init__(self):
            self.committed = False
            self.refreshed = None

        def commit(self):
            self.committed = True

        def refresh(self, value):
            self.refreshed = value

        def rollback(self):
            raise AssertionError("rollback should not be called")

    db = FakeDb()
    user = SimpleNamespace(id="user-1", email=None)
    character = SimpleNamespace(
        id="char-1",
        name="Gemma Bird",
        execution_mode="llm",
    )
    credential = SimpleNamespace(
        id="cred-1",
        owner_id=user.id,
        character_id=character.id,
        provider="google",
        purpose="agent",
        model="gemini-3.1-flash-lite",
        label="Gemma Bird google",
        encrypted_api_key="encrypted-key",
        key_fingerprint="fingerprint",
        enabled=True,
        cooldown_until=None,
        created_at=datetime(2026, 6, 20, tzinfo=UTC),
        updated_at=datetime(2026, 6, 20, tzinfo=UTC),
    )

    monkeypatch.setattr(agent_service, "_get_owned_character", lambda *_: character)
    monkeypatch.setattr(agent_service.slot_queries, "get_assigned_slot", lambda *_: None)
    monkeypatch.setattr(
        agent_service.agent_crud,
        "get_character_credential",
        lambda *_: credential,
    )
    monkeypatch.setattr(
        agent_service.agent_crud,
        "upsert_credential",
        lambda *_, **__: (_ for _ in ()).throw(
            AssertionError("upsert_credential should not be called")
        ),
    )
    monkeypatch.setattr(agent_service.agent_crud, "log_activity", lambda *_, **__: None)

    result = agent_service.update_credential(
        db,
        user,
        character.id,
        schemas.CredentialUpsert(model="gemma-4-31b-it"),
    )

    assert result.model == "gemma-4-31b-it"
    assert credential.encrypted_api_key == "encrypted-key"
    assert credential.key_fingerprint == "fingerprint"
    assert db.committed is True
    assert db.refreshed is credential


def test_api_key_credential_update_without_slot_commits_in_upsert(monkeypatch):
    class FakeDb:
        def rollback(self):
            raise AssertionError("rollback should not be called")

    db = FakeDb()
    user = SimpleNamespace(id="user-1", email=None)
    character = SimpleNamespace(id="char-1", name="Gemma Bird", execution_mode="llm")
    credential = SimpleNamespace(
        id="cred-1",
        owner_id=user.id,
        character_id=character.id,
        provider="google",
        purpose="agent",
        model="gemini-3.1-flash-lite",
        label="Gemma Bird google",
        key_fingerprint="fingerprint",
        enabled=True,
        cooldown_until=None,
        created_at=datetime(2026, 6, 20, tzinfo=UTC),
        updated_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    upsert_calls: list[dict[str, object]] = []

    def fake_upsert_credential(*_args, **kwargs):
        upsert_calls.append(kwargs)
        return credential

    monkeypatch.setattr(agent_service, "_get_owned_character", lambda *_: character)
    monkeypatch.setattr(agent_service.slot_queries, "get_assigned_slot", lambda *_: None)
    monkeypatch.setattr(
        agent_service.agent_crud, "upsert_credential", fake_upsert_credential
    )
    monkeypatch.setattr(agent_service.agent_crud, "log_activity", lambda *_, **__: None)

    result = agent_service.update_credential(
        db,
        user,
        character.id,
        schemas.CredentialUpsert(api_key="new-key"),
    )

    assert result.id == credential.id
    assert upsert_calls[0]["api_key"] == "new-key"
    assert upsert_calls[0]["commit"] is True


def test_api_key_credential_update_with_idle_slot_syncs_profile(monkeypatch):
    class FakeDb:
        def __init__(self):
            self.committed = False
            self.refreshed = None

        def commit(self):
            self.committed = True

        def refresh(self, value):
            self.refreshed = value

        def rollback(self):
            raise AssertionError("rollback should not be called")

    db = FakeDb()
    user = SimpleNamespace(id="user-1", email=None)
    character = SimpleNamespace(id="char-1", name="Gemma Bird", execution_mode="llm")
    slot = SimpleNamespace(
        agent_id="angmoo-1",
        status=agent_run_crud.SLOT_STATUS_ASSIGNED_IDLE,
        assigned_user_id=user.id,
        assigned_character_id=character.id,
        assigned_credential_id="cred-1",
        next_tick_at=None,
        last_run_at=None,
        heartbeat_interval_seconds=1800,
        locked_by_run_id=None,
        lease_expires_at=None,
        last_error=None,
        updated_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    credential = SimpleNamespace(
        id="cred-1",
        owner_id=user.id,
        character_id=character.id,
        provider="google",
        purpose="agent",
        model="gemini-3.1-flash-lite",
        label="Gemma Bird google",
        key_fingerprint="fingerprint",
        enabled=True,
        cooldown_until=None,
        created_at=datetime(2026, 6, 20, tzinfo=UTC),
        updated_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    upsert_calls: list[dict[str, object]] = []
    bind_calls: list[dict[str, object]] = []
    reload_calls: list[bool] = []

    def fake_upsert_credential(*_args, **kwargs):
        upsert_calls.append(kwargs)
        return credential

    def fake_bind_slot_auth_profile(slot_read, **kwargs):
        bind_calls.append({"slot": slot_read, **kwargs})

    monkeypatch.setattr(agent_service, "_get_owned_character", lambda *_: character)
    monkeypatch.setattr(agent_service.slot_queries, "get_assigned_slot", lambda *_: slot)
    monkeypatch.setattr(
        agent_service.agent_crud, "upsert_credential", fake_upsert_credential
    )
    monkeypatch.setattr(agent_service.agent_crud, "log_activity", lambda *_, **__: None)
    monkeypatch.setattr(agent_service, "_resident_openclaw_sync_enabled", lambda: True)
    monkeypatch.setattr(
        agent_service, "_bind_slot_auth_profile", fake_bind_slot_auth_profile
    )
    monkeypatch.setattr(
        agent_service, "_reload_openclaw_secrets_sync", lambda: reload_calls.append(True)
    )

    result = agent_service.update_credential(
        db,
        user,
        character.id,
        schemas.CredentialUpsert(api_key="new-key"),
    )

    assert result.id == credential.id
    assert upsert_calls[0]["api_key"] == "new-key"
    assert upsert_calls[0]["commit"] is False
    assert bind_calls[0]["slot"].agent_id == slot.agent_id
    assert bind_calls[0]["user_id"] == user.id
    assert bind_calls[0]["character"] is character
    assert bind_calls[0]["credential"] is credential
    assert reload_calls == [True]
    assert db.committed is True
    assert db.refreshed is credential


def test_model_only_credential_update_requires_existing_key(monkeypatch):
    db = SimpleNamespace(
        rollback=lambda: None,
    )
    user = SimpleNamespace(id="user-1", email=None)
    character = SimpleNamespace(id="char-1", execution_mode="llm")

    monkeypatch.setattr(agent_service, "_get_owned_character", lambda *_: character)
    monkeypatch.setattr(agent_service.slot_queries, "get_assigned_slot", lambda *_: None)
    monkeypatch.setattr(
        agent_service.agent_crud,
        "get_character_credential",
        lambda *_: None,
    )

    with pytest.raises(agent_service.CredentialRequiredError):
        agent_service.update_credential(
            db,
            user,
            character.id,
            schemas.CredentialUpsert(model="gemma-4-31b-it"),
        )


def test_running_slot_blocks_credential_model_update(monkeypatch):
    db = SimpleNamespace()
    user = SimpleNamespace(id="user-1", email=None)
    character = SimpleNamespace(id="char-1", execution_mode="llm")
    slot = SimpleNamespace(status=agent_run_crud.SLOT_STATUS_RUNNING)

    monkeypatch.setattr(agent_service, "_get_owned_character", lambda *_: character)
    monkeypatch.setattr(agent_service.slot_queries, "get_assigned_slot", lambda *_: slot)

    with pytest.raises(agent_service.ActiveSlotBusyError):
        agent_service.update_credential(
            db,
            user,
            character.id,
            schemas.CredentialUpsert(model="gemma-4-31b-it"),
        )
