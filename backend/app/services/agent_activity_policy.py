from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app import models
from app.core import agent_activity_schedule
from app.cruds import agents as agent_crud


APP_TIMEZONE = agent_activity_schedule.APP_TIMEZONE
TickSchedule = agent_activity_schedule.TickSchedule
tick_interval_seconds = agent_activity_schedule.tick_interval_seconds
next_tick_schedule = agent_activity_schedule.next_tick_schedule
initial_tick_schedule = agent_activity_schedule.initial_tick_schedule
retry_tick_schedule = agent_activity_schedule.retry_tick_schedule
recovery_tick_schedule = agent_activity_schedule.recovery_tick_schedule
_is_within_active_hours = agent_activity_schedule.is_within_active_hours
_aware_utc = agent_activity_schedule.aware_utc
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


def activity_timezone(db: Session, *, character_id: str) -> ZoneInfo:
    """Resolve the selected World's IANA timezone, falling back to KST."""

    inspector = inspect(db.get_bind())
    if not inspector.has_table(models.CharacterActiveWorld.__tablename__):
        return APP_TIMEZONE
    active_world = db.get(models.CharacterActiveWorld, character_id)
    if active_world is None:
        return APP_TIMEZONE
    if not inspector.has_table(models.WorldCharacter.__tablename__):
        return APP_TIMEZONE
    world_character = db.get(models.WorldCharacter, active_world.world_character_id)
    if world_character is None or world_character.character_id != character_id:
        return APP_TIMEZONE
    if not inspector.has_table(models.World.__tablename__):
        return APP_TIMEZONE
    world = db.get(models.World, world_character.world_id)
    if world is None:
        return APP_TIMEZONE
    try:
        return ZoneInfo(world.timezone)
    except (KeyError, ValueError):
        return APP_TIMEZONE


def activity_timezone_name(db: Session, *, character_id: str) -> str:
    return activity_timezone(db, character_id=character_id).key


def is_policy_enforced_session(session_key: str) -> bool:
    return (
        POLICY_SESSION_MARKER in session_key
        or MANUAL_POLICY_SESSION_MARKER in session_key
    )


def is_manual_policy_session(session_key: str) -> bool:
    return MANUAL_POLICY_SESSION_MARKER in session_key


def is_imported_world_runtime_locked(
    db: Session,
    world_character: models.WorldCharacter,
) -> bool:
    """Return whether package lineage still requires explicit autonomy enable.

    Direct-created characters retain the user-initiated manual-run contract.
    Imported Worlds are stricter: P4-P7 must remain inert while their active
    WorldCharacter is autonomy-disabled, even in a resident-manual session.
    """

    if world_character.autonomous_enabled:
        return False
    bind = db.get_bind()
    if not inspect(bind).has_table(models.WorldPackageImport.__tablename__):
        # Focused service fixtures may intentionally omit the v1 package
        # registry. Migrated production runtimes always have this table.
        return False
    return (
        db.scalar(
            select(models.WorldPackageImport.import_id)
            .where(
                models.WorldPackageImport.imported_world_id
                == world_character.world_id
            )
            .limit(1)
        )
        is not None
    )


def is_imported_world_runtime_locked_for_character(
    db: Session,
    *,
    character_id: str,
) -> bool:
    """Apply the import activation gate before an active World exists, too."""

    bind = db.get_bind()
    if not inspect(bind).has_table(models.WorldPackageImport.__tablename__):
        return False
    active_world = db.get(models.CharacterActiveWorld, character_id)
    if active_world is not None:
        world_character = db.get(
            models.WorldCharacter, active_world.world_character_id
        )
    else:
        world_character = db.scalar(
            select(models.WorldCharacter)
            .join(
                models.WorldPackageImport,
                models.WorldPackageImport.imported_world_id
                == models.WorldCharacter.world_id,
            )
            .where(models.WorldCharacter.character_id == character_id)
            .order_by(models.WorldCharacter.created_at.desc())
            .limit(1)
        )
    return bool(
        world_character is not None
        and not world_character.autonomous_enabled
        and db.scalar(
            select(models.WorldPackageImport.import_id)
            .where(
                models.WorldPackageImport.imported_world_id
                == world_character.world_id
            )
            .limit(1)
        )
        is not None
    )


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


def build_activity_policy(
    db: Session,
    *,
    character_id: str,
    now: datetime | None = None,
    ignore_active_hours: bool = False,
) -> ActivityPolicy:
    setting = agent_crud.ensure_setting(db, character_id)
    current = _aware_utc(now or datetime.now(UTC))
    timezone = activity_timezone(db, character_id=character_id)
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
        timezone=activity_timezone(db, character_id=character_id),
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


def _count_action_today(
    db: Session,
    character_id: str,
    action_types: str | tuple[str, ...],
    now: datetime,
    *,
    timezone: ZoneInfo = APP_TIMEZONE,
) -> int:
    local_now = now.astimezone(timezone)
    day_start = datetime.combine(local_now.date(), time.min, tzinfo=timezone)
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
