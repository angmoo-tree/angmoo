import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity import dependencies as api_deps
from app.domains.identity.router import auth as auth_routes
from app.core import security
from app.domains.identity.service import auth as auth_service


def _create_test_app():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.AuthSession.__table__.create(engine)

    app = FastAPI()
    app.include_router(auth_routes.router)

    def get_test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[api_deps.get_db] = get_test_db
    return app, engine


def _store_session(
    engine,
    *,
    user_id: str,
    token: str,
    auth_method: str,
    created_at: datetime | None = None,
) -> None:
    with Session(engine) as db:
        user = db.get(models.User, user_id)
        if user is None:
            db.add(
                models.User(
                    id=user_id,
                    email=f"{user_id}@example.test",
                    display_name=user_id,
                    profile_setup_completed=True,
                )
            )
        db.add(
            models.AuthSession(
                token_hash=security.hash_token(token),
                user_id=user_id,
                auth_method=auth_method,
                created_at=created_at or datetime.now(timezone.utc),
            )
        )
        db.commit()


def _post_logout(app: FastAPI, token: str) -> httpx.Response:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )

    return asyncio.run(call())


@pytest.mark.parametrize("auth_method", ["password", "google", "demo"])
def test_logout_revokes_only_current_session(auth_method: str) -> None:
    app, engine = _create_test_app()
    current_token = f"{auth_method}-current"
    other_token = f"{auth_method}-other"
    _store_session(
        engine,
        user_id=f"user-{auth_method}",
        token=current_token,
        auth_method=auth_method,
    )
    _store_session(
        engine,
        user_id=f"user-{auth_method}",
        token=other_token,
        auth_method=auth_method,
    )

    response = _post_logout(app, current_token)

    assert response.status_code == 204
    assert response.content == b""
    with Session(engine) as db:
        assert db.get(models.AuthSession, security.hash_token(current_token)) is None
        assert db.get(models.AuthSession, security.hash_token(other_token)) is not None


def test_revoked_and_invalid_logout_tokens_share_the_same_401_contract() -> None:
    app, engine = _create_test_app()
    token = "revoke-once"
    _store_session(
        engine,
        user_id="user-revoke",
        token=token,
        auth_method="google",
    )

    first = _post_logout(app, token)
    revoked = _post_logout(app, token)
    invalid = _post_logout(app, "never-issued")

    assert first.status_code == 204
    assert revoked.status_code == 401
    assert revoked.json() == {"detail": "Invalid token"}
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid token"}


def test_expired_session_cannot_be_used_for_logout(monkeypatch) -> None:
    app, engine = _create_test_app()
    now = datetime(2026, 7, 26, 3, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_service, "_utcnow", lambda: now)
    token = "expired-session"
    _store_session(
        engine,
        user_id="user-expired",
        token=token,
        auth_method="google",
        created_at=now - auth_service.AUTH_SESSION_TTL,
    )

    response = _post_logout(app, token)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}
    with Session(engine) as db:
        stored_hashes = set(db.scalars(select(models.AuthSession.token_hash)))
    assert security.hash_token(token) in stored_hashes
