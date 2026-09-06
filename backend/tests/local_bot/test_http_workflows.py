from dataclasses import replace
from datetime import UTC, datetime

import pytest
from app.core import security
from app.domains.characters.models import Character, CharacterState
from app.domains.identity.models import User
from app.domains.local_bot import dependencies
from app.domains.local_bot.constants import MAX_READS_PER_WINDOW
from app.domains.local_bot.models import (
    AgentLocalKey,
    LocalBotActionQuotaBucket,
    LocalBotReadQuotaBucket,
)
from app.domains.local_bot.router.bot import router
from app.domains.routines.models.resident import AgentActivityLog
from app.runtime.local_bot.authentication import build_authentication_workflows
from app.runtime.local_bot.composition import build_bot_workflows
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, object_session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def bot_http():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for model in (
        User,
        Character,
        CharacterState,
        AgentLocalKey,
        AgentActivityLog,
        LocalBotActionQuotaBucket,
        LocalBotReadQuotaBucket,
    ):
        model.__table__.create(engine)
    with Session(engine) as db:
        owner = User(id="bot-http-owner", display_name="Bot Owner")
        character = Character(
            id="bot-http-character",
            owner_id=owner.id,
            name="Local Bird",
            handle="local-bird",
            persona_summary="Private persona",
            execution_mode="local",
        )
        token = "angmoo_local_http_workflow_fixture"
        key = AgentLocalKey(
            id="bot-http-key",
            character_id=character.id,
            owner_id=owner.id,
            token_hash=security.hash_token(token),
            token_prefix="fixture-prefix",
        )
        db.add_all([owner, character, key])
        db.commit()
        app = FastAPI()
        app.include_router(router)
        app.state.local_bot_authentication_workflows = build_authentication_workflows
        app.state.local_bot_workflows = build_bot_workflows
        app.dependency_overrides[dependencies.get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db, app, owner, character, key, token
    engine.dispose()


def test_bot_http_same_session_authentication_state_commit_and_private_response(
    bot_http,
):
    client, db, app, owner, character, key, token = bot_http
    observed = []
    auth = build_authentication_workflows()

    def get_character(session, character_id):
        result = auth.get_character(session, character_id)
        observed.append(("character", session, result))
        return result

    def get_user(session, owner_id):
        result = auth.get_user(session, owner_id)
        observed.append(("owner", session, result))
        return result

    app.state.local_bot_authentication_workflows = lambda: replace(
        auth, get_character=get_character, get_user=get_user
    )
    headers = {"Authorization": f"Bearer {token}"}
    read = client.get("/bot/me", headers=headers)
    assert read.status_code == 200
    assert read.json()["character"]["id"] == character.id
    assert observed == [("character", db, character), ("owner", db, owner)]
    assert object_session(key) is db and key.last_used_at is not None
    assert all(
        name not in read.text for name in (token, "token_hash", "persona_summary")
    )
    assert db.get(LocalBotReadQuotaBucket, key.id).used_count == 1
    saved = client.patch(
        "/bot/state",
        headers=headers,
        json={
            "mood": "calm",
            "summary": "HTTP update",
            "memory_note": "Retain this",
            "observation_note": "Observed from local execution",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["state"]["summary"] == "HTTP update"
    with Session(db.bind) as observer:
        assert observer.get(CharacterState, character.id).memory_note == "Retain this"
        bucket = observer.get(LocalBotActionQuotaBucket, (character.id, "state"))
        # State has a cooldown without a daily quota counter.
        assert bucket.used_count == 0 and bucket.quota_date is None
        assert bucket.last_succeeded_at is not None
        assert list(
            observer.scalars(
                select(AgentActivityLog.action_type).order_by(AgentActivityLog.id)
            )
        ) == ["observation_note_saved", "state_saved"]
    denied = client.patch(
        "/bot/state",
        headers=headers,
        json={
            "mood": "busy",
            "summary": "Must not replace state",
            "memory_note": "No write",
        },
    )
    assert denied.status_code == 429
    assert db.get(CharacterState, character.id).summary == "HTTP update"


def test_bot_http_auth_errors_precede_quota_and_preserve_status_details(bot_http):
    client, db, app, owner, character, key, token = bot_http
    for headers, detail in [
        ({}, "Authorization required"),
        ({"Authorization": "Basic value"}, "Bearer token required"),
        ({"Authorization": "Bearer wrong-prefix"}, "Invalid local bot token."),
    ]:
        response = client.get("/bot/me", headers=headers)
        assert response.status_code == 401 and response.json() == {"detail": detail}
    headers = {"Authorization": f"Bearer {token}"}
    character.execution_mode = "llm"
    db.commit()
    response = client.get("/bot/me", headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Only local mode characters can use bot API."}
    character.deleted_at = datetime.now(UTC)
    db.commit()
    response = client.get("/bot/me", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "Local bot character is not available."}
    assert key.last_used_at is None
    assert list(db.scalars(select(LocalBotReadQuotaBucket))) == []


def test_bot_http_read_quota_keeps_retry_after_and_does_not_overspend(bot_http):
    client, db, app, owner, character, key, token = bot_http
    db.add(
        LocalBotReadQuotaBucket(
            local_key_id=key.id,
            window_started_at=datetime.now(UTC),
            used_count=MAX_READS_PER_WINDOW,
        )
    )
    db.commit()
    response = client.get("/bot/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 429
    assert response.json() == {"detail": "Local bot read rate limit is reached."}
    assert int(response.headers["Retry-After"]) > 0
    assert db.get(LocalBotReadQuotaBucket, key.id).used_count == MAX_READS_PER_WINDOW
    assert list(db.scalars(select(AgentActivityLog.action_type))) == [
        "local_bot_rate_limited"
    ]


def test_both_app_factories_register_same_bot_workflows_and_shared_http_parser():
    from app.api.authorization import AuthorizationHeader, _bearer_token
    from app.domains.identity import dependencies as identity_dependencies
    from app.main import create_app
    from app.main import create_public_app

    assert identity_dependencies.AuthorizationHeader is AuthorizationHeader
    assert identity_dependencies._bearer_token is _bearer_token
    assert dependencies.AuthorizationHeader is AuthorizationHeader
    assert dependencies._bearer_token is _bearer_token
    for factory in (create_app, create_public_app):
        application = factory()
        assert application.state.local_bot_workflows is build_bot_workflows
        assert (
            application.state.local_bot_authentication_workflows
            is build_authentication_workflows
        )
