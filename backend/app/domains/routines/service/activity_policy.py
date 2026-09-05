"""Activity permissions, daily limits and cooldown decisions owned by Routines.

The explicit timezone reader uses the caller Session after ensure_setting, never
an eager read or a second transaction. Existing ensure_setting commit semantics
remain part of the original workflow.
"""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.domains.routines import models
from app.domains.routines.constants import PUBLIC_ACTION_TYPES, POLICY_ACTION_NAMES
from app.domains.routines.exceptions import ActivityPolicyDeniedError
from app.domains.routines.contracts.activity_policy import ActivityPolicy, ActivityTimezoneReader
from app.domains.routines.service import activity_settings as agent_crud
from app.domains.routines.service.activity_sessions import is_policy_enforced_session, is_manual_policy_session
from app.domains.routines.service.tick_schedule import aware_utc as _aware_utc, is_within_active_hours as _is_within_active_hours, next_tick_schedule
from app.domains.routines.repository.activity_counts import _count_action_today, _latest_action_at


def build_activity_policy(
    db: Session,
    *,
    character_id: str,
    now: datetime | None = None,
    ignore_active_hours: bool = False,
    timezone_reader: ActivityTimezoneReader,
) -> ActivityPolicy:
    setting = agent_crud.ensure_setting(db, character_id)
    current = _aware_utc(now or datetime.now(UTC))
    timezone = timezone_reader(db, character_id=character_id)
    actual_within_active_hours = _is_within_active_hours(
        setting, current, timezone=timezone
    )
    within_active_hours = True if ignore_active_hours else actual_within_active_hours
    schedule = next_tick_schedule(
        setting,
        character_id=character_id,
        now=current,
        within_active_hours=actual_within_active_hours,
        timezone=timezone,
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
            timezone=timezone,
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
            timezone=timezone,
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



def assert_action_allowed(db: Session, *, run: models.AgentRun, action: str, timezone_reader: ActivityTimezoneReader) -> None:
    if not is_policy_enforced_session(run.session_key):
        return
    policy = build_activity_policy(
        db,
        character_id=run.character_id,
        ignore_active_hours=is_manual_policy_session(run.session_key),
        timezone_reader=timezone_reader,
    )
    if action in policy.allowed_actions:
        return
    reason = policy.blocked_reasons.get(action, "action is not allowed for this tick")
    raise ActivityPolicyDeniedError(reason)



def count_action_today(
    db: Session,
    *,
    character_id: str,
    action: str,
    now: datetime | None = None,
    timezone_reader: ActivityTimezoneReader,
) -> int:
    action_type = PUBLIC_ACTION_TYPES[action]
    return _count_action_today(
        db,
        character_id,
        action_type,
        _aware_utc(now or datetime.now(UTC)),
        timezone=timezone_reader(db, character_id=character_id),
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
    timezone: ZoneInfo,
) -> None:
    action_label = "/".join(actions)
    if max_per_day <= 0:
        _block_actions(blocked, actions, "daily limit is 0")
        return
    today_count = _count_action_today(
        db, character_id, action_types, now, timezone=timezone
    )
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



def _block_actions(
    blocked: dict[str, str], actions: tuple[str, ...], reason: str
) -> None:
    for action in actions:
        blocked[action] = reason

