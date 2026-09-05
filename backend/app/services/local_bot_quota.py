from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from math import ceil

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.domains.routines.service import tick_schedule as agent_activity_policy


@dataclass(frozen=True)
class QuotaExceeded(Exception):
    label: str
    message: str
    retry_after_seconds: int

    def __str__(self) -> str:
        return self.message


@dataclass
class ActionQuota:
    rows: dict[str, models.LocalBotActionQuotaBucket]
    now: datetime
    local_timezone: tzinfo

    def ensure_allowed(
        self,
        label: str,
        *,
        cooldown: timedelta,
        max_per_day: int | None,
        message: str,
    ) -> None:
        row = self.rows[label]
        if max_per_day is not None:
            quota_date = self.now.astimezone(self.local_timezone).date()
            if row.quota_date != quota_date:
                row.quota_date = quota_date
                row.used_count = 0
            if row.used_count >= max_per_day:
                raise QuotaExceeded(
                    label=label,
                    message=message,
                    retry_after_seconds=_seconds_until(
                        _next_local_day_start_utc(self.now, self.local_timezone),
                        self.now,
                    ),
                )
        if row.last_succeeded_at is None or cooldown <= timedelta(0):
            return
        last_succeeded_at = _aware_utc(row.last_succeeded_at)
        ready_at = last_succeeded_at + cooldown
        if ready_at > self.now:
            raise QuotaExceeded(
                label=label,
                message=message,
                retry_after_seconds=_seconds_until(ready_at, self.now),
            )

    def consume(self, labels: tuple[str, ...]) -> None:
        for label in labels:
            row = self.rows[label]
            if row.quota_date is not None:
                row.used_count += 1
            row.last_succeeded_at = self.now
            row.updated_at = self.now


def lock_action_quota(
    db: Session,
    *,
    character_id: str,
    labels: tuple[str, ...],
    now: datetime | None = None,
) -> ActionQuota:
    current = _aware_utc(now or datetime.now(UTC))
    ordered_labels = tuple(sorted(dict.fromkeys(labels)))
    for label in ordered_labels:
        _ensure_action_bucket(db, character_id=character_id, action_label=label)
    rows = list(
        db.scalars(
            select(models.LocalBotActionQuotaBucket)
            .where(
                models.LocalBotActionQuotaBucket.character_id == character_id,
                models.LocalBotActionQuotaBucket.action_label.in_(ordered_labels),
            )
            .order_by(models.LocalBotActionQuotaBucket.action_label.asc())
            .with_for_update()
        )
    )
    by_label = {row.action_label: row for row in rows}
    missing = set(ordered_labels) - set(by_label)
    if missing:
        raise RuntimeError(f"Local Bot quota bucket missing after insert: {sorted(missing)}")
    return ActionQuota(
        rows=by_label,
        now=current,
        local_timezone=agent_activity_policy.APP_TIMEZONE,
    )


def consume_read(
    db: Session,
    *,
    local_key_id: str,
    now: datetime | None = None,
    limit: int,
    window: timedelta,
) -> None:
    current = _aware_utc(now or datetime.now(UTC))
    _ensure_read_bucket(db, local_key_id=local_key_id, now=current)
    row = db.scalar(
        select(models.LocalBotReadQuotaBucket)
        .where(models.LocalBotReadQuotaBucket.local_key_id == local_key_id)
        .with_for_update()
    )
    if row is None:
        raise RuntimeError("Local Bot read quota bucket missing after insert")
    window_started_at = _aware_utc(row.window_started_at)
    if current - window_started_at >= window:
        row.window_started_at = current
        row.used_count = 0
    if row.used_count >= limit:
        retry_at = _aware_utc(row.window_started_at) + window
        raise QuotaExceeded(
            label="read",
            message="Local bot read rate limit is reached.",
            retry_after_seconds=_seconds_until(retry_at, current),
        )
    row.used_count += 1
    row.updated_at = current
    db.commit()


def _ensure_action_bucket(
    db: Session,
    *,
    character_id: str,
    action_label: str,
) -> None:
    if db.get(
        models.LocalBotActionQuotaBucket,
        {
            "character_id": character_id,
            "action_label": action_label,
        },
    ) is not None:
        return
    try:
        with db.begin_nested():
            db.add(
                models.LocalBotActionQuotaBucket(
                    character_id=character_id,
                    action_label=action_label,
                    used_count=0,
                )
            )
            db.flush()
    except IntegrityError:
        pass


def _ensure_read_bucket(
    db: Session,
    *,
    local_key_id: str,
    now: datetime,
) -> None:
    if db.get(models.LocalBotReadQuotaBucket, local_key_id) is not None:
        return
    try:
        with db.begin_nested():
            db.add(
                models.LocalBotReadQuotaBucket(
                    local_key_id=local_key_id,
                    window_started_at=now,
                    used_count=0,
                )
            )
            db.flush()
    except IntegrityError:
        pass


def _next_local_day_start_utc(now: datetime, local_timezone: tzinfo) -> datetime:
    local_now = now.astimezone(local_timezone)
    next_date = local_now.date() + timedelta(days=1)
    return datetime.combine(
        next_date,
        datetime.min.time(),
        tzinfo=local_timezone,
    ).astimezone(UTC)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _seconds_until(until: datetime, now: datetime) -> int:
    return max(1, ceil((until - now).total_seconds()))
