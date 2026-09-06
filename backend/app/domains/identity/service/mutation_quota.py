"""Hashed mutation quota subjects and counters within the caller's transaction."""
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
from math import ceil

from sqlalchemy.orm import Session

from app.config import settings
from app.domains.identity.repository import mutation_quota as quota_repository


def consume(
    db: Session,
    *,
    user_id: str,
    policies: tuple[tuple[str, timedelta, int], ...],
    now: datetime | None = None,
) -> int | None:
    current = _aware_utc(now or datetime.now(UTC))
    subject_hash = _subject_hash(user_id)
    for scope, _window, _limit in policies:
        quota_repository.ensure_bucket(
            db,
            scope=scope,
            subject_hash=subject_hash,
            now=current,
        )
    rows = quota_repository.lock_buckets(db, policies=policies, subject_hash=subject_hash)
    by_scope = {row.scope: row for row in rows}
    retry_after: list[int] = []
    for scope, window, limit in policies:
        row = by_scope.get(scope)
        if row is None:
            raise RuntimeError("Community mutation quota bucket missing")
        window_started_at = _aware_utc(row.window_started_at)
        if current - window_started_at >= window:
            row.window_started_at = current
            row.used_count = 0
            window_started_at = current
        if row.used_count >= limit:
            retry_after.append(
                max(
                    1,
                    ceil((window_started_at + window - current).total_seconds()),
                )
            )
    if retry_after:
        db.rollback()
        return max(retry_after)
    for row in rows:
        row.used_count += 1
        row.updated_at = current
    return None


def _subject_hash(user_id: str) -> str:
    return hmac.new(
        settings.login_throttle_hmac_secret.encode("utf-8"),
        f"community-mutation-user-v1:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
