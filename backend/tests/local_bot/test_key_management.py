from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core import security
from app.domains.characters.models import Character
from app.domains.identity.models import User
from app.domains.local_bot import dependencies
from app.domains.local_bot.models import AgentLocalKey
from app.domains.local_bot.repository.keys import get_active_local_key_by_hash
from app.domains.local_bot.router.keys import router
from app.domains.routines.models.resident import AgentActivityLog
from app.runtime.local_bot.keys import build_local_key_workflows
from app.domains.local_bot.service.authentication import authenticate_local_bot
from app.runtime.local_bot.authentication import build_authentication_workflows


@pytest.fixture
def key_owner():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (User, Character, AgentLocalKey, AgentActivityLog):
        model.__table__.create(engine)
    with Session(engine) as db:
        owner = User(id="key-owner", display_name="Key Owner")
        db.add_all([owner, User(id="foreign-owner", display_name="Foreign Owner")])
        db.flush()
        for character_id, execution_mode, owner_id in [
            ("local-bird", "local", owner.id),
            ("server-bird", "llm", owner.id),
            ("foreign-bird", "local", "foreign-owner"),
        ]:
            db.add(Character(id=character_id, owner_id=owner_id, name=character_id,
                             handle=character_id, persona_summary="Fixture bird",
                             execution_mode=execution_mode))
        db.commit()
        app = FastAPI()
        app.include_router(router)
        app.state.local_key_workflows = build_local_key_workflows
        app.dependency_overrides[dependencies.get_current_user] = lambda: owner
        app.dependency_overrides[dependencies.get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db
    engine.dispose()


def test_local_key_http_rotation_authentication_and_revocation_share_persisted_identity(key_owner):
    client, db = key_owner
    assert client.get("/agents/local-bird/local-connection").json()["has_active_key"] is False
    first = client.post("/agents/local-bird/local-key")
    assert first.status_code == 201
    token = first.json()["token"]
    assert token.startswith("angmoo_local_")
    key = get_active_local_key_by_hash(db, security.hash_token(token))
    assert key is not None and key.token_hash != token
    assert key.token_prefix == token[:24] + "..."
    authenticated = authenticate_local_bot(db, token, workflows=build_authentication_workflows())
    assert authenticated.local_key is key
    assert key.last_used_at is not None
    read = client.get("/agents/local-bird/local-connection")
    assert read.status_code == 200 and "token" not in read.json()
    assert read.json()["last_used_at"] is not None
    second = client.post("/agents/local-bird/local-key")
    assert second.status_code == 201
    replacement = second.json()["token"]
    assert replacement != token
    assert get_active_local_key_by_hash(db, security.hash_token(token)) is None
    assert client.delete("/agents/local-bird/local-key").status_code == 204
    assert get_active_local_key_by_hash(db, security.hash_token(replacement)) is None
    with Session(db.bind) as observer:
        keys = list(observer.scalars(select(AgentLocalKey)))
        assert len(keys) == 2
        assert all(not row.enabled and row.revoked_at is not None for row in keys)
        actions = list(observer.scalars(select(AgentActivityLog.action_type).order_by(AgentActivityLog.id)))
        assert actions == ["local_key_issued", "local_key_issued", "local_key_revoked"]


def test_local_key_http_rejects_foreign_owner_and_server_mode_without_key_or_log(key_owner):
    client, db = key_owner
    for method, suffix in [(client.get, "local-connection"), (client.post, "local-key"), (client.delete, "local-key")]:
        assert method(f"/agents/foreign-bird/{suffix}").status_code == 404
        assert method(f"/agents/server-bird/{suffix}").status_code == 409
    assert list(db.scalars(select(AgentLocalKey))) == []
    assert list(db.scalars(select(AgentActivityLog))) == []
