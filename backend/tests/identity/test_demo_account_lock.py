import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException, Request, Response

from app import models, schemas
from app.domains.identity import dependencies as api_deps
from app.api.v1.routes import agents as agent_routes
from app.domains.characters import router as character_routes
from app.domains.identity.router import auth as auth_routes
from app.config import settings
from app.cruds import agents as agent_crud
from app.runtime.characters import management as agent_service
from app.domains.identity.service import auth as auth_service
from app.domains.identity.service import demo_access as demo_lock
from app.services import local_bot as local_bot_service
from app.public_main import app as public_app


DEMO_EMAIL = "demo-kimarin@angmoo.test"


def _user(email: str = DEMO_EMAIL) -> models.User:
    return models.User(
        id="user-demo",
        email=email,
        display_name="Demo User",
        profile_setup_completed=True,
        feed_content_filter="all",
        is_admin=False,
    )


def _character() -> models.Character:
    return models.Character(
        id="char-demo",
        owner_id="user-demo",
        name="Kima Rin",
        handle="kima_rin",
        persona_summary="Demo character",
    )


def _request(method: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/synthetic",
            "headers": [(b"origin", b"http://127.0.0.1:3000")],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 3000),
            "scheme": "http",
            "query_string": b"",
        }
    )


def _session(auth_method: str = "demo") -> SimpleNamespace:
    return SimpleNamespace(auth_method=auth_method)


@pytest.fixture(autouse=True)
def locked_demo_email(monkeypatch):
    monkeypatch.setattr(settings, "LOCKED_DEMO_USER_EMAILS", DEMO_EMAIL)


def test_demo_lock_normalizes_configured_email():
    user = _user("  Demo-Kimarin@Angmoo.Test  ")

    assert demo_lock.is_locked_demo_user(user)


def test_demo_principal_accepts_session_method_or_locked_email():
    assert demo_lock.is_read_only_demo_principal(
        _user("normal@example.test"),
        auth_method="  DeMo  ",
    )
    assert demo_lock.is_read_only_demo_principal(
        _user("  Demo-Kimarin@Angmoo.Test  "),
        auth_method="google",
    )
    assert not demo_lock.is_read_only_demo_principal(
        _user("normal@example.test"),
        auth_method="google",
    )


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_demo_principal_allows_safe_http_methods(method):
    demo_lock.ensure_demo_request_allowed(
        _user(),
        auth_method="demo",
        method=method,
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_demo_principal_blocks_unsafe_http_methods(method):
    with pytest.raises(
        demo_lock.DemoAccountLockedError,
        match=demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE,
    ):
        demo_lock.ensure_demo_request_allowed(
            _user(),
            auth_method="demo",
            method=method,
        )


def test_normal_principal_remains_mutable():
    demo_lock.ensure_demo_request_allowed(
        _user("normal@example.test"),
        auth_method="google",
        method="POST",
    )


def test_demo_session_dependency_allows_get(monkeypatch):
    user = _user("normal@example.test")
    monkeypatch.setattr(
        auth_service,
        "get_user_session_for_token",
        lambda _db, _token: (user, _session("demo")),
    )

    assert (
        api_deps.get_current_user_allow_incomplete(
            _request("GET"),
            "Bearer demo-token",
            object(),
        )
        is user
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_demo_session_dependency_blocks_mutation(monkeypatch, method):
    user = _user("normal@example.test")
    monkeypatch.setattr(
        auth_service,
        "get_user_session_for_token",
        lambda _db, _token: (user, _session("demo")),
    )

    with pytest.raises(HTTPException) as exc_info:
        api_deps.get_current_user_allow_incomplete(
            _request(method),
            "Bearer demo-token",
            object(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE


def test_locked_email_dependency_blocks_google_session_mutation(monkeypatch):
    user = _user()
    monkeypatch.setattr(
        auth_service,
        "get_user_session_for_token",
        lambda _db, _token: (user, _session("google")),
    )

    with pytest.raises(HTTPException) as exc_info:
        api_deps.get_current_user_allow_incomplete(
            _request("PATCH"),
            "Bearer google-token",
            object(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE


def test_optional_demo_dependency_blocks_mutation_when_token_is_present(monkeypatch):
    user = _user("normal@example.test")
    monkeypatch.setattr(
        auth_service,
        "get_user_session_for_token",
        lambda _db, _token: (user, _session("demo")),
    )

    with pytest.raises(HTTPException) as exc_info:
        api_deps.get_optional_current_user(
            _request("DELETE"),
            "Bearer demo-token",
            object(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE


def test_incomplete_demo_profile_is_blocked_before_profile_gate(monkeypatch):
    user = _user("normal@example.test")
    user.profile_setup_completed = False
    monkeypatch.setattr(
        auth_service,
        "get_user_session_for_token",
        lambda _db, _token: (user, _session("demo")),
    )

    with pytest.raises(HTTPException) as exc_info:
        api_deps.get_current_user(
            _request("POST"),
            "Bearer demo-token",
            object(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE


def test_demo_mutation_is_blocked_before_route_handler(monkeypatch):
    user = _user("normal@example.test")
    called = False
    test_app = FastAPI()

    @test_app.patch("/mutation")
    def mutation(
        current_user: models.User = Depends(
            api_deps.get_current_user_allow_incomplete
        ),
    ) -> dict[str, str]:
        nonlocal called
        called = True
        return {"user_id": current_user.id}

    monkeypatch.setattr(
        auth_service,
        "get_user_session_for_token",
        lambda _db, _token: (user, _session("demo")),
    )
    test_app.dependency_overrides[api_deps.get_db] = lambda: object()

    async def call_mutation() -> httpx.Response:
        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.patch(
                "/mutation",
                headers={"Authorization": "Bearer demo-token"},
            )

    response = asyncio.run(call_mutation())

    assert response.status_code == 403
    assert response.json()["detail"] == demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE
    assert called is False


def test_locked_demo_local_bot_is_blocked_before_last_used_update(monkeypatch):
    user = _user()
    character = SimpleNamespace(
        id="char-demo",
        deleted_at=None,
        execution_mode="local",
    )
    local_key = SimpleNamespace(
        character_id=character.id,
        owner_id=user.id,
        last_used_at=None,
    )
    marked_used = False

    class FakeDb:
        def get(self, model, key):
            if model is models.Character and key == character.id:
                return character
            if model is models.User and key == user.id:
                return user
            return None

    monkeypatch.setattr(
        agent_crud,
        "get_active_local_key_by_hash",
        lambda _db, _token_hash: local_key,
    )

    def mark_used(*_args, **_kwargs):
        nonlocal marked_used
        marked_used = True
        return local_key

    monkeypatch.setattr(agent_crud, "mark_local_key_used", mark_used)

    with pytest.raises(
        local_bot_service.LocalBotForbiddenError,
        match=demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE,
    ):
        local_bot_service.authenticate_local_bot(
            FakeDb(),
            f"{agent_service.LOCAL_KEY_PREFIX}synthetic",
        )

    assert marked_used is False
    assert local_key.last_used_at is None


def test_normal_local_bot_authentication_still_updates_last_used(monkeypatch):
    user = _user("normal@example.test")
    character = SimpleNamespace(
        id="char-normal",
        deleted_at=None,
        execution_mode="local",
    )
    local_key = SimpleNamespace(
        character_id=character.id,
        owner_id=user.id,
    )
    marked_used = False

    class FakeDb:
        def get(self, model, key):
            if model is models.Character and key == character.id:
                return character
            if model is models.User and key == user.id:
                return user
            return None

    monkeypatch.setattr(
        agent_crud,
        "get_active_local_key_by_hash",
        lambda _db, _token_hash: local_key,
    )

    def mark_used(*_args, **_kwargs):
        nonlocal marked_used
        marked_used = True
        return local_key

    monkeypatch.setattr(agent_crud, "mark_local_key_used", mark_used)

    context = local_bot_service.authenticate_local_bot(
        FakeDb(),
        f"{agent_service.LOCAL_KEY_PREFIX}synthetic",
    )

    assert context.user is user
    assert context.character is character
    assert marked_used is True


def test_public_demo_login_route_is_absent():
    async def call_removed_route() -> httpx.Response:
        transport = httpx.ASGITransport(app=public_app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/auth/demo-login",
                headers={"Origin": "http://127.0.0.1:3000"},
            )

    response = asyncio.run(call_removed_route())

    assert response.status_code == 404


def test_account_delete_route_returns_403_for_locked_demo_user():
    data = schemas.AccountDeletionCreate(
        confirmation=auth_service.ACCOUNT_DELETE_CONFIRMATION
    )

    with pytest.raises(HTTPException) as exc_info:
        auth_routes.delete_me(
            data=data,
            response=Response(),
            db=object(),
            user=_user(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE


def test_agent_route_returns_403_for_locked_demo_error(monkeypatch):
    def raise_locked(*args, **kwargs):
        raise agent_service.DemoAccountLockedError(demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE)

    monkeypatch.setattr(character_routes.character_service, "update_profile", raise_locked)

    with pytest.raises(HTTPException) as exc_info:
        agent_routes.update_profile(
            "char-demo",
            schemas.AgentProfileUpdate(one_liner="locked"),
            db=object(),
            user=_user(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == demo_lock.DEMO_ACCOUNT_LOCKED_MESSAGE


def test_agent_service_blocks_profile_update_after_ownership_check(monkeypatch):
    from app.domains.characters.service import mutations

    monkeypatch.setattr(
        mutations,
        "_get_owned_character",
        lambda db, user, character_id: _character(),
    )

    with pytest.raises(agent_service.DemoAccountLockedError):
        agent_service.update_profile(
            object(),
            _user(),
            "char-demo",
            schemas.AgentProfileUpdate(one_liner="locked"),
        )
