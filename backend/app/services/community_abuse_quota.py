from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
from math import ceil

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.core.config import settings


@dataclass(frozen=True)
class CommunityQuotaExceeded(Exception):
    retry_after_seconds: int


_ACTION_POLICIES = {
    "reply": (
        ("reply_minute", timedelta(minutes=1), 10),
        ("reply_day", timedelta(days=1), 100),
    ),
    "report": (
        ("report_10m", timedelta(minutes=10), 5),
        ("report_day", timedelta(days=1), 30),
    ),
}


def consume(
    db: Session,
    *,
    user_id: str,
    action: str,
    now: datetime | None = None,
) -> None:
    policies = _ACTION_POLICIES.get(action)
    if policies is None:
        raise ValueError("Unsupported community quota action")
    current = _aware_utc(now or datetime.now(UTC))
    subject_hash = _subject_hash(user_id)
    for scope, _window, _limit in policies:
        _ensure_bucket(
            db,
            scope=scope,
            subject_hash=subject_hash,
            now=current,
        )
    rows = list(
        db.scalars(
            select(models.CommunityMutationQuotaBucket)
            .where(
                tuple_(
                    models.CommunityMutationQuotaBucket.scope,
                    models.CommunityMutationQuotaBucket.subject_hash,
                ).in_(
                    [(scope, subject_hash) for scope, _window, _limit in policies]
                )
            )
            .order_by(models.CommunityMutationQuotaBucket.scope.asc())
            .with_for_update()
        )
    )
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
        raise CommunityQuotaExceeded(max(retry_after))
    for row in rows:
        row.used_count += 1
        row.updated_at = current


def _ensure_bucket(
    db: Session,
    *,
    scope: str,
    subject_hash: str,
    now: datetime,
) -> None:
    identity = {"scope": scope, "subject_hash": subject_hash}
    if db.get(models.CommunityMutationQuotaBucket, identity) is not None:
        return
    try:
        with db.begin_nested():
            db.add(
                models.CommunityMutationQuotaBucket(
                    scope=scope,
                    subject_hash=subject_hash,
                    window_started_at=now,
                    used_count=0,
                    updated_at=now,
                )
            )
            db.flush()
    except IntegrityError:
        pass


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
