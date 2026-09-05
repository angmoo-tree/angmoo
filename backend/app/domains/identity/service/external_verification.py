from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import logging
from math import ceil
from threading import Lock
from uuid import uuid4

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.identity import models
from app.config import settings


PROVIDER_GOOGLE = "google"
_GLOBAL_LOCK_KEY = int.from_bytes(
    hashlib.sha256(b"angmoo:external-auth-verification:global:v1").digest()[:8],
    byteorder="big",
    signed=True,
)
_NON_POSTGRES_LOCK = Lock()
logger = logging.getLogger(__name__)


from app.domains.identity.exceptions import ExternalVerificationRateLimitedError


def reserve_google_verification(
    db: Session,
    *,
    source: str,
    now: datetime | None = None,
) -> models.AuthExternalVerificationReservation:
    current = _aware_utc(now or datetime.now(UTC))
    source_hash = _subject_hash("google-verification-source-v1", source)
    lease_seconds = max(1, settings.GOOGLE_AUTH_VERIFY_LEASE_SECONDS)

    with _reservation_lock(db, source_hash):
        try:
            db.execute(
                delete(models.AuthExternalVerificationReservation).where(
                    models.AuthExternalVerificationReservation.created_at
                    < current
                    - timedelta(
                        hours=max(1, settings.GOOGLE_AUTH_VERIFY_RETENTION_HOURS)
                    )
                ).execution_options(synchronize_session=False)
            )
            retry_after = _retry_after_seconds(
                db,
                source_hash=source_hash,
                now=current,
            )
            if retry_after is not None:
                db.rollback()
                raise ExternalVerificationRateLimitedError(retry_after)

            reservation = models.AuthExternalVerificationReservation(
                id=f"auth-verify-{uuid4().hex}",
                provider=PROVIDER_GOOGLE,
                source_hash=source_hash,
                created_at=current,
                lease_expires_at=current + timedelta(seconds=lease_seconds),
                completed_at=None,
                outcome_class=None,
            )
            db.add(reservation)
            db.commit()
            db.refresh(reservation)
            return reservation
        except ExternalVerificationRateLimitedError:
            raise
        except Exception:
            db.rollback()
            raise


def complete_google_verification(
    db: Session,
    reservation_id: str,
    *,
    outcome_class: str,
    now: datetime | None = None,
) -> None:
    if outcome_class not in {"success", "invalid", "error"}:
        raise ValueError("Unsupported external verification outcome")
    current = _aware_utc(now or datetime.now(UTC))
    try:
        db.execute(
            update(models.AuthExternalVerificationReservation)
            .where(
                models.AuthExternalVerificationReservation.id == reservation_id,
                models.AuthExternalVerificationReservation.completed_at.is_(None),
            )
            .values(completed_at=current, outcome_class=outcome_class)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning(
            "external_auth_verification_completion_failed "
            "provider=google outcome=%s",
            outcome_class,
        )


def _retry_after_seconds(
    db: Session,
    *,
    source_hash: str,
    now: datetime,
) -> int | None:
    windows = (
        (
            models.AuthExternalVerificationReservation.source_hash == source_hash,
            timedelta(minutes=1),
            max(1, settings.GOOGLE_AUTH_VERIFY_SOURCE_PER_MINUTE),
        ),
        (
            models.AuthExternalVerificationReservation.source_hash == source_hash,
            timedelta(minutes=15),
            max(1, settings.GOOGLE_AUTH_VERIFY_SOURCE_PER_15_MINUTES),
        ),
        (
            None,
            timedelta(minutes=1),
            max(1, settings.GOOGLE_AUTH_VERIFY_GLOBAL_PER_MINUTE),
        ),
    )
    retry_candidates: list[int] = []
    for source_condition, window, limit in windows:
        conditions = [
            models.AuthExternalVerificationReservation.provider == PROVIDER_GOOGLE,
            models.AuthExternalVerificationReservation.created_at >= now - window,
        ]
        if source_condition is not None:
            conditions.append(source_condition)
        count = int(
            db.scalar(
                select(func.count(models.AuthExternalVerificationReservation.id)).where(
                    *conditions
                )
            )
            or 0
        )
        if count < limit:
            continue
        oldest = db.scalar(
            select(models.AuthExternalVerificationReservation.created_at)
            .where(*conditions)
            .order_by(
                models.AuthExternalVerificationReservation.created_at.asc(),
                models.AuthExternalVerificationReservation.id.asc(),
            )
            .limit(1)
        )
        if oldest is not None:
            retry_candidates.append(
                max(1, ceil((_aware_utc(oldest) + window - now).total_seconds()))
            )

    active_conditions = (
        models.AuthExternalVerificationReservation.provider == PROVIDER_GOOGLE,
        models.AuthExternalVerificationReservation.completed_at.is_(None),
        models.AuthExternalVerificationReservation.lease_expires_at > now,
    )
    active_count = int(
        db.scalar(
            select(func.count(models.AuthExternalVerificationReservation.id)).where(
                *active_conditions
            )
        )
        or 0
    )
    if active_count >= max(1, settings.GOOGLE_AUTH_VERIFY_MAX_IN_FLIGHT):
        first_lease = db.scalar(
            select(models.AuthExternalVerificationReservation.lease_expires_at)
            .where(*active_conditions)
            .order_by(
                models.AuthExternalVerificationReservation.lease_expires_at.asc(),
                models.AuthExternalVerificationReservation.id.asc(),
            )
            .limit(1)
        )
        if first_lease is not None:
            retry_candidates.append(
                max(1, ceil((_aware_utc(first_lease) - now).total_seconds()))
            )

    return max(retry_candidates) if retry_candidates else None


@contextmanager
def _reservation_lock(db: Session, source_hash: str):
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        source_lock_key = int.from_bytes(
            hashlib.sha256(
                f"angmoo:external-auth-verification:{source_hash}:v1".encode("ascii")
            ).digest()[:8],
            byteorder="big",
            signed=True,
        )
        db.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _GLOBAL_LOCK_KEY},
        )
        db.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": source_lock_key},
        )
        yield
        return
    with _NON_POSTGRES_LOCK:
        yield


def _subject_hash(domain: str, subject: str) -> str:
    return hmac.new(
        settings.login_throttle_hmac_secret.encode("utf-8"),
        f"{domain}:{subject}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
