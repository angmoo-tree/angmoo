from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import models, schemas
from app.api.v1.routes import auth as auth_routes
from app.services import auth as auth_service
from app.services import external_auth_verification


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.AuthExternalVerificationReservation.__table__.create(engine)
    return Session(engine)


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/google",
            "headers": [],
            "client": ("198.51.100.70", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def _configure_limits(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_minute: int = 5,
    source_15_minutes: int = 20,
    global_minute: int = 60,
    max_in_flight: int = 8,
) -> None:
    settings = external_auth_verification.settings
    monkeypatch.setattr(
        settings,
        "GOOGLE_AUTH_VERIFY_SOURCE_PER_MINUTE",
        source_minute,
    )
    monkeypatch.setattr(
        settings,
        "GOOGLE_AUTH_VERIFY_SOURCE_PER_15_MINUTES",
        source_15_minutes,
    )
    monkeypatch.setattr(
        settings,
        "GOOGLE_AUTH_VERIFY_GLOBAL_PER_MINUTE",
        global_minute,
    )
    monkeypatch.setattr(
        settings,
        "GOOGLE_AUTH_VERIFY_MAX_IN_FLIGHT",
        max_in_flight,
    )
    monkeypatch.setattr(settings, "GOOGLE_AUTH_VERIFY_LEASE_SECONDS", 30)
    monkeypatch.setattr(settings, "GOOGLE_AUTH_VERIFY_RETENTION_HOURS", 24)


def test_google_verifier_is_not_called_after_source_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    _configure_limits(monkeypatch, source_minute=2)
    verifier_calls = 0

    def reject_credential(_credential: str) -> dict:
        nonlocal verifier_calls
        verifier_calls += 1
        raise auth_service.InvalidGoogleCredentialError

    monkeypatch.setattr(
        auth_service,
        "_verify_google_credential",
        reject_credential,
    )
    data = schemas.GoogleLoginCreate(credential="synthetic-google-token")

    for _ in range(2):
        with pytest.raises(auth_service.InvalidGoogleCredentialError):
            auth_service.login_with_google(
                db,
                data,
                source="198.51.100.70",
            )

    with pytest.raises(auth_service.GoogleLoginRateLimitedError) as exc:
        auth_service.login_with_google(
            db,
            data,
            source="198.51.100.70",
        )

    assert verifier_calls == 2
    assert 1 <= exc.value.retry_after_seconds <= 60


def test_google_verification_active_lease_limit_and_stale_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    _configure_limits(
        monkeypatch,
        source_minute=20,
        source_15_minutes=20,
        global_minute=20,
        max_in_flight=2,
    )
    now = datetime(2026, 7, 26, 5, 0, tzinfo=UTC)

    first = external_auth_verification.reserve_google_verification(
        db,
        source="198.51.100.71",
        now=now,
    )
    second = external_auth_verification.reserve_google_verification(
        db,
        source="198.51.100.72",
        now=now,
    )

    with pytest.raises(
        external_auth_verification.ExternalVerificationRateLimitedError
    ) as exc:
        external_auth_verification.reserve_google_verification(
            db,
            source="198.51.100.73",
            now=now,
        )
    assert 1 <= exc.value.retry_after_seconds <= 30

    external_auth_verification.complete_google_verification(
        db,
        first.id,
        outcome_class="invalid",
        now=now + timedelta(seconds=1),
    )
    third = external_auth_verification.reserve_google_verification(
        db,
        source="198.51.100.73",
        now=now + timedelta(seconds=1),
    )
    assert third.id

    stale_time = now + timedelta(seconds=31)
    fourth = external_auth_verification.reserve_google_verification(
        db,
        source="198.51.100.74",
        now=stale_time,
    )
    assert fourth.id
    assert second.completed_at is None


def test_google_verification_reservation_stores_only_hashed_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    _configure_limits(monkeypatch)
    source = "198.51.100.75"

    external_auth_verification.reserve_google_verification(db, source=source)

    row = db.scalar(select(models.AuthExternalVerificationReservation))
    assert row is not None
    serialized = " ".join(
        str(value)
        for value in (
            row.id,
            row.provider,
            row.source_hash,
            row.outcome_class,
        )
    )
    assert source not in serialized
    assert len(row.source_hash) == 64


def test_google_route_returns_generic_429_with_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def rate_limited(*_args, **_kwargs):
        raise auth_service.GoogleLoginRateLimitedError(30)

    monkeypatch.setattr(
        auth_routes.auth_service,
        "login_with_google",
        rate_limited,
    )

    with pytest.raises(HTTPException) as exc:
        auth_routes.google_login(
            schemas.GoogleLoginCreate(credential="synthetic-google-token"),
            _request(),
            object(),
        )

    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "30"}
    assert exc.value.detail == "Google login temporarily rate limited"
