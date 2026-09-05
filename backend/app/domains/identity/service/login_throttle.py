from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac

import logging
from math import ceil


from sqlalchemy import delete, select, tuple_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.identity import models
from app.config import settings


FAILURE_WINDOW = timedelta(minutes=15)
STALE_BUCKET_AGE = timedelta(hours=24)
logger = logging.getLogger(__name__)


@dataclass
class LoginThrottle:
    rows: dict[str, models.AuthLoginThrottleBucket]
    now: datetime

    def retry_after_seconds(self) -> int | None:
        blocked_until = [
            _aware_utc(row.blocked_until)
            for row in self.rows.values()
            if row.blocked_until is not None
            and _aware_utc(row.blocked_until) > self.now
        ]
        if not blocked_until:
            return None
        return max(1, ceil((max(blocked_until) - self.now).total_seconds()))

    def record_failure(self) -> None:
        for row in self.rows.values():
            window_started_at = _aware_utc(row.window_started_at)
            if self.now - window_started_at >= FAILURE_WINDOW:
                row.window_started_at = self.now
                row.failure_count = 0
                row.blocked_until = None
            row.failure_count += 1
            row.last_failure_at = self.now
            row.blocked_until = blocked_until_for_failure_count(
                row.failure_count,
                now=self.now,
            )
            row.updated_at = self.now

    def reset_account_source(self) -> None:
        row = self.rows["account_source"]
        row.window_started_at = self.now
        row.failure_count = 0
        row.blocked_until = None
        row.last_failure_at = None
        row.updated_at = self.now


def lock_login_throttle(
    db: Session,
    *,
    normalized_email: str,
    source: str,
    now: datetime | None = None,
) -> LoginThrottle:
    current = _aware_utc(now or datetime.now(UTC))
    subjects = {
        "source": _subject_hash("login-source-v1", source),
        "account_source": _subject_hash(
            "login-account-source-v1",
            f"{normalized_email}:{source}",
        ),
    }
    for scope in sorted(subjects):
        _ensure_bucket(
            db,
            scope=scope,
            subject_hash=subjects[scope],
            now=current,
        )
    rows = list(
        db.scalars(
            select(models.AuthLoginThrottleBucket)
            .where(
                tuple_(
                    models.AuthLoginThrottleBucket.scope,
                    models.AuthLoginThrottleBucket.subject_hash,
                ).in_([(scope, subjects[scope]) for scope in sorted(subjects)])
            )
            .order_by(
                models.AuthLoginThrottleBucket.scope.asc(),
                models.AuthLoginThrottleBucket.subject_hash.asc(),
            )
            .with_for_update()
        )
    )
    by_scope = {row.scope: row for row in rows}
    if set(by_scope) != set(subjects):
        raise RuntimeError("Login throttle bucket missing after insert")
    return LoginThrottle(rows=by_scope, now=current)


def cleanup_stale_buckets(db: Session, *, now: datetime | None = None) -> None:
    current = _aware_utc(now or datetime.now(UTC))
    try:
        with db.begin_nested():
            db.execute(
                delete(models.AuthLoginThrottleBucket)
                .where(
                    models.AuthLoginThrottleBucket.updated_at
                    < current - STALE_BUCKET_AGE
                )
                .execution_options(synchronize_session=False)
            )
    except SQLAlchemyError:
        logger.warning("login_throttle_stale_bucket_cleanup_failed")


def blocked_until_for_failure_count(
    failure_count: int,
    *,
    now: datetime,
) -> datetime | None:
    if failure_count >= 20:
        return now + timedelta(minutes=30)
    if failure_count >= 10:
        return now + timedelta(minutes=5)
    if failure_count >= 5:
        return now + timedelta(seconds=60)
    return None


def _ensure_bucket(
    db: Session,
    *,
    scope: str,
    subject_hash: str,
    now: datetime,
) -> None:
    identity = {"scope": scope, "subject_hash": subject_hash}
    if db.get(models.AuthLoginThrottleBucket, identity) is not None:
        return
    try:
        with db.begin_nested():
            db.add(
                models.AuthLoginThrottleBucket(
                    scope=scope,
                    subject_hash=subject_hash,
                    window_started_at=now,
                    failure_count=0,
                )
            )
            db.flush()
    except IntegrityError:
        pass


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
