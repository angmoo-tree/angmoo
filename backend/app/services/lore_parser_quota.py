from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
from threading import Lock
from typing import Iterator
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models
from app.core.config import settings


GLOBAL_ACTIVE_LIMIT = 2
SUBJECT_ACTIVE_LIMIT = 1
LEASE_SECONDS = 30
RETRY_AFTER_SECONDS = 2
_SQLITE_LOCK = Lock()
_POSTGRES_LOCK_ID = 7_026_006_600_001


@dataclass(frozen=True)
class LoreParserCapacityError(Exception):
    retry_after_seconds: int = RETRY_AFTER_SECONDS


class LoreParserLeaseUnavailableError(Exception):
    pass


@contextmanager
def parser_lease(
    db: Session,
    *,
    user_id: str,
    now: datetime | None = None,
) -> Iterator[str]:
    current = _aware_utc(now or datetime.now(UTC))
    subject_hash = _subject_hash(user_id)
    lease_id = f"lore-lease-{uuid4().hex}"
    dialect = db.get_bind().dialect.name
    lock = _SQLITE_LOCK if dialect != "postgresql" else None

    if lock is not None:
        lock.acquire()
    try:
        if dialect == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": _POSTGRES_LOCK_ID},
            )
        active_filter = (
            models.LoreParserLease.released_at.is_(None),
            models.LoreParserLease.lease_expires_at > current,
        )
        global_active = int(
            db.scalar(
                select(func.count(models.LoreParserLease.id)).where(*active_filter)
            )
            or 0
        )
        subject_active = int(
            db.scalar(
                select(func.count(models.LoreParserLease.id)).where(
                    *active_filter,
                    models.LoreParserLease.subject_hash == subject_hash,
                )
            )
            or 0
        )
        if (
            global_active >= GLOBAL_ACTIVE_LIMIT
            or subject_active >= SUBJECT_ACTIVE_LIMIT
        ):
            db.rollback()
            raise LoreParserCapacityError()
        db.add(
            models.LoreParserLease(
                id=lease_id,
                subject_hash=subject_hash,
                created_at=current,
                lease_expires_at=current + timedelta(seconds=LEASE_SECONDS),
            )
        )
        db.commit()
    except LoreParserCapacityError:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise LoreParserLeaseUnavailableError(
            "Lore parser capacity is unavailable"
        ) from exc
    finally:
        if lock is not None:
            lock.release()

    try:
        yield lease_id
    finally:
        try:
            lease = db.get(models.LoreParserLease, lease_id)
            if lease is not None and lease.released_at is None:
                lease.released_at = datetime.now(UTC)
                db.commit()
        except SQLAlchemyError:
            db.rollback()


def _subject_hash(user_id: str) -> str:
    return hmac.new(
        settings.login_throttle_hmac_secret.encode("utf-8"),
        f"lore-parser-user-v1:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
