from dataclasses import dataclass

from datetime import UTC, datetime, timedelta, tzinfo

from math import ceil

from sqlalchemy.orm import Session

from app.domains.local_bot import models

from app.domains.local_bot.repository import quota as quota_repository

from app.domains.local_bot.exceptions import QuotaExceeded

from app.domains.routines.service import tick_schedule as agent_activity_policy
from app.contracts.environment import AccountingPeriod
from app.core.calendar import day_bounds, local_period
from app.core.calendar_ledger import add_bucket, ledger_usage, CalendarLedgerInvalid

@dataclass
class ActionQuota:
    rows: dict[str, models.LocalBotActionQuotaBucket]
    now: datetime
    local_timezone: tzinfo
    period: AccountingPeriod | None = None

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
            if self.period is not None:
                if row.period_state is None:
                    ledger = {"version": 1, "buckets": {}}
                    if row.used_count:
                        if row.quota_date is None:
                            raise CalendarLedgerInvalid("calendar_quota_recovery_required")
                        ledger = add_bucket(ledger, "legacy:kst:" + row.quota_date.isoformat(),
                            day_bounds(row.quota_date, "Asia/Seoul"), row.used_count)
                    row.period_state = ledger
                used = ledger_usage(row.period_state, self.period)
                row.quota_date = self.now.astimezone(self.local_timezone).date()
                row.used_count = used
            quota_date = self.now.astimezone(self.local_timezone).date()
            if row.quota_date != quota_date:
                row.quota_date = quota_date
                row.used_count = 0
            if row.used_count >= max_per_day:
                raise QuotaExceeded(
                    label=label,
                    message=message,
                    retry_after_seconds=_seconds_until(
                        self.period.allowance_available_at if self.period else _next_local_day_start_utc(self.now, self.local_timezone),
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
                if self.period is not None and row.period_state is not None:
                    row.period_state = add_bucket(row.period_state, "day:" + self.period.timezone + ":" + self.period.key,
                        local_period(self.now, self.period.timezone, "day"), 1)
            row.last_succeeded_at = self.now
            row.updated_at = self.now

def lock_action_quota(
    db: Session,
    *,
    character_id: str,
    labels: tuple[str, ...],
    now: datetime | None = None,
) -> ActionQuota:
    from app.domains.identity.service.environment import lock_environment_admission, accounting_period
    from zoneinfo import ZoneInfo
    lock_environment_admission(db)
    current = _aware_utc(now or datetime.now(UTC))
    period = accounting_period(db, None, "day", now=current)
    ordered_labels = tuple(sorted(dict.fromkeys(labels)))
    for label in ordered_labels:
        quota_repository._ensure_action_bucket(db, character_id=character_id, action_label=label)
    rows = list(
        quota_repository.read_action_buckets(db, character_id, ordered_labels)
    )
    by_label = {row.action_label: row for row in rows}
    missing = set(ordered_labels) - set(by_label)
    if missing:
        raise RuntimeError(f"Local Bot quota bucket missing after insert: {sorted(missing)}")
    return ActionQuota(
        rows=by_label,
        now=current,
        local_timezone=ZoneInfo(period.timezone),
        period=period,
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
    quota_repository._ensure_read_bucket(db, local_key_id=local_key_id, now=current)
    row = quota_repository.read_read_bucket(db, local_key_id)
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
