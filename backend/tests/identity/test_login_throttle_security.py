from app.domains.identity import browser_session
from datetime import UTC, datetime
from statistics import median
from time import perf_counter

from fastapi import HTTPException, Response
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import models, schemas
from app.domains.identity.router import auth as auth_routes
from app.core import security
from app.domains.identity.service import auth as auth_service
from app.domains.identity.service import login_throttle


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.AuthSession.__table__.create(engine)
    models.AuthLoginThrottleBucket.__table__.create(engine)
    return Session(engine)


def _user(*, user_id: str, email: str, password: str | None) -> models.User:
    return models.User(
        id=user_id,
        email=email,
        password_hash=security.hash_password(password) if password is not None else None,
        display_name=user_id,
        display_name_normalized=user_id,
        profile_setup_completed=True,
        feed_content_filter="all",
    )


def test_missing_and_google_only_users_run_one_password_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    db.add(_user(user_id="user-google", email="google@example.com", password=None))
    malformed = _user(
        user_id="user-malformed",
        email="malformed@example.com",
        password=None,
    )
    malformed.password_hash = "legacy-unsupported-hash"
    db.add(malformed)
    db.commit()
    calls: list[str | None] = []

    def fake_verify(password: str, password_hash: str | None) -> bool:
        calls.append(password_hash)
        return False

    monkeypatch.setattr(auth_service.security, "verify_password", fake_verify)

    for email in (
        "missing@example.com",
        "google@example.com",
        "malformed@example.com",
    ):
        with pytest.raises(auth_service.InvalidCredentialsError):
            auth_service.login(
                db,
                schemas.LoginCreate(email=email, password="wrong-password"),
                source="198.51.100.10",
            )

    assert calls == [
        auth_service.DUMMY_PASSWORD_HASH,
        auth_service.DUMMY_PASSWORD_HASH,
        auth_service.DUMMY_PASSWORD_HASH,
    ]
    assert auth_service._is_current_password_hash(auth_service.DUMMY_PASSWORD_HASH)


def test_login_throttle_persists_hashed_subjects_and_returns_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    monkeypatch.setattr(
        auth_service.security,
        "verify_password",
        lambda _password, _password_hash: False,
    )
    data = schemas.LoginCreate(email="target@example.com", password="wrong-password")

    for _ in range(5):
        with pytest.raises(auth_service.InvalidCredentialsError):
            auth_service.login(db, data, source="198.51.100.20")

    with pytest.raises(auth_service.LoginRateLimitedError) as exc:
        auth_service.login(db, data, source="198.51.100.20")
    assert 1 <= exc.value.retry_after_seconds <= 60

    rows = list(db.scalars(select(models.AuthLoginThrottleBucket)))
    assert {row.scope for row in rows} == {"source", "account_source"}
    serialized = " ".join(f"{row.scope}:{row.subject_hash}" for row in rows)
    assert "target@example.com" not in serialized
    assert "198.51.100.20" not in serialized


def test_successful_login_resets_only_account_source_bucket() -> None:
    db = _session()
    db.add(_user(user_id="user-password", email="user@example.com", password="correct"))
    db.commit()
    data = schemas.LoginCreate(email="user@example.com", password="wrong")

    with pytest.raises(auth_service.InvalidCredentialsError):
        auth_service.login(db, data, source="198.51.100.30")

    result = auth_service.login(
        db,
        schemas.LoginCreate(email="user@example.com", password="correct"),
        source="198.51.100.30",
    )
    assert result.user.id == "user-password"

    rows = {
        row.scope: row
        for row in db.scalars(select(models.AuthLoginThrottleBucket))
    }
    assert rows["source"].failure_count == 1
    assert rows["account_source"].failure_count == 0
    assert rows["account_source"].blocked_until is None


def test_login_source_ignores_forwarded_header_from_untrusted_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domains.identity import browser_session as login_throttle

    monkeypatch.setattr(login_throttle.settings, "LOGIN_TRUSTED_PROXY_CIDRS", "")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [(b"x-forwarded-for", b"203.0.113.8")],
            "client": ("198.51.100.40", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )
    assert login_throttle.request_source(request) == "198.51.100.40"


def test_login_source_uses_forwarded_chain_only_for_trusted_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.domains.identity import browser_session as login_throttle

    monkeypatch.setattr(
        login_throttle.settings,
        "LOGIN_TRUSTED_PROXY_CIDRS",
        "127.0.0.0/8,10.0.0.0/8",
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.5")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )
    assert login_throttle.request_source(request) == "203.0.113.9"


def test_throttle_backoff_matches_approved_thresholds() -> None:
    now = datetime(2026, 7, 26, 3, 0, tzinfo=UTC)
    assert login_throttle.blocked_until_for_failure_count(4, now=now) is None
    assert (
        login_throttle.blocked_until_for_failure_count(5, now=now) - now
    ).total_seconds() == 60
    assert (
        login_throttle.blocked_until_for_failure_count(10, now=now) - now
    ).total_seconds() == 300
    assert (
        login_throttle.blocked_until_for_failure_count(20, now=now) - now
    ).total_seconds() == 1800


def test_missing_and_existing_account_login_timings_have_similar_medians() -> None:
    db = _session()
    db.add(_user(user_id="user-timing", email="timing@example.com", password="correct"))
    db.commit()

    def samples(email: str, source_prefix: str) -> list[float]:
        durations: list[float] = []
        for index in range(5):
            started_at = perf_counter()
            with pytest.raises(auth_service.InvalidCredentialsError):
                auth_service.login(
                    db,
                    schemas.LoginCreate(email=email, password="wrong-password"),
                    source=f"{source_prefix}-{index}",
                )
            durations.append(perf_counter() - started_at)
        return durations

    existing = samples("timing@example.com", "existing")
    missing = samples("missing@example.com", "missing")
    ratio = max(median(existing), median(missing)) / min(
        median(existing), median(missing)
    )
    assert ratio < 2.5


def test_login_route_returns_generic_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rate_limited(*_args, **_kwargs):
        raise auth_service.LoginRateLimitedError(60)

    monkeypatch.setattr(auth_routes.auth_service, "login", rate_limited)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [(b"origin", b"http://127.0.0.1:3000")],
            "client": ("198.51.100.50", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.login(
            schemas.LoginCreate(
                email="unknown@example.com",
                password="wrong-password",
            ),
            request,
            Response(),
            object(),
        )

    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "60"}
    assert exc.value.detail == "Login temporarily rate limited"


def test_stale_bucket_cleanup_failure_does_not_escape() -> None:
    class Nested:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FailingDb:
        def begin_nested(self):
            return Nested()

        def execute(self, _statement):
            raise OperationalError("cleanup failed", {}, RuntimeError("synthetic"))

    login_throttle.cleanup_stale_buckets(FailingDb())
