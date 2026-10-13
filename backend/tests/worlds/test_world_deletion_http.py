"""Real authentication, Origin validation and receipts after membership erasure."""
from datetime import UTC, datetime
import pytest
from fastapi import FastAPI
from app.config import settings
from app.database import get_db
from app.domains.identity.models import AuthSession
from app.core.security import hash_token
from app.domains.worlds.router_deletion import router
from app.domains.worlds.router import router as world_router
from app.runtime.world_deletion.http_gate import WorldDeletionHttpGate
from app.runtime.world_deletion.canonical_erasure import stop_admission
from worlds.test_creator_routes import _request
from worlds.test_world_deletion import environment, command, finish


@pytest.fixture
def secured(environment, monkeypatch):
    sessions, ports, effects = environment
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(settings, "BROWSER_SESSION_ALLOWED_ORIGINS", "http://127.0.0.1:3417")
    with sessions() as db:
        for user in ("owner", "other"):
            db.add(AuthSession(token_hash=hash_token("fixture-" + user), user_id=user,
                auth_method="password", created_at=datetime.now(UTC)))
        db.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(world_router, prefix="/api/v1")
    def scoped_db():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = scoped_db
    app.state.world_deletion_stop_admission = stop_admission
    app.add_middleware(WorldDeletionHttpGate, sessions=sessions)
    return app, sessions, ports


def call(app, method, path, *, user="owner", origin="http://127.0.0.1:3417", **kwargs):
    cookies = {"angmoo_browser_session": "fixture-" + user} if user else {}
    headers = {"Origin": origin} if origin else {}
    return _request(app, method, "/api/v1" + path, cookies=cookies, headers=headers, **kwargs)


@pytest.mark.parametrize("user,origin,expected", [(None, None, 401), ("other", "http://127.0.0.1:3417", 404),
    ("owner", None, 403), ("owner", "https://foreign.example.test", 403)])
def test_real_cookie_auth_and_origin_do_not_accept_unauthorized_erasure(secured, user, origin, expected):
    app, sessions, _ = secured
    response = call(app, "DELETE", "/worlds/a", user=user, origin=origin, json=command().model_dump())
    assert response.status_code == expected
    from app.domains.worlds.models_deletion import WorldDeletionRequest
    from sqlalchemy import select
    with sessions() as db:
        assert db.scalar(select(WorldDeletionRequest)) is None


def test_real_api_intent_closes_world_but_receipt_remains_owner_only(secured):
    app, sessions, ports = secured
    body = command().model_dump()
    preview = call(app, "GET", "/worlds/a/deletion-preview")
    assert preview.status_code == 200 and preview.json()["stored_name"] == "World a"
    response = call(app, "DELETE", "/worlds/a", json=body)
    assert response.status_code == 202 and response.json()["state"] == "accepted"
    identifier = response.json()["request_id"]
    assert call(app, "GET", "/worlds/a").json() == {"detail": "world_deleting"}
    assert call(app, "GET", "/worlds/b").status_code == 200
    assert call(app, "GET", "/world-deletions").json()[0]["request_id"] == identifier
    assert call(app, "DELETE", "/worlds/a", json=body).json()["request_id"] == identifier
    assert finish(sessions, ports).state == "completed"
    assert call(app, "GET", "/worlds/a").status_code == 410
    assert call(app, "GET", "/worlds/a", user=None).status_code == 404
    receipt = call(app, "GET", "/world-deletions/" + identifier)
    assert receipt.status_code == 200 and receipt.json()["state"] == "completed"
    assert set(receipt.json()) == {"request_id", "world_id", "state", "accepted_at", "completed_at", "can_retry"}
    assert call(app, "GET", "/world-deletions/" + identifier, user="other").status_code == 404
    assert call(app, "GET", "/world-deletions/" + identifier, user=None).status_code == 401
    assert call(app, "GET", "/world-deletions").json() == []
    assert call(app, "DELETE", "/worlds/a", json=body).json()["state"] == "completed"


def test_intent_blocks_send_retry_text_only_media_memory_and_new_registration(secured):
    app, _, _ = secured
    assert call(app, "DELETE", "/worlds/a", json=command().model_dump()).status_code == 202
    for path in ("/worlds/a/chat/threads/thread/messages", "/worlds/a/chat/threads/thread/requests/request/retry",
        "/worlds/a/world-characters/actor/memory/save", "/worlds/a/my-profile/media", "/worlds/a/icon",
        "/worlds/a/characters", "/media/worlds/a/posts/post/image-generation/retry"):
        response = call(app, "POST", path, json={"retry_without_image": True})
        assert response.status_code == 409 and response.json() == {"detail": "world_deleting"}


@pytest.mark.parametrize("consent", [False, "true", 1, None])
def test_consent_is_an_explicit_boolean_not_a_coerced_value(secured, consent):
    app, _, _ = secured
    body = command().model_dump()
    body["consent"] = consent
    assert call(app, "DELETE", "/worlds/a", json=body).status_code == 422
