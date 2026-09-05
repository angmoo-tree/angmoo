from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.domains.identity.dependencies import get_current_user
from app.api.v1.routes.agents import router
from app.core import security
from app.core.db import Base, get_db
from app.core.redaction import sanitize_support_bundle_metadata
from app.domains.identity.exceptions import CredentialResolutionError
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.identity.contracts import CredentialPurpose
from app.services import agents as agent_service


def _app_and_engine(owner: models.User):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    principal = {"user": owner}

    def test_db():
        with Session(engine) as db:
            yield db

    def test_user():
        return principal["user"]

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = test_user
    return app, engine, principal


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json: object | None = None,
) -> httpx.Response:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:3000",
        ) as client:
            return await client.request(method, path, json=json)

    return asyncio.run(call())


def _world(world_id: str, owner_id: str) -> models.World:
    return models.World(
        id=world_id,
        slug=world_id,
        owner_user_id=owner_id,
        name=world_id,
        contract_version="world-v1",
        contract_hash=f"hash-{world_id}",
        create_idempotency_key=f"create-{world_id}",
    )


def test_byok_register_metadata_replace_and_idempotent_delete_are_owner_scoped(
    monkeypatch: pytest.MonkeyPatch,
    deny_external_network,
) -> None:
    monkeypatch.setattr(security.settings, "APP_SECRET", SecretStr("l1-pr-d-secret"))
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "local")
    owner = models.User(
        id="owner-a",
        display_name="Owner A",
        display_name_normalized="owner a",
        profile_setup_completed=True,
    )
    app, engine, principal = _app_and_engine(owner)
    other = models.User(
        id="owner-b",
        display_name="Owner B",
        display_name_normalized="owner b",
        profile_setup_completed=True,
    )
    character = models.Character(
        id="character-a",
        owner_id=owner.id,
        name="Mango",
        handle="mango-l1-pr-d",
        persona_summary="",
    )
    world = _world("world-a", owner.id)
    other_world = _world("world-b", other.id)
    membership = models.WorldMembership(
        id="membership-a",
        world_id=world.id,
        user_id=owner.id,
        role="owner",
        status="active",
    )
    other_membership = models.WorldMembership(
        id="membership-b",
        world_id=other_world.id,
        user_id=other.id,
        role="owner",
        status="active",
    )
    world_character = models.WorldCharacter(
        id="world-character-a",
        world_id=world.id,
        character_id=character.id,
        membership_id=membership.id,
        status="active",
    )
    with Session(engine, expire_on_commit=False) as db:
        db.add_all(
            [
                owner,
                other,
                character,
                world,
                other_world,
                membership,
                other_membership,
                world_character,
            ]
        )
        db.commit()

    registered = _request(
        app,
        "PUT",
        "/api/v1/agents/character-a/credential",
        json={
            "provider": "google",
            "model": "gemini-3.1-flash-lite",
            "api_key": "synthetic-first-key",
            "world_id": world.id,
        },
    )
    assert registered.status_code == 200
    body = registered.json()
    assert body["owner_id"] == owner.id
    assert body["character_id"] == character.id
    assert body["purpose"] == "agent"
    assert body["enabled"] is True
    assert body["key_fingerprint"]
    assert "api_key" not in body
    assert "encrypted_api_key" not in body
    first_fingerprint = body["key_fingerprint"]

    metadata = _request(
        app,
        "GET",
        f"/api/v1/agents/{character.id}/credential?world_id={world.id}",
    )
    assert metadata.status_code == 200
    assert metadata.json() == body

    wrong_world = _request(
        app,
        "GET",
        f"/api/v1/agents/{character.id}/credential?world_id={other_world.id}",
    )
    assert wrong_world.status_code == 404

    principal["user"] = other
    cross_owner = _request(
        app,
        "GET",
        f"/api/v1/agents/{character.id}/credential",
    )
    assert cross_owner.status_code == 404
    principal["user"] = owner

    replaced = _request(
        app,
        "PUT",
        f"/api/v1/agents/{character.id}/credential",
        json={
            "provider": "google",
            "model": "gemini-3.1-flash-lite",
            "api_key": "synthetic-replacement-key",
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["key_fingerprint"] != first_fingerprint

    with Session(engine) as db:
        stored = db.get(models.LlmCredential, body["id"])
        assert stored is not None
        assert stored.encrypted_api_key.startswith("local-v2:")
        assert "synthetic-replacement-key" not in stored.encrypted_api_key

    deleted = _request(
        app,
        "DELETE",
        f"/api/v1/agents/{character.id}/credential?world_id={world.id}",
    )
    repeated = _request(
        app,
        "DELETE",
        f"/api/v1/agents/{character.id}/credential?world_id={world.id}",
    )
    assert deleted.status_code == 204
    assert repeated.status_code == 204
    with Session(engine) as db:
        stored = db.get(models.LlmCredential, body["id"])
        assert stored is not None
        assert stored.enabled is False
        assert stored.encrypted_api_key is None
        assert stored.key_fingerprint is None
        with pytest.raises(CredentialResolutionError, match="credential is disabled"):
            CredentialResolver.resolve_llm_credential(
                stored,
                purpose=CredentialPurpose.RESIDENT_LLM,
                owner_id=owner.id,
                character_id=character.id,
            )


def test_failed_replace_preserves_old_local_v2_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(security.settings, "APP_SECRET", SecretStr("l1-pr-d-secret"))
    monkeypatch.setattr(security.settings, "CREDENTIAL_ENCRYPTION_PROVIDER", "local")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = models.User(id="owner-a", display_name="Owner A")
        character = models.Character(
            id="character-a",
            owner_id=owner.id,
            name="Mango",
            handle="mango-l1-replace",
            persona_summary="",
        )
        db.add_all([owner, character])
        db.commit()
        original = agent_service.update_credential(
            db,
            owner,
            character.id,
            schemas.CredentialUpsert(api_key="synthetic-first-key"),
        )
        stored = db.get(models.LlmCredential, original.id)
        old_envelope = stored.encrypted_api_key
        old_fingerprint = stored.key_fingerprint

        def fail_encrypt(*args, **kwargs):
            raise ValueError("synthetic encryption failure")

        monkeypatch.setattr(security, "encrypt_secret", fail_encrypt)
        with pytest.raises(ValueError, match="synthetic encryption failure"):
            agent_service.update_credential(
                db,
                owner,
                character.id,
                schemas.CredentialUpsert(api_key="synthetic-replacement-key"),
            )
        db.expire_all()
        preserved = db.get(models.LlmCredential, original.id)
        assert preserved.encrypted_api_key == old_envelope
        assert preserved.key_fingerprint == old_fingerprint
        assert preserved.enabled is True


def test_support_metadata_excludes_secrets_and_private_payloads() -> None:
    synthetic_google_key = "AI" + "zaSyntheticSecretValue1234567890"
    synthetic_openai_key = "sk-" + "SyntheticSecretValue1234567890"
    payload = {
        "request_id": "request-1",
        "provider": "google",
        "api_key": synthetic_google_key,
        "encrypted_api_key": "local-v2:synthetic-envelope",
        "app_secret": "synthetic-app-secret",
        "full_prompt": "private prompt",
        "provider_response": "private provider response",
        "private_chat": [{"body": "private chat body"}],
        "nested": {
            "latency_ms": 120,
            "error": f"failed with {synthetic_openai_key}",
        },
    }

    sanitized = sanitize_support_bundle_metadata(payload)

    assert sanitized["request_id"] == "request-1"
    assert sanitized["provider"] == "google"
    assert sanitized["nested"]["latency_ms"] == 120
    assert sanitized["nested"]["error"] == "failed with [REDACTED_OPENAI_API_KEY]"
    for forbidden in (
        "api_key",
        "encrypted_api_key",
        "app_secret",
        "full_prompt",
        "provider_response",
        "private_chat",
    ):
        assert forbidden not in sanitized
