from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.identity.router import auth as auth_routes
from app.domains.identity import browser_session
from app.core import security
from app.core.db import Base, get_db
from app.domains.identity.router.local import router
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.models import LocalOwnerBootstrapChallenge
from app.domains.identity.service.local_owner import LocalIdentityService as SqlAlchemyIdentityRepository


ORIGIN = "http://127.0.0.1:3000"
FRONTEND_HEADERS = {
    "Origin": ORIGIN,
    "Host": "127.0.0.1:3000",
    "X-Angmoo-Frontend-Origin": ORIGIN,
    "Sec-Fetch-Site": "same-origin",
}


def _app_and_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(auth_routes.public_router, prefix="/api/v1")

    def test_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    return app, engine


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    json: object | None = None,
):
    async def call():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as client:
            return await client.request(
                method,
                path,
                headers=headers,
                cookies=cookies,
                json=json,
            )

    return asyncio.run(call())


def _challenge_cookie(response: httpx.Response) -> str:
    return response.cookies[browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME]


def test_runtime_prepare_creates_only_an_unclaimed_installation_identity() -> None:
    _, engine = _app_and_engine()
    now = datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)

    with Session(engine) as db:
        repository = SqlAlchemyIdentityRepository(db)
        first = repository.ensure_local_installation_identity(now=now)
        second = repository.ensure_local_installation_identity(now=now)

        identity = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
        assert identity is not None
        assert first == second == identity.installation_id
        assert identity.bootstrap_state == "unclaimed"
        assert identity.owner_user_id is None
        assert db.scalar(select(models.User.id)) is None
        assert db.scalar(select(LocalOwnerBootstrapChallenge.challenge_hash)) is None


def test_clean_bootstrap_claims_one_owner_and_stores_only_session_hash() -> None:
    app, engine = _app_and_engine()

    status_response = _request(
        app,
        "GET",
        "/api/v1/auth/local/bootstrap",
        headers={
            "Host": "127.0.0.1:3000",
            "X-Angmoo-Frontend-Origin": ORIGIN,
        },
    )
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "unclaimed"

    challenge_response = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/challenge",
        headers=FRONTEND_HEADERS,
    )
    assert challenge_response.status_code == 201
    challenge_cookie = challenge_response.headers["set-cookie"]
    assert "HttpOnly" in challenge_cookie
    assert "SameSite=lax" in challenge_cookie
    assert "Path=/api" in challenge_cookie
    challenge_token = _challenge_cookie(challenge_response)
    assert challenge_token not in challenge_response.text

    claim_response = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/claim",
        headers=FRONTEND_HEADERS,
        cookies={
            browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME: challenge_token,
        },
        json={
            "display_name": "Local Owner",
            "local_label": "Test PC",
            "privacy_acknowledged": True,
        },
    )
    assert claim_response.status_code == 201
    payload = claim_response.json()
    assert payload["user"]["display_name"] == "Local Owner"
    assert "token" not in payload
    session_token = claim_response.cookies[browser_session.SESSION_COOKIE_NAME]
    assert session_token not in claim_response.text

    with Session(engine) as db:
        identity = db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY)
        assert identity is not None
        assert identity.bootstrap_state == "claimed"
        assert identity.local_label == "Test PC"
        assert identity.owner_user_id == payload["user"]["id"]
        assert db.get(models.AuthSession, security.hash_token(session_token)) is not None
        assert db.scalar(select(models.AuthSession.token_hash)) != session_token
        challenge = db.get(
            LocalOwnerBootstrapChallenge,
            security.hash_token(challenge_token),
        )
        assert challenge is not None
        assert challenge.consumed_at is not None


def test_existing_data_candidate_is_adopted_without_rewriting_foreign_keys() -> None:
    app, engine = _app_and_engine()
    with Session(engine) as db:
        db.add(
            models.User(
                id="user-existing",
                display_name="Existing Owner",
                display_name_normalized="existing owner",
                profile_setup_completed=True,
            )
        )
        db.add(
            models.Character(
                id="char-existing",
                owner_id="user-existing",
                name="Existing",
                handle="existing",
                persona_summary="existing",
            )
        )
        db.commit()

    status_response = _request(
        app,
        "GET",
        "/api/v1/auth/local/bootstrap",
        headers={
            "Host": "127.0.0.1:3000",
            "X-Angmoo-Frontend-Origin": ORIGIN,
        },
    )
    candidate = status_response.json()["candidates"][0]
    assert candidate == {
        "user_id": "user-existing",
        "display_name": "Existing Owner",
        "character_count": 1,
        "world_count": 0,
        "credential_count": 0,
        "suggested": True,
    }

    challenge = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/challenge",
        headers=FRONTEND_HEADERS,
    )
    response = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/claim",
        headers=FRONTEND_HEADERS,
        cookies={
            browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME: _challenge_cookie(
                challenge
            )
        },
        json={
            "owner_user_id": "user-existing",
            "privacy_acknowledged": True,
        },
    )
    assert response.status_code == 201
    with Session(engine) as db:
        assert db.get(models.Character, "char-existing").owner_id == "user-existing"
        assert db.get(InstallationIdentity, LOCAL_INSTALLATION_KEY).owner_user_id == "user-existing"


def test_bootstrap_closes_after_claim_and_replayed_challenge_loses_race() -> None:
    app, _ = _app_and_engine()
    challenge = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/challenge",
        headers=FRONTEND_HEADERS,
    )
    token = _challenge_cookie(challenge)
    claim = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/claim",
        headers=FRONTEND_HEADERS,
        cookies={browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME: token},
        json={"display_name": "Owner", "privacy_acknowledged": True},
    )
    assert claim.status_code == 201

    replay = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/claim",
        headers=FRONTEND_HEADERS,
        cookies={browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME: token},
        json={"display_name": "Other", "privacy_acknowledged": True},
    )
    closed = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/challenge",
        headers=FRONTEND_HEADERS,
    )
    assert replay.status_code == 409
    assert replay.json() == {"detail": "bootstrap_race_lost"}
    assert closed.status_code == 409
    assert closed.json() == {"detail": "bootstrap_closed"}


def test_local_session_reentry_issues_opaque_cookie_for_claimed_owner() -> None:
    app, engine = _app_and_engine()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        user = models.User(
            id="user-owner",
            display_name="Owner",
            display_name_normalized="owner",
            profile_setup_completed=True,
        )
        db.add(user)
        db.add(
            InstallationIdentity(
                singleton_key=LOCAL_INSTALLATION_KEY,
                installation_id="installation-test",
                owner_user_id=user.id,
                bootstrap_state="claimed",
                claimed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

    response = _request(
        app,
        "POST",
        "/api/v1/auth/local/session",
        headers=FRONTEND_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-owner"
    assert "token" not in response.json()
    assert "HttpOnly" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://attacker.invalid", "Host": "127.0.0.1:3000"},
        {"Origin": ORIGIN, "Host": "attacker.invalid"},
        {
            "Origin": ORIGIN,
            "Host": "127.0.0.1:3000",
            "X-Angmoo-Frontend-Origin": "http://localhost:3000",
        },
        {
            "Origin": ORIGIN,
            "Host": "127.0.0.1:3000",
            "X-Angmoo-Frontend-Origin": ORIGIN,
            "Sec-Fetch-Site": "cross-site",
        },
    ],
)
def test_local_mutations_reject_invalid_origin_host_and_cross_site(headers) -> None:
    app, _ = _app_and_engine()
    response = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/challenge",
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "csrf_origin_invalid"}


def test_expired_challenge_is_rejected_without_creating_owner() -> None:
    _, engine = _app_and_engine()
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        repository = SqlAlchemyIdentityRepository(db)
        challenge = repository.create_bootstrap_challenge(now=now)
        stored = db.get(
            LocalOwnerBootstrapChallenge,
            security.hash_token(challenge.token),
        )
        stored.expires_at = now - timedelta(seconds=1)
        db.commit()
        with pytest.raises(Exception, match="invalid or expired bootstrap challenge"):
            repository.claim_local_owner(
                challenge_token=challenge.token,
                owner_user_id=None,
                display_name="Owner",
                local_label=None,
                privacy_acknowledged=True,
                now=now,
            )
        assert db.scalar(select(models.User)) is None



def test_multiple_existing_users_are_never_preselected() -> None:
    app, engine = _app_and_engine()
    with Session(engine) as db:
        db.add_all(
            [
                models.User(
                    id="user-first",
                    display_name="First",
                    display_name_normalized="first",
                    profile_setup_completed=True,
                ),
                models.User(
                    id="user-second",
                    display_name="Second",
                    display_name_normalized="second",
                    profile_setup_completed=True,
                ),
            ]
        )
        db.commit()

    response = _request(
        app,
        "GET",
        "/api/v1/auth/local/bootstrap",
        headers={
            "Host": "127.0.0.1:3000",
            "X-Angmoo-Frontend-Origin": ORIGIN,
        },
    )
    assert response.status_code == 200
    assert len(response.json()["candidates"]) == 2
    assert not any(candidate["suggested"] for candidate in response.json()["candidates"])


def test_valid_challenge_has_bounded_invalid_claim_attempts() -> None:
    app, engine = _app_and_engine()
    challenge_response = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/challenge",
        headers=FRONTEND_HEADERS,
    )
    token = _challenge_cookie(challenge_response)
    for _ in range(5):
        response = _request(
            app,
            "POST",
            "/api/v1/auth/local/bootstrap/claim",
            headers=FRONTEND_HEADERS,
            cookies={browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME: token},
            json={"owner_user_id": "missing-user", "privacy_acknowledged": True},
        )
        assert response.status_code == 422

    rejected = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/claim",
        headers=FRONTEND_HEADERS,
        cookies={browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME: token},
        json={"display_name": "Owner", "privacy_acknowledged": True},
    )
    assert rejected.status_code == 401
    assert rejected.json() == {"detail": "bootstrap_challenge_invalid"}
    with Session(engine) as db:
        challenge = db.get(LocalOwnerBootstrapChallenge, security.hash_token(token))
        assert challenge is not None
        assert challenge.attempt_count == 5


def test_logout_revokes_local_session_and_expires_cookie() -> None:
    app, engine = _app_and_engine()
    challenge = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/challenge",
        headers=FRONTEND_HEADERS,
    )
    claim = _request(
        app,
        "POST",
        "/api/v1/auth/local/bootstrap/claim",
        headers=FRONTEND_HEADERS,
        cookies={browser_session.BOOTSTRAP_CHALLENGE_COOKIE_NAME: _challenge_cookie(challenge)},
        json={"display_name": "Owner", "privacy_acknowledged": True},
    )
    token = claim.cookies[browser_session.SESSION_COOKIE_NAME]
    response = _request(
        app,
        "POST",
        "/api/v1/auth/logout",
        headers=FRONTEND_HEADERS,
        cookies={browser_session.SESSION_COOKIE_NAME: token},
    )
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    with Session(engine) as db:
        assert db.get(models.AuthSession, security.hash_token(token)) is None


def test_expired_local_session_cannot_authenticate() -> None:
    app, engine = _app_and_engine()
    now = datetime.now(timezone.utc)
    token = security.create_token()
    with Session(engine) as db:
        db.add(
            models.User(
                id="user-expired",
                display_name="Expired",
                display_name_normalized="expired",
                profile_setup_completed=True,
            )
        )
        db.add(
            models.AuthSession(
                token_hash=security.hash_token(token),
                user_id="user-expired",
                auth_method="local_owner",
                created_at=now - timedelta(days=8),
                expires_at=now - timedelta(seconds=1),
            )
        )
        db.commit()
    response = _request(
        app,
        "GET",
        "/api/v1/auth/me",
        cookies={browser_session.SESSION_COOKIE_NAME: token},
    )
    assert response.status_code == 401
