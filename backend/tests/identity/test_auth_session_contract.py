from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models, schemas
from app.domains.identity import dependencies as api_deps
from app.domains.identity.router import auth as auth_routes
from app.domains.identity import browser_session
from app.core import security
from app.core.desktop_loopback import DESKTOP_WEBVIEW_AUTHENTICATED_SCOPE_KEY
from app.config import settings
from app.domains.identity.service import auth as auth_service


ALLOWED_ORIGIN = "http://127.0.0.1:3000"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic/versions/20260804_0069_auth_session_expiry.py"
)


def _request(
    method: str = "GET",
    *,
    cookie_token: str | None = None,
    origin: str | None = None,
    desktop_webview_authenticated: bool = False,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie_token is not None:
        headers.append(
            (
                b"cookie",
                f"{browser_session.SESSION_COOKIE_NAME}={cookie_token}".encode(
                    "ascii"
                ),
            )
        )
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    scope = {
            "type": "http",
            "method": method,
            "path": "/api/v1/auth/me",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 3000),
            "scheme": "http",
            "query_string": b"",
        }
    if desktop_webview_authenticated:
        scope[DESKTOP_WEBVIEW_AUTHENTICATED_SCOPE_KEY] = True
    return Request(scope)


def _create_tables(engine) -> None:
    models.User.__table__.create(engine)
    models.AuthSession.__table__.create(engine)
    models.InstallationIdentity.__table__.create(engine)


def _store_user(db: Session, suffix: str = "context") -> models.User:
    user = models.User(
        id=f"user-{suffix}",
        email=f"{suffix}@example.test",
        display_name=f"User {suffix}",
        profile_setup_completed=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(autouse=True)
def browser_session_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(
        settings,
        "BROWSER_SESSION_ALLOWED_ORIGINS",
        ALLOWED_ORIGIN,
    )


def test_authenticated_session_context_resolves_bearer_without_exposing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    now = datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_service, "_utcnow", lambda: now)
    monkeypatch.setattr(security, "create_token", lambda: "raw-session-token")

    with Session(engine) as db:
        user = _store_user(db)
        issued = auth_service.issue_auth_session(
            db,
            user,
            auth_method="portfolio_review",
            expires_at=now + timedelta(hours=2),
        )

        context = api_deps.resolve_authenticated_session_context(
            _request(),
            f"Bearer {issued.token}",
            db,
        )
        stored = db.get(models.AuthSession, security.hash_token(issued.token))

        assert context.user.id == user.id
        assert context.session is stored
        assert context.session.auth_method == "portfolio_review"
        assert context.cookie_authenticated is False
        assert stored is not None
        assert stored.token_hash != issued.token
        assert issued.expires_at == now + timedelta(hours=2)


def test_authenticated_desktop_webview_resolves_claimed_installation_owner(
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        user = _store_user(db, "desktop-owner")
        now = datetime(2026, 8, 22, 0, 0, tzinfo=timezone.utc)
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="installation-desktop-owner",
                owner_user_id=user.id,
                bootstrap_state="claimed",
                claimed_at=now,
            )
        )
        db.commit()

        context = api_deps.resolve_authenticated_session_context(
            _request(desktop_webview_authenticated=True),
            None,
            db,
        )

        assert context.user.id == user.id
        assert context.session is None
        assert context.cookie_authenticated is False
        assert context.auth_method == "local_owner"

        optional = api_deps.get_optional_current_user(
            _request(desktop_webview_authenticated=True),
            None,
            db,
        )
        assert optional is not None
        assert optional.id == user.id


def test_authenticated_session_context_rejects_cookie_origin_and_token_ambiguity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    monkeypatch.setattr(security, "create_token", lambda: "cookie-session-token")

    with Session(engine) as db:
        issued = auth_service.issue_auth_session(db, _store_user(db, "cookie"))

        with pytest.raises(HTTPException) as origin_exc:
            api_deps.resolve_authenticated_session_context(
                _request("POST", cookie_token=issued.token),
                None,
                db,
            )
        with pytest.raises(HTTPException) as ambiguity_exc:
            api_deps.resolve_authenticated_session_context(
                _request(cookie_token=issued.token),
                f"Bearer {issued.token}",
                db,
            )

        context = api_deps.resolve_authenticated_session_context(
            _request("POST", cookie_token=issued.token, origin=ALLOWED_ORIGIN),
            None,
            db,
        )

        assert origin_exc.value.status_code == 403
        assert origin_exc.value.detail == "csrf_origin_invalid"
        assert ambiguity_exc.value.status_code == 401
        assert ambiguity_exc.value.detail == "ambiguous_auth"
        assert context.cookie_authenticated is True


def test_explicit_session_expiry_overrides_legacy_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    now = datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)
    expires_at = now + timedelta(hours=2)
    monkeypatch.setattr(auth_service, "_utcnow", lambda: now)
    monkeypatch.setattr(security, "create_token", lambda: "short-session-token")

    with Session(engine) as db:
        issued = auth_service.issue_auth_session(
            db,
            _store_user(db, "expiry"),
            expires_at=expires_at,
        )
        assert auth_service.get_session_for_token(db, issued.token) is not None

        monkeypatch.setattr(auth_service, "_utcnow", lambda: expires_at)
        assert auth_service.get_session_for_token(db, issued.token) is None


def test_session_issuer_rejects_already_expired_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    now = datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_service, "_utcnow", lambda: now)

    with Session(engine) as db:
        user = _store_user(db, "past-expiry")
        with pytest.raises(ValueError, match="expiry must be in the future"):
            auth_service.issue_auth_session(
                db,
                user,
                expires_at=now,
            )
        assert db.query(models.AuthSession).count() == 0


def test_legacy_null_expiry_keeps_seven_day_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    now = datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)
    token = "legacy-null-expiry"

    with Session(engine) as db:
        user = _store_user(db, "legacy")
        db.add(
            models.AuthSession(
                token_hash=security.hash_token(token),
                user_id=user.id,
                auth_method="password",
                created_at=now - auth_service.AUTH_SESSION_TTL + timedelta(seconds=1),
                expires_at=None,
            )
        )
        db.commit()

        monkeypatch.setattr(auth_service, "_utcnow", lambda: now)
        assert auth_service.get_session_for_token(db, token) is not None

        monkeypatch.setattr(
            auth_service,
            "_utcnow",
            lambda: now + timedelta(seconds=1),
        )
        assert auth_service.get_session_for_token(db, token) is None


def test_expiring_session_sets_matching_browser_cookie_max_age(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 4, 3, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_service, "_utcnow", lambda: now)
    response = Response()
    issued = auth_service.IssuedAuthSession(
        token="short-browser-session",
        user=schemas.UserRead(
            id="user-cookie-max-age",
            email="cookie-max-age@example.test",
            display_name="Cookie Max Age",
            profile_setup_completed=True,
        ),
        expires_at=now + timedelta(hours=2),
    )

    auth_routes._browser_auth_response(response, issued)

    cookie = response.headers.getlist("set-cookie")[0]
    assert "Max-Age=7200" in cookie
    assert "short-browser-session" not in str(issued.public_response())


def test_auth_session_expiry_migration_is_nullable_and_reversible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = importlib.util.spec_from_file_location(
        "auth_session_expiry_migration",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = migration
    spec.loader.exec_module(migration)

    added: list[tuple[str, object]] = []
    dropped: list[tuple[str, str]] = []
    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda table, column: added.append((table, column)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table, column: dropped.append((table, column)),
    )

    migration.upgrade()
    migration.downgrade()

    assert migration.down_revision == "20260802_0068"
    assert len(added) == 1
    table, column = added[0]
    assert table == "auth_sessions"
    assert column.name == "expires_at"
    assert column.nullable is True
    assert dropped == [("auth_sessions", "expires_at")]
