from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.domains.identity import dependencies as api_deps
from app.domains.identity.router import auth as auth_routes
from app.domains.identity import browser_session
from app.core import security
from app.config import Settings, settings
from app.runtime.startup_security import StartupSecurityError, validate_startup_security
from app.domains.identity.service import auth as auth_service


ALLOWED_ORIGIN = "http://127.0.0.1:3000"


def _user_read() -> schemas.UserRead:
    return schemas.UserRead(
        id="user-browser",
        email="browser@example.test",
        display_name="browser",
        profile_setup_completed=True,
    )


def _issued_session(token: str = "browser-session-token") -> auth_service.IssuedAuthSession:
    return auth_service.IssuedAuthSession(
        token=token,
        user=_user_read(),
        profile_setup_required=False,
    )


def _create_test_app() -> tuple[FastAPI, object]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.AuthSession.__table__.create(engine)

    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/v1")

    def get_test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[api_deps.get_db] = get_test_db
    return app, engine


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: object | None = None,
) -> httpx.Response:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url=ALLOWED_ORIGIN,
        ) as client:
            return await client.request(method, path, headers=headers, json=json)

    return asyncio.run(call())


def _store_session(engine, *, token: str = "browser-session-token") -> None:
    with Session(engine) as db:
        db.add(
            models.User(
                id="user-browser",
                email="browser@example.test",
                display_name="browser",
                profile_setup_completed=True,
            )
        )
        db.add(
            models.AuthSession(
                token_hash=security.hash_token(token),
                user_id="user-browser",
                auth_method="password",
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()


@pytest.fixture(autouse=True)
def browser_session_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(
        settings,
        "BROWSER_SESSION_ALLOWED_ORIGINS",
        ALLOWED_ORIGIN,
    )


def test_browser_auth_schemas_do_not_serialize_tokens() -> None:
    assert "token" not in schemas.AuthRead.model_fields
    assert "token" not in schemas.GoogleLoginRead.model_fields
    assert "pending_token" not in schemas.GoogleLoginRead.model_fields
    assert "pending_token" not in schemas.GoogleSignupCompleteCreate.model_fields


def test_password_login_sets_http_only_cookie_without_token_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = _create_test_app()
    monkeypatch.setattr(auth_routes.auth_service, "login", lambda *_args, **_kwargs: _issued_session())

    response = _request(
        app,
        "POST",
        "/api/v1/auth/login",
        headers={"Origin": ALLOWED_ORIGIN},
        json={"email": "browser@example.test", "password": "synthetic-password"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user": _user_read().model_dump(mode="json"),
        "profile_setup_required": False,
    }
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{browser_session.SESSION_COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api" in cookie
    assert f"Max-Age={browser_session.SESSION_MAX_AGE_SECONDS}" in cookie
    assert "browser-session-token" not in response.text


def test_login_requires_exact_origin_before_service_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = _create_test_app()
    called = False

    def unexpected_login(*_args, **_kwargs):
        nonlocal called
        called = True
        return _issued_session()

    monkeypatch.setattr(auth_routes.auth_service, "login", unexpected_login)

    missing = _request(
        app,
        "POST",
        "/api/v1/auth/login",
        json={"email": "browser@example.test", "password": "synthetic-password"},
    )
    foreign = _request(
        app,
        "POST",
        "/api/v1/auth/login",
        headers={"Origin": "https://angmoo.com.attacker.example"},
        json={"email": "browser@example.test", "password": "synthetic-password"},
    )

    assert missing.status_code == 403
    assert foreign.status_code == 403
    assert missing.json() == {"detail": "csrf_origin_invalid"}
    assert foreign.json() == {"detail": "csrf_origin_invalid"}
    assert called is False


def test_google_signup_pending_token_is_cookie_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _ = _create_test_app()
    result = auth_service.GoogleLoginResult(
        signup_required=True,
        pending_token="pending-google-token",
        expires_at=datetime(2026, 8, 1, 3, 15, tzinfo=timezone.utc),
        email="browser@example.test",
    )
    monkeypatch.setattr(
        auth_routes.auth_service,
        "login_with_google",
        lambda *_args, **_kwargs: result,
    )

    response = _request(
        app,
        "POST",
        "/api/v1/auth/google",
        headers={"Origin": ALLOWED_ORIGIN},
        json={"credential": "synthetic-google-credential"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user": None,
        "profile_setup_required": False,
        "signup_required": True,
        "expires_at": "2026-08-01T03:15:00Z",
        "email": "browser@example.test",
    }
    assert response.headers["set-cookie"].startswith(
        f"{browser_session.GOOGLE_PENDING_COOKIE_NAME}="
    )
    assert "pending-google-token" not in response.text


def test_invalid_google_signup_pending_cookie_is_deleted() -> None:
    app, _ = _create_test_app()

    response = _request(
        app,
        "POST",
        "/api/v1/auth/google/complete",
        headers={"Origin": ALLOWED_ORIGIN},
        json={
            "display_name": "browser",
            "privacy_policy_agreed": True,
            "terms_agreed": True,
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired signup token"}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{browser_session.GOOGLE_PENDING_COOKIE_NAME}=")
    assert "Max-Age=0" in cookie
    assert "Path=/api" in cookie


def test_cookie_auth_requires_origin_for_mutation_and_allows_exact_origin() -> None:
    app, engine = _create_test_app()
    _store_session(engine)
    cookie = f"{browser_session.SESSION_COOKIE_NAME}=browser-session-token"

    missing = _request(
        app,
        "PATCH",
        "/api/v1/auth/me/preferences",
        headers={"Cookie": cookie},
        json={"feed_content_filter": "posts"},
    )
    foreign = _request(
        app,
        "PATCH",
        "/api/v1/auth/me/preferences",
        headers={"Cookie": cookie, "Origin": "null"},
        json={"feed_content_filter": "posts"},
    )
    allowed = _request(
        app,
        "PATCH",
        "/api/v1/auth/me/preferences",
        headers={"Cookie": cookie, "Origin": ALLOWED_ORIGIN},
        json={"feed_content_filter": "posts"},
    )

    assert missing.status_code == 403
    assert foreign.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["feed_content_filter"] == "posts"


def test_cookie_and_user_bearer_are_rejected_as_ambiguous() -> None:
    app, engine = _create_test_app()
    _store_session(engine)

    response = _request(
        app,
        "GET",
        "/api/v1/auth/me",
        headers={
            "Cookie": f"{browser_session.SESSION_COOKIE_NAME}=browser-session-token",
            "Authorization": "Bearer browser-session-token",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "ambiguous_auth"}


def test_invalid_cookie_logout_is_idempotent_and_deletes_cookie() -> None:
    app, _ = _create_test_app()

    response = _request(
        app,
        "POST",
        "/api/v1/auth/logout",
        headers={
            "Cookie": f"{browser_session.SESSION_COOKIE_NAME}=invalid-cookie",
            "Origin": ALLOWED_ORIGIN,
        },
    )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{browser_session.SESSION_COOKIE_NAME}=")
    assert "Max-Age=0" in cookie
    assert "Path=/api" in cookie


def test_production_browser_origin_configuration_fails_closed() -> None:
    config = Settings(
        _env_file=None,
        APP_ENV="production",
        CREDENTIAL_ENCRYPTION_PROVIDER="oci_kms",
        OCI_KMS_KEY_ID="ocid1.key.synthetic",
        OCI_KMS_CRYPTO_ENDPOINT="https://synthetic.crypto.example.test",
        OCI_REGION="ap-chuncheon-1",
        OCI_AUTH_MODE="instance_principal",
        BROWSER_SESSION_ALLOWED_ORIGINS="http://angmoo.com",
        **{"APP" + "_SECRET": "synthetic-production-secret"},
    )

    with pytest.raises(StartupSecurityError, match="invalid_browser_session_origin"):
        validate_startup_security(config, kms_round_trip=lambda value: value)


def test_production_cookie_is_secure() -> None:
    response = Response()
    config = Settings(
        _env_file=None,
        APP_ENV="production",
        BROWSER_SESSION_ALLOWED_ORIGINS="https://angmoo.com",
    )

    browser_session.set_session_cookie(response, "synthetic", config=config)

    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api" in cookie
