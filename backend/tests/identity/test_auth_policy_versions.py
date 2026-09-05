from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.domains.identity import dependencies as api_deps
from app.domains.identity.router import auth as auth_routes
from app.core import security
from app.domains.identity.service import auth
from app.domains.identity import client as turnstile


EXPECTED_POLICY_VERSION = "2026-06-22"
ALLOWED_ORIGIN = "http://127.0.0.1:3000"


def _browser_request(path: str, *, cookies: dict[str, str] | None = None) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [(b"origin", ALLOWED_ORIGIN.encode("ascii"))],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 3000),
            "scheme": "http",
            "query_string": b"",
        }
    )
    if cookies:
        request.scope["headers"].append(
            (
                b"cookie",
                "; ".join(f"{key}={value}" for key, value in cookies.items()).encode(
                    "ascii"
                ),
            )
        )
    return request


def _create_tables(engine) -> None:
    models.User.__table__.create(engine)
    models.AuthSession.__table__.create(engine)
    models.AuthGoogleSignupGrant.__table__.create(engine)


def _store_auth_session(
    db: Session, *, token: str, created_at: datetime, suffix: str
) -> models.User:
    user = models.User(
        id=f"user-session-{suffix}",
        email=f"session-{suffix}@example.test",
        display_name=f"Session User {suffix}",
        profile_setup_completed=True,
    )
    db.add(user)
    db.add(
        models.AuthSession(
            token_hash=security.hash_token(token),
            user_id=user.id,
            auth_method="google",
            created_at=created_at,
        )
    )
    db.commit()
    return user


def test_auth_session_is_valid_before_absolute_ttl(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    now = datetime(2026, 7, 23, 3, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth, "_utcnow", lambda: now)

    with Session(engine) as db:
        token = "session-before-seven-days"
        user = _store_auth_session(
            db,
            token=token,
            created_at=now - auth.AUTH_SESSION_TTL + timedelta(seconds=1),
            suffix="valid",
        )

        current_user = api_deps.get_current_user_allow_incomplete(
            type("Request", (), {"method": "GET"})(),
            f"Bearer {token}",
            db,
        )

        assert current_user.id == user.id


def test_expired_auth_session_is_rejected_like_invalid_token(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    now = datetime(2026, 7, 23, 3, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(auth, "_utcnow", lambda: now)

    with Session(engine) as db:
        token = "session-at-seven-days"
        _store_auth_session(
            db,
            token=token,
            created_at=now - auth.AUTH_SESSION_TTL,
            suffix="expired",
        )

        with pytest.raises(HTTPException) as expired_exc:
            api_deps.get_current_user_allow_incomplete(
                type("Request", (), {"method": "GET"})(),
                f"Bearer {token}",
                db,
            )
        with pytest.raises(HTTPException) as invalid_exc:
            api_deps.get_current_user_allow_incomplete(
                type("Request", (), {"method": "GET"})(),
                "Bearer missing-token",
                db,
            )

        assert expired_exc.value.status_code == 401
        assert expired_exc.value.detail == "Invalid token"
        assert invalid_exc.value.status_code == 401
        assert invalid_exc.value.detail == "Invalid token"


def test_email_signup_records_current_privacy_and_terms_versions() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        result = auth.create_user(
            db,
            schemas.SignupCreate(
                email="new@example.test",
                password="password-123",
                display_name="New User",
                privacy_policy_agreed=True,
                terms_agreed=True,
            ),
        )

        user = db.get(models.User, result.user.id)
        assert user is not None
        assert user.privacy_policy_version == EXPECTED_POLICY_VERSION
        assert user.terms_version == EXPECTED_POLICY_VERSION


def test_google_signup_completion_records_current_privacy_and_terms_versions() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        pending_token = auth._create_pending_google_signup_token(
            db,
            google_sub="google-sub-1",
            email="google@example.test",
            expires_at=auth._utcnow() + timedelta(minutes=5),
        )
        result = auth.complete_google_signup(
            db,
            schemas.GoogleSignupCompleteCreate(
                display_name="Google User",
                privacy_policy_agreed=True,
                terms_agreed=True,
            ),
            pending_token=pending_token,
        )

        user = db.get(models.User, result.user.id)
        assert user is not None
        assert user.privacy_policy_version == EXPECTED_POLICY_VERSION
        assert user.terms_version == EXPECTED_POLICY_VERSION


def test_legacy_profile_setup_records_current_privacy_and_terms_versions() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        user = models.User(
            id="user-legacy",
            email="legacy@example.test",
            display_name="",
            display_name_normalized=None,
            profile_setup_completed=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        auth.update_user_display_name(
            db,
            user,
            schemas.UserDisplayNameUpdate(
                display_name="Legacy User",
                privacy_policy_agreed=True,
                terms_agreed=True,
            ),
        )

        stored = db.scalar(select(models.User).where(models.User.id == user.id))
        assert stored is not None
        assert stored.privacy_policy_version == EXPECTED_POLICY_VERSION
        assert stored.terms_version == EXPECTED_POLICY_VERSION


def test_email_signup_route_checks_turnstile_before_user_creation(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    monkeypatch.setattr(auth_routes.settings, "SIGNUP_ENABLED", True)

    def fail_turnstile(token: str | None) -> None:
        raise turnstile.TurnstileVerificationError("blocked")

    monkeypatch.setattr(
        auth_routes.turnstile,
        "verify_turnstile_or_raise",
        fail_turnstile,
    )

    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc:
            auth_routes.signup(
                schemas.SignupCreate(
                    email="blocked@example.test",
                    password="password-123",
                    display_name="Blocked User",
                    privacy_policy_agreed=True,
                    terms_agreed=True,
                    turnstile_token="bad-token",
                ),
                _browser_request("/api/v1/auth/signup"),
                Response(),
                db,
            )

        assert exc.value.status_code == 403
        assert db.scalar(select(models.User)) is None


def test_google_signup_route_checks_turnstile_before_user_creation(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    def fail_turnstile(token: str | None) -> None:
        raise turnstile.TurnstileVerificationError("blocked")

    monkeypatch.setattr(
        auth_routes.turnstile,
        "verify_turnstile_or_raise",
        fail_turnstile,
    )

    with Session(engine) as db:
        pending_token = auth._create_pending_google_signup_token(
            db,
            google_sub="google-sub-blocked",
            email="blocked-google@example.test",
            expires_at=auth._utcnow() + timedelta(minutes=5),
        )
        with pytest.raises(HTTPException) as exc:
            auth_routes.complete_google_signup(
                schemas.GoogleSignupCompleteCreate(
                    display_name="Blocked Google",
                    privacy_policy_agreed=True,
                    terms_agreed=True,
                    turnstile_token="bad-token",
                ),
                _browser_request(
                    "/api/v1/auth/google/complete",
                    cookies={"angmoo_google_signup_pending": pending_token},
                ),
                Response(),
                db,
            )

        assert exc.value.status_code == 403
        assert db.scalar(select(models.User)) is None


def test_google_account_can_signup_again_after_deleted_user_scrubbed() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        first_token = auth._create_pending_google_signup_token(
            db,
            google_sub="google-sub-repeat",
            email="repeat@example.test",
            expires_at=auth._utcnow() + timedelta(minutes=5),
        )
        first = auth.complete_google_signup(
            db,
            schemas.GoogleSignupCompleteCreate(
                display_name="Repeat User",
                privacy_policy_agreed=True,
                terms_agreed=True,
            ),
            pending_token=first_token,
        )
        first_user_id = first.user.id
        first_user = db.get(models.User, first_user_id)
        assert first_user is not None

        first_user.deleted_at = auth._utcnow()
        first_user.email = None
        first_user.google_sub = None
        first_user.display_name_normalized = None
        db.commit()

        deleted_user = db.get(models.User, first_user_id)
        assert deleted_user is not None
        assert deleted_user.deleted_at is not None
        assert deleted_user.email is None
        assert deleted_user.google_sub is None
        assert deleted_user.display_name_normalized is None

        second_token = auth._create_pending_google_signup_token(
            db,
            google_sub="google-sub-repeat",
            email="repeat@example.test",
            expires_at=auth._utcnow() + timedelta(minutes=5),
        )
        second = auth.complete_google_signup(
            db,
            schemas.GoogleSignupCompleteCreate(
                display_name="Repeat User New",
                privacy_policy_agreed=True,
                terms_agreed=True,
            ),
            pending_token=second_token,
        )

        assert second.user.id != first_user_id
        second_user = db.get(models.User, second.user.id)
        assert second_user is not None
        assert second_user.deleted_at is None
        assert second_user.email == "repeat@example.test"
        assert second_user.google_sub == "google-sub-repeat"
        assert second_user.profile_setup_completed is True


def test_google_signup_pending_token_is_consumed_once() -> None:
    import hashlib
    import hmac

    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        pending_token = auth._create_pending_google_signup_token(
            db,
            google_sub="google-sub-one-time",
            email="one-time@example.test",
            expires_at=auth._utcnow() + timedelta(minutes=5),
        )
        # An issued token retains the original keyed-MAC wire format. These
        # expected bytes deliberately use the previous HMAC constructor API.
        original_key = hmac.new(
            auth.settings.app_secret.encode("utf-8"),
            b"angmoo-google-signup-pending-key-v1",
            hashlib.sha256,
        ).digest()
        signed, signature = pending_token.rsplit(".", 1)
        assert auth._pending_signup_key() == original_key
        assert auth._b64url_decode(signature) == hmac.new(
            original_key, signed.encode("ascii"), hashlib.sha256,
        ).digest()
        payload = auth._read_pending_google_signup_token(pending_token)
        assert auth._pending_signup_jti_hash(payload["jti"]) == hmac.new(
            original_key,
            f"google-signup-jti-v1:{payload['jti']}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        first = auth.complete_google_signup(
            db,
            schemas.GoogleSignupCompleteCreate(
                display_name="One Time User",
                privacy_policy_agreed=True,
                terms_agreed=True,
            ),
            pending_token=pending_token,
        )
        first_user = db.get(models.User, first.user.id)
        assert first_user is not None
        assert first_user.google_sub == "google-sub-one-time"

        with pytest.raises(auth.InvalidGoogleSignupTokenError):
            auth.complete_google_signup(
                db,
                schemas.GoogleSignupCompleteCreate(
                    display_name="Replay User",
                    privacy_policy_agreed=True,
                    terms_agreed=True,
                ),
                pending_token=pending_token,
            )

        grants = list(db.scalars(select(models.AuthGoogleSignupGrant)))
        assert len(grants) == 1
        assert grants[0].consumed_at is not None
        assert "google-sub-one-time" not in grants[0].jti_hash
        assert "one-time@example.test" not in grants[0].jti_hash
