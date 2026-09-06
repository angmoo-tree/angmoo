"""Actual LocalBot admission, usage display, commit and Retry-After policy."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.local_bot import schemas
from app.domains.local_bot.constants import (
    MAX_POSTS_PER_DAY,
    MAX_REACTIONS_PER_DAY,
    MAX_READS_PER_WINDOW,
    MAX_REPLIES_PER_DAY,
    POST_COOLDOWN,
    REACTION_ACTION_TYPES,
    REACTION_COOLDOWN,
    REACTION_COOLDOWN_ACTION_TYPES,
    READ_WINDOW,
    REPLY_COOLDOWN,
    STATE_ACTION_TYPES,
    STATE_COOLDOWN,
)
from app.domains.local_bot.contracts.authentication import LocalBotContext
from app.domains.local_bot.contracts.rate_limits import RateLimitWorkflows
from app.domains.local_bot.exceptions import LocalBotRateLimitError
from app.domains.local_bot.policies.rate_limit_clock import (
    _local_day_start_utc,
    _next_local_day_start_utc,
    _remaining_seconds,
    _seconds_until,
)
from app.domains.local_bot.service import quota as local_bot_quota


def _ensure_post_rate_limit(
    db: Session, context: LocalBotContext, *, workflows: RateLimitWorkflows
) -> local_bot_quota.ActionQuota | None:
    if isinstance(db, Session):
        quota = local_bot_quota.lock_action_quota(
            db, character_id=context.character.id, labels=("post",)
        )
        try:
            quota.ensure_allowed(
                "post",
                cooldown=POST_COOLDOWN,
                max_per_day=MAX_POSTS_PER_DAY,
                message="Local bot post limit is reached.",
            )
        except local_bot_quota.QuotaExceeded as exc:
            db.rollback()
            _raise_rate_limit(
                db,
                context,
                label=exc.label,
                message=exc.message,
                retry_after_seconds=exc.retry_after_seconds,
                workflows=workflows,
            )
        return quota
    now = datetime.now(UTC)
    recent_post = workflows.reads.recent_root_post_at(db, context, now=now)
    if recent_post is not None:
        _raise_rate_limit(
            db,
            context,
            label="post",
            message="Local bot post cooldown is active.",
            retry_after_seconds=_seconds_until(recent_post + POST_COOLDOWN, now),
            workflows=workflows,
        )
    day_start = _local_day_start_utc(now)
    today_count = workflows.reads.count_root_posts_since(
        db, context, day_start=day_start
    )
    if (today_count or 0) >= MAX_POSTS_PER_DAY:
        _raise_rate_limit(
            db,
            context,
            label="post",
            message="Local bot daily post limit is reached.",
            retry_after_seconds=_seconds_until(_next_local_day_start_utc(now), now),
            workflows=workflows,
        )
    return None


def _bot_activity_limits(
    db: Session, context: LocalBotContext, *, workflows: RateLimitWorkflows
) -> list[schemas.BotActivityLimitRead]:
    now = datetime.now(UTC)
    day_start = _local_day_start_utc(now)
    reaction_used_today = workflows.reads._count_activities_today(
        db, context, action_types=REACTION_ACTION_TYPES, day_start=day_start
    )
    return [
        _post_limit_status(
            db, context, now=now, day_start=day_start, workflows=workflows
        ),
        _activity_limit_status(
            db,
            context,
            action="reply",
            action_types=("replied",),
            cooldown=REPLY_COOLDOWN,
            max_per_day=MAX_REPLIES_PER_DAY,
            now=now,
            day_start=day_start,
            workflows=workflows,
        ),
        schemas.BotActivityLimitRead(
            action="reaction",
            used_today=reaction_used_today,
            max_per_day=MAX_REACTIONS_PER_DAY,
            cooldown_seconds=0,
            retry_after_seconds=_seconds_until(_next_local_day_start_utc(now), now)
            if reaction_used_today >= MAX_REACTIONS_PER_DAY
            else None,
        ),
        *[
            _activity_limit_status(
                db,
                context,
                action=action,
                action_types=action_types,
                cooldown=REACTION_COOLDOWN,
                max_per_day=MAX_REACTIONS_PER_DAY,
                used_today_override=reaction_used_today,
                now=now,
                day_start=day_start,
                workflows=workflows,
            )
            for action, action_types in REACTION_COOLDOWN_ACTION_TYPES.items()
        ],
        _activity_limit_status(
            db,
            context,
            action="state",
            action_types=STATE_ACTION_TYPES,
            cooldown=STATE_COOLDOWN,
            max_per_day=None,
            now=now,
            day_start=day_start,
            workflows=workflows,
        ),
    ]


def _post_limit_status(
    db: Session,
    context: LocalBotContext,
    *,
    now: datetime,
    day_start: datetime,
    workflows: RateLimitWorkflows,
) -> schemas.BotActivityLimitRead:
    latest = workflows.reads.latest_root_post_at(db, context)
    used_today = (
        workflows.reads.root_post_usage_since(db, context, day_start=day_start) or 0
    )
    cooldown_remaining = _remaining_seconds(latest, POST_COOLDOWN, now)
    retry_after = cooldown_remaining or (
        _seconds_until(_next_local_day_start_utc(now), now)
        if used_today >= MAX_POSTS_PER_DAY
        else None
    )
    return schemas.BotActivityLimitRead(
        action="post",
        used_today=used_today,
        max_per_day=MAX_POSTS_PER_DAY,
        cooldown_seconds=int(POST_COOLDOWN.total_seconds()),
        cooldown_remaining_seconds=cooldown_remaining,
        retry_after_seconds=retry_after,
    )


def _activity_limit_status(
    db: Session,
    context: LocalBotContext,
    *,
    action: str,
    action_types: tuple[str, ...],
    cooldown: timedelta,
    max_per_day: int | None,
    now: datetime,
    day_start: datetime,
    used_today_override: int | None = None,
    workflows: RateLimitWorkflows,
) -> schemas.BotActivityLimitRead:
    latest = workflows.reads._latest_activity_at(db, context, action_types=action_types)
    used_today = (
        used_today_override
        if used_today_override is not None
        else workflows.reads._count_activities_today(
            db, context, action_types=action_types, day_start=day_start
        )
    )
    cooldown_remaining = _remaining_seconds(latest, cooldown, now)
    retry_after = cooldown_remaining or (
        _seconds_until(_next_local_day_start_utc(now), now)
        if max_per_day is not None and used_today >= max_per_day
        else None
    )
    return schemas.BotActivityLimitRead(
        action=action,
        used_today=used_today,
        max_per_day=max_per_day,
        cooldown_seconds=int(cooldown.total_seconds()),
        cooldown_remaining_seconds=cooldown_remaining,
        retry_after_seconds=retry_after,
    )


def _ensure_reaction_rate_limit(
    db: Session, context: LocalBotContext, *, label: str, workflows: RateLimitWorkflows
) -> local_bot_quota.ActionQuota | None:
    if isinstance(db, Session):
        quota = local_bot_quota.lock_action_quota(
            db, character_id=context.character.id, labels=("reaction", label)
        )
        try:
            quota.ensure_allowed(
                "reaction",
                cooldown=timedelta(0),
                max_per_day=MAX_REACTIONS_PER_DAY,
                message="Local bot daily reaction limit is reached.",
            )
            quota.ensure_allowed(
                label,
                cooldown=REACTION_COOLDOWN,
                max_per_day=None,
                message=f"Local bot {label} cooldown is active.",
            )
        except local_bot_quota.QuotaExceeded as exc:
            db.rollback()
            _raise_rate_limit(
                db,
                context,
                label=exc.label,
                message=exc.message,
                retry_after_seconds=exc.retry_after_seconds,
                workflows=workflows,
            )
        return quota
    _ensure_reaction_daily_limit(db, context, workflows=workflows)
    _ensure_activity_rate_limit(
        db,
        context=context,
        action_types=REACTION_COOLDOWN_ACTION_TYPES[label],
        cooldown=REACTION_COOLDOWN,
        max_per_day=None,
        label=label,
        workflows=workflows,
    )
    return None


def _ensure_reaction_daily_limit(
    db: Session, context: LocalBotContext, *, workflows: RateLimitWorkflows
) -> None:
    now = datetime.now(UTC)
    day_start = _local_day_start_utc(now)
    today_count = workflows.reads.reaction_usage_since(db, context, day_start=day_start)
    if (today_count or 0) >= MAX_REACTIONS_PER_DAY:
        _raise_rate_limit(
            db,
            context,
            label="reaction",
            message="Local bot daily reaction limit is reached.",
            retry_after_seconds=_seconds_until(_next_local_day_start_utc(now), now),
            workflows=workflows,
        )


def _ensure_activity_rate_limit(
    db: Session,
    *,
    context: LocalBotContext,
    action_types: tuple[str, ...],
    cooldown: timedelta,
    max_per_day: int | None,
    label: str,
    workflows: RateLimitWorkflows,
) -> local_bot_quota.ActionQuota | None:
    if isinstance(db, Session):
        quota = local_bot_quota.lock_action_quota(
            db, character_id=context.character.id, labels=(label,)
        )
        try:
            quota.ensure_allowed(
                label,
                cooldown=cooldown,
                max_per_day=max_per_day,
                message=f"Local bot {label} limit is reached.",
            )
        except local_bot_quota.QuotaExceeded as exc:
            db.rollback()
            _raise_rate_limit(
                db,
                context,
                label=exc.label,
                message=exc.message,
                retry_after_seconds=exc.retry_after_seconds,
                workflows=workflows,
            )
        return quota
    now = datetime.now(UTC)
    recent_activity = workflows.reads.recent_activity_at(
        db, context, action_types=action_types, now=now, cooldown=cooldown
    )
    if recent_activity is not None:
        _raise_rate_limit(
            db,
            context,
            label=label,
            message=f"Local bot {label} cooldown is active.",
            retry_after_seconds=_seconds_until(recent_activity + cooldown, now),
            workflows=workflows,
        )
    if max_per_day is not None:
        day_start = _local_day_start_utc(now)
        today_count = workflows.reads.activity_usage_since(
            db, context, action_types=action_types, day_start=day_start
        )
        if (today_count or 0) >= max_per_day:
            _raise_rate_limit(
                db,
                context,
                label=label,
                message=f"Local bot daily {label} limit is reached.",
                retry_after_seconds=_seconds_until(_next_local_day_start_utc(now), now),
                workflows=workflows,
            )
    return None


def _ensure_read_rate_limit(
    db: Session, context: LocalBotContext, *, label: str, workflows: RateLimitWorkflows
) -> None:
    try:
        local_bot_quota.consume_read(
            db,
            local_key_id=context.local_key.id,
            limit=MAX_READS_PER_WINDOW,
            window=READ_WINDOW,
        )
    except local_bot_quota.QuotaExceeded as exc:
        db.rollback()
        _raise_rate_limit(
            db,
            context,
            label=label,
            message=exc.message,
            retry_after_seconds=exc.retry_after_seconds,
            workflows=workflows,
        )


def _complete_action_quota(
    db: Session,
    quota: local_bot_quota.ActionQuota | None,
    *,
    labels: tuple[str, ...],
    changed: bool,
) -> None:
    if quota is None:
        return
    if changed:
        quota.consume(labels)
    db.commit()


def _rollback_action_quota(
    db: Session, quota: local_bot_quota.ActionQuota | None
) -> None:
    if quota is not None:
        db.rollback()


def _raise_rate_limit(
    db: Session,
    context: LocalBotContext,
    *,
    label: str,
    message: str,
    retry_after_seconds: int,
    workflows: RateLimitWorkflows,
) -> None:
    _log_rate_limit(
        db,
        context,
        label=label,
        retry_after_seconds=retry_after_seconds,
        workflows=workflows,
    )
    raise LocalBotRateLimitError(message, retry_after_seconds=retry_after_seconds)


def _log_rate_limit(
    db: Session,
    context: LocalBotContext,
    *,
    label: str,
    retry_after_seconds: int,
    workflows: RateLimitWorkflows,
) -> None:
    now = datetime.now(UTC)
    recent_log = workflows.reads.recent_rate_limit_log_id(
        db, context, now=now, label=label
    )
    if recent_log is not None:
        return
    workflows.log_activity(
        db,
        user_id=context.user.id,
        character_id=context.character.id,
        action_type="local_bot_rate_limited",
        target_post_id=None,
        reason="local_bot_rate_limit",
        result=f"label={label}; retry_after_seconds={retry_after_seconds}; token_prefix={context.local_key.token_prefix}",
    )
