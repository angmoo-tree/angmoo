import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.core import active_hours
from app.core.config import settings
from app.cruds import agents as agent_crud


APP_TIMEZONE = ZoneInfo("Asia/Seoul")
PUBLIC_ACTION_TYPES = {
    "comment": ("commented", "replied"),
    "reply": ("commented", "replied"),
    "post": ("post_created",),
    "quote": ("quoted",),
    "like": ("liked",),
    "repost": ("reposted",),
    "follow": ("followed",),
    "unfollow": ("unfollowed",),
}
POLICY_ACTION_NAMES = (
    "post",
    "reply",
    "quote",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)
TENDENCY_PUBLIC_ACTION_NAMES = ("post", "reply", "like", "repost", "follow", "unfollow")
POLICY_SESSION_MARKER = ":resident-tick:"
MANUAL_POLICY_SESSION_MARKER = ":resident-manual:"


class ActivityPolicyDeniedError(Exception):
    pass


@dataclass(frozen=True)
class ActivityPolicy:
    within_active_hours: bool
    allowed_actions: tuple[str, ...]
    blocked_reasons: dict[str, str]
    next_tick_at: datetime
    summary: str
    target_interval_seconds: int = 0
    schedule_spread_seconds: int = 0
    schedule_spread_reason: str = ""
    tendency_summary: str = ""
    tendency_action_ranges: dict[str, object] | None = None
    planner_tendency_profile: dict[str, object] | None = None

    @property
    def should_skip_llm(self) -> bool:
        return not self.within_active_hours or not any(
            action != "observe" for action in self.allowed_actions
        )

    def to_prompt(self) -> str:
        allowed = ", ".join(self.allowed_actions) if self.allowed_actions else "none"
        blocked = (
            "\n".join(f"  - {action}: {reason}" for action, reason in self.blocked_reasons.items())
            if self.blocked_reasons
            else "  - none"
        )
        tendency = _format_tendency_prompt(
            self.tendency_summary, self.tendency_action_ranges
        )
        return f"""Backend activity policy for this tick:
- Allowed actions: {allowed}
- Blocked actions:
{blocked}
- Persona public-action tendency notes:
{tendency}
- If a public action is not listed as allowed, do not call its tool.
- Observe is not a tendency action. If no public action fits and observe is allowed, finish without public writes so the backend can record an observed fallback.
- Next scheduled tick after this run: {self.next_tick_at.isoformat()}"""

    def to_result(self) -> dict[str, object]:
        return {
            "within_active_hours": self.within_active_hours,
            "allowed_actions": list(self.allowed_actions),
            "blocked_reasons": self.blocked_reasons,
            "next_tick_at": self.next_tick_at.isoformat(),
            "target_interval_seconds": self.target_interval_seconds,
            "schedule_spread_seconds": self.schedule_spread_seconds,
            "schedule_spread_reason": self.schedule_spread_reason,
            "summary": self.summary,
            "tendency_summary": self.tendency_summary,
            "tendency_action_ranges": self.tendency_action_ranges or {},
        }


@dataclass(frozen=True)
class TickSchedule:
    next_tick_at: datetime
    target_interval_seconds: int
    schedule_spread_seconds: int
    schedule_spread_reason: str


def is_policy_enforced_session(session_key: str) -> bool:
    return (
        POLICY_SESSION_MARKER in session_key
        or MANUAL_POLICY_SESSION_MARKER in session_key
    )


def is_manual_policy_session(session_key: str) -> bool:
    return MANUAL_POLICY_SESSION_MARKER in session_key


def _format_tendency_prompt(
    tendency_summary: str, action_ranges: dict[str, object] | None
) -> str:
    lines: list[str] = []
    if tendency_summary.strip():
        lines.append(f"  - summary: {tendency_summary.strip()}")
    if action_ranges:
        for action in TENDENCY_PUBLIC_ACTION_NAMES:
            raw = action_ranges.get(action)
            if not isinstance(raw, dict):
                continue
            note = raw.get("note")
            if isinstance(note, str) and note.strip():
                lines.append(f"  - {action}: {note.strip()}")
    return "\n".join(lines) if lines else "  - none saved yet"


def tick_interval_seconds(setting: models.AgentActivitySetting) -> int:
    return max(30 * 60, min(setting.activity_interval_minutes, 1440) * 60)


def next_tick_schedule(
    setting: models.AgentActivitySetting,
    *,
    character_id: str,
    now: datetime,
    within_active_hours: bool,
) -> TickSchedule:
    current = _aware_utc(now)
    target_interval = tick_interval_seconds(setting)
    if not within_active_hours:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current,
            reason="active_start_spread",
            target_interval_seconds=target_interval,
        )

    base = current + timedelta(seconds=target_interval)
    current_window = _active_window_containing(setting, current)
    if current_window is not None and base >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="next_window",
            target_interval_seconds=target_interval,
        )

    max_spread = settings.resident_tick_interval_jitter_max_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "interval_jitter",
        f"{base.astimezone(APP_TIMEZONE).isoformat()}:{target_interval}",
        max_spread,
    )
    candidate = base + timedelta(seconds=spread)
    if current_window is not None and candidate >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="next_window",
            target_interval_seconds=target_interval,
        )
    return TickSchedule(
        next_tick_at=candidate,
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="interval_jitter",
    )


def initial_tick_schedule(
    setting: models.AgentActivitySetting,
    *,
    character_id: str,
    now: datetime,
) -> TickSchedule:
    current = _aware_utc(now)
    target_interval = tick_interval_seconds(setting)
    if not _is_within_active_hours(setting, current):
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current,
            reason="active_start_spread",
            target_interval_seconds=target_interval,
        )

    max_spread = settings.resident_tick_initial_spread_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "initial_spread",
        current.astimezone(APP_TIMEZONE).strftime("%Y-%m-%dT%H:%M"),
        max_spread,
    )
    candidate = current + timedelta(seconds=spread)
    current_window = _active_window_containing(setting, current)
    if current_window is not None and candidate >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="next_window",
            target_interval_seconds=target_interval,
        )
    return TickSchedule(
        next_tick_at=candidate,
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="initial_spread",
    )


def retry_tick_schedule(
    setting: models.AgentActivitySetting,
    *,
    character_id: str,
    retry_at: datetime,
) -> TickSchedule:
    base = _aware_utc(retry_at)
    target_interval = tick_interval_seconds(setting)
    if not _is_within_active_hours(setting, base):
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=base,
            reason="retry_spread",
            target_interval_seconds=target_interval,
        )

    max_spread = settings.resident_tick_retry_spread_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "retry_spread",
        base.astimezone(APP_TIMEZONE).strftime("%Y-%m-%dT%H:%M"),
        max_spread,
    )
    candidate = base + timedelta(seconds=spread)
    current_window = _active_window_containing(setting, base)
    if current_window is not None and candidate >= current_window[1]:
        return _active_start_schedule(
            setting,
            character_id=character_id,
            now=current_window[1],
            reason="retry_spread",
            target_interval_seconds=target_interval,
        )
    return TickSchedule(
        next_tick_at=candidate,
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="retry_spread",
    )


def recovery_tick_schedule(
    setting: models.AgentActivitySetting,
    *,
    character_id: str,
    now: datetime,
) -> TickSchedule:
    current = _aware_utc(now)
    target_interval = tick_interval_seconds(setting)
    max_spread = settings.resident_tick_retry_spread_seconds
    spread = _deterministic_spread_seconds(
        character_id,
        "recovery_spread",
        current.astimezone(APP_TIMEZONE).strftime("%Y-%m-%dT%H:%M"),
        max_spread,
    )
    return TickSchedule(
        next_tick_at=current + timedelta(seconds=spread),
        target_interval_seconds=target_interval,
        schedule_spread_seconds=spread,
        schedule_spread_reason="recovery_spread",
    )


def build_activity_policy(
    db: Session,
    *,
    character_id: str,
    now: datetime | None = None,
    ignore_active_hours: bool = False,
) -> ActivityPolicy:
    setting = agent_crud.ensure_setting(db, character_id)
    current = _aware_utc(now or datetime.now(UTC))
    actual_within_active_hours = _is_within_active_hours(setting, current)
    within_active_hours = True if ignore_active_hours else actual_within_active_hours
    schedule = next_tick_schedule(
        setting,
        character_id=character_id,
        now=current,
        within_active_hours=actual_within_active_hours,
    )
    blocked: dict[str, str] = {}

    if not within_active_hours:
        reason = (
            f"outside active hours {setting.active_hours_start}-{setting.active_hours_end}"
        )
        return ActivityPolicy(
            within_active_hours=False,
            allowed_actions=(),
            blocked_reasons={action: reason for action in POLICY_ACTION_NAMES},
            next_tick_at=schedule.next_tick_at,
            summary=reason,
            target_interval_seconds=schedule.target_interval_seconds,
            schedule_spread_seconds=schedule.schedule_spread_seconds,
            schedule_spread_reason=schedule.schedule_spread_reason,
            tendency_summary=setting.tendency_summary,
            tendency_action_ranges=setting.tendency_action_ranges,
            planner_tendency_profile=setting.planner_tendency_profile,
        )

    allowed: list[str] = []
    if setting.allow_reply:
        _evaluate_counted_actions(
            db,
            character_id=character_id,
            actions=("reply",),
            action_types=PUBLIC_ACTION_TYPES["reply"],
            max_per_day=setting.max_comments_per_day,
            cooldown=timedelta(0),
            now=current,
            allowed=allowed,
            blocked=blocked,
        )
    else:
        blocked["reply"] = "reply writing is disabled"

    if setting.allow_post:
        _evaluate_counted_actions(
            db,
            character_id=character_id,
            actions=("post",),
            action_types=PUBLIC_ACTION_TYPES["post"],
            max_per_day=setting.max_posts_per_day,
            cooldown=timedelta(0),
            now=current,
            allowed=allowed,
            blocked=blocked,
        )
    else:
        blocked["post"] = "new post writing is disabled"
    blocked["quote"] = "quote is disabled for agent activity"

    if not setting.allow_like:
        blocked["like"] = "like is disabled"
    else:
        allowed.append("like")
    if setting.allow_repost:
        allowed.append("repost")
    else:
        blocked["repost"] = "repost is disabled"

    if setting.allow_follow:
        allowed.append("follow")
    else:
        blocked["follow"] = "follow is disabled"

    if setting.allow_unfollow:
        allowed.append("unfollow")
    else:
        blocked["unfollow"] = "unfollow is disabled"

    allowed.append("observe")

    summary = f"allowed={','.join(allowed)}"
    return ActivityPolicy(
        within_active_hours=True,
        allowed_actions=tuple(allowed),
        blocked_reasons=blocked,
        next_tick_at=schedule.next_tick_at,
        summary=summary,
        target_interval_seconds=schedule.target_interval_seconds,
        schedule_spread_seconds=schedule.schedule_spread_seconds,
        schedule_spread_reason=schedule.schedule_spread_reason,
        tendency_summary=setting.tendency_summary,
        tendency_action_ranges=setting.tendency_action_ranges,
        planner_tendency_profile=setting.planner_tendency_profile,
    )


def assert_action_allowed(db: Session, *, run: models.AgentRun, action: str) -> None:
    if not is_policy_enforced_session(run.session_key):
        return
    policy = build_activity_policy(
        db,
        character_id=run.character_id,
        ignore_active_hours=is_manual_policy_session(run.session_key),
    )
    if action in policy.allowed_actions:
        return
    reason = policy.blocked_reasons.get(action, "action is not allowed for this tick")
    raise ActivityPolicyDeniedError(reason)


def count_public_actions_since(
    db: Session, *, character_id: str, since: datetime
) -> int:
    return (
        db.scalar(
            select(func.count(models.AgentActivityLog.id)).where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type.in_(_public_action_log_types()),
                models.AgentActivityLog.created_at >= since,
            )
        )
        or 0
    )


def count_action_today(
    db: Session,
    *,
    character_id: str,
    action: str,
    now: datetime | None = None,
) -> int:
    action_type = PUBLIC_ACTION_TYPES[action]
    return _count_action_today(
        db,
        character_id,
        action_type,
        _aware_utc(now or datetime.now(UTC)),
    )


def _evaluate_counted_actions(
    db: Session,
    *,
    character_id: str,
    actions: tuple[str, ...],
    action_types: tuple[str, ...],
    max_per_day: int,
    cooldown: timedelta,
    now: datetime,
    allowed: list[str],
    blocked: dict[str, str],
) -> None:
    action_label = "/".join(actions)
    if max_per_day <= 0:
        _block_actions(blocked, actions, "daily limit is 0")
        return
    today_count = _count_action_today(db, character_id, action_types, now)
    if today_count >= max_per_day:
        _block_actions(
            blocked,
            actions,
            f"daily limit reached ({today_count}/{max_per_day})",
        )
        return
    latest = _latest_action_at(db, character_id, action_types)
    if latest is not None:
        ready_at = _aware_utc(latest) + cooldown
        if ready_at > now:
            _block_actions(
                blocked,
                actions,
                f"{action_label} cooldown until {ready_at.isoformat()}",
            )
            return
    allowed.extend(actions)


def _count_action_today(
    db: Session, character_id: str, action_types: str | tuple[str, ...], now: datetime
) -> int:
    local_now = now.astimezone(APP_TIMEZONE)
    day_start = datetime.combine(local_now.date(), time.min, tzinfo=APP_TIMEZONE)
    action_type_values = _normalize_action_types(action_types)
    return (
        db.scalar(
            select(func.count(models.AgentActivityLog.id)).where(
                models.AgentActivityLog.character_id == character_id,
                models.AgentActivityLog.action_type.in_(action_type_values),
                models.AgentActivityLog.created_at >= day_start.astimezone(UTC),
            )
        )
        or 0
    )


def _latest_action_at(
    db: Session, character_id: str, action_types: str | tuple[str, ...]
) -> datetime | None:
    action_type_values = _normalize_action_types(action_types)
    return db.scalar(
        select(models.AgentActivityLog.created_at)
        .where(
            models.AgentActivityLog.character_id == character_id,
            models.AgentActivityLog.action_type.in_(action_type_values),
        )
        .order_by(models.AgentActivityLog.created_at.desc(), models.AgentActivityLog.id.desc())
        .limit(1)
    )


def _block_actions(
    blocked: dict[str, str], actions: tuple[str, ...], reason: str
) -> None:
    for action in actions:
        blocked[action] = reason


def _normalize_action_types(action_types: str | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(action_types, str):
        return (action_types,)
    return action_types


def _public_action_log_types() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            action_type
            for action_types in PUBLIC_ACTION_TYPES.values()
            for action_type in action_types
        )
    )


def _next_tick_at(
    setting: models.AgentActivitySetting, now: datetime, within_active_hours: bool
) -> datetime:
    if within_active_hours:
        return now + timedelta(seconds=tick_interval_seconds(setting))
    return _next_active_start(setting, now)


def _is_within_active_hours(setting: models.AgentActivitySetting, now: datetime) -> bool:
    try:
        start, end = active_hours.active_hours_minutes(
            setting.active_hours_start,
            setting.active_hours_end,
        )
    except ValueError:
        return False
    if active_hours.active_hours_duration_from_minutes(start, end) <= 0:
        return False
    local_now = now.astimezone(APP_TIMEZONE)
    minute = local_now.hour * 60 + local_now.minute
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def _next_active_start(setting: models.AgentActivitySetting, now: datetime) -> datetime:
    window = _next_active_window(setting, now)
    if window is not None:
        return window[0]
    try:
        start = active_hours.parse_active_hour(
            setting.active_hours_start,
            allow_end_of_day=False,
        )
    except ValueError:
        start = active_hours.parse_active_hour(
            active_hours.DEFAULT_ACTIVE_HOURS_START,
            allow_end_of_day=False,
        )
    local_now = now.astimezone(APP_TIMEZONE)
    minute = local_now.hour * 60 + local_now.minute
    candidate_date = local_now.date()
    if minute >= start:
        candidate_date = candidate_date + timedelta(days=1)
    start_hour = min(start // 60, 23)
    start_minute = 0 if start >= 24 * 60 else start % 60
    if start >= 24 * 60:
        candidate_date = candidate_date + timedelta(days=1)
    return datetime.combine(
        candidate_date, time(start_hour, start_minute), tzinfo=APP_TIMEZONE
    ).astimezone(UTC)


def _active_start_schedule(
    setting: models.AgentActivitySetting,
    *,
    character_id: str,
    now: datetime,
    reason: str,
    target_interval_seconds: int,
) -> TickSchedule:
    window = _next_active_window(setting, now)
    if window is None:
        next_tick_at = _next_active_start(setting, now)
        return TickSchedule(
            next_tick_at=next_tick_at,
            target_interval_seconds=target_interval_seconds,
            schedule_spread_seconds=0,
            schedule_spread_reason=reason,
        )

    start_at, end_at = window
    max_spread = _active_start_spread_limit_seconds(setting, start_at, end_at)
    spread = _deterministic_spread_seconds(
        character_id,
        reason,
        start_at.astimezone(APP_TIMEZONE).isoformat(),
        max_spread,
    )
    return TickSchedule(
        next_tick_at=start_at + timedelta(seconds=spread),
        target_interval_seconds=target_interval_seconds,
        schedule_spread_seconds=spread,
        schedule_spread_reason=reason,
    )


def _active_start_spread_limit_seconds(
    setting: models.AgentActivitySetting,
    start_at: datetime,
    end_at: datetime,
) -> int:
    configured = settings.resident_tick_active_start_spread_seconds
    window_seconds = max(0, int((end_at - start_at).total_seconds()) - 1)
    boundary_seconds = (30 * 60) - 1
    return max(0, min(configured, boundary_seconds, window_seconds))


def _active_window_containing(
    setting: models.AgentActivitySetting, now: datetime
) -> tuple[datetime, datetime] | None:
    local_now = _aware_utc(now).astimezone(APP_TIMEZONE)
    start, end, duration = _active_hours_parts(setting)
    if duration <= 0:
        return None
    for day_offset in (-1, 0, 1):
        start_at = _local_datetime_for_minute(
            local_now.date() + timedelta(days=day_offset),
            start,
        )
        end_at = start_at + timedelta(minutes=duration)
        if start_at <= local_now < end_at:
            return start_at.astimezone(UTC), end_at.astimezone(UTC)
    return None


def _next_active_window(
    setting: models.AgentActivitySetting, now: datetime
) -> tuple[datetime, datetime] | None:
    local_now = _aware_utc(now).astimezone(APP_TIMEZONE)
    start, end, duration = _active_hours_parts(setting)
    if duration <= 0:
        return None
    for day_offset in (-1, 0, 1, 2, 3):
        start_at = _local_datetime_for_minute(
            local_now.date() + timedelta(days=day_offset),
            start,
        )
        end_at = start_at + timedelta(minutes=duration)
        if end_at <= local_now:
            continue
        if start_at >= local_now or start_at <= local_now < end_at:
            return start_at.astimezone(UTC), end_at.astimezone(UTC)
    return None


def _active_hours_parts(setting: models.AgentActivitySetting) -> tuple[int, int, int]:
    try:
        start, end = active_hours.active_hours_minutes(
            setting.active_hours_start,
            setting.active_hours_end,
        )
    except ValueError:
        start, end = active_hours.active_hours_minutes(
            active_hours.DEFAULT_ACTIVE_HOURS_START,
            active_hours.DEFAULT_ACTIVE_HOURS_END,
        )
    duration = active_hours.active_hours_duration_from_minutes(start, end)
    return start, end, duration


def _local_datetime_for_minute(base_date: date, minute: int) -> datetime:
    day_offset, minute_of_day = divmod(minute, 24 * 60)
    hour, local_minute = divmod(minute_of_day, 60)
    return datetime.combine(
        base_date + timedelta(days=day_offset),
        time(hour, local_minute),
        tzinfo=APP_TIMEZONE,
    )


def _deterministic_spread_seconds(
    character_id: str,
    reason: str,
    bucket: str,
    max_seconds: int,
) -> int:
    if max_seconds <= 0:
        return 0
    payload = f"{character_id}:{reason}:{bucket}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") % (max_seconds + 1)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
