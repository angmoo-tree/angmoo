from app.domains.local_bot.contracts.authentication import LocalBotContext
from app.domains.local_bot.service.presentation import (_bot_post_reference, _bot_post_summary, _bot_post_detail, _bot_feed_page, _bot_post_thread, _bot_notification_read, _bot_notification_page, _bot_profile_ref, _bot_follow_read, _bot_profile_read)
from app.domains.local_bot.policies.rate_limit_clock import (_remaining_seconds, _local_day_start_utc, _next_local_day_start_utc, _seconds_until)
from app.domains.local_bot.exceptions import LocalBotAuthError, LocalBotError, LocalBotForbiddenError, LocalBotModeError, LocalBotRateLimitError
from app.domains.local_bot.constants import MAX_POSTS_PER_DAY, MAX_REACTIONS_PER_DAY, MAX_READS_PER_WINDOW, MAX_REPLIES_PER_DAY, POST_COOLDOWN, RATE_LIMIT_LOG_DEDUPE_WINDOW, REACTION_ACTION_TYPES, REACTION_COOLDOWN, REACTION_COOLDOWN_ACTION_TYPES, READ_WINDOW, REPLY_COOLDOWN, STATE_ACTION_TYPES, STATE_COOLDOWN
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app import schemas
from app.core import unit_of_work
from app.cruds import agents as agent_crud
from app.services import agent_activity_policy
from app.services import community as community_service
from app.domains.local_bot.service import quota as local_bot_quota
from app.services import post_image_generation


def get_me(db: Session, context: LocalBotContext) -> schemas.BotMeRead:
    _ensure_read_rate_limit(db, context, label="read")
    return schemas.BotMeRead(
        character=schemas.BotCharacterRead.model_validate(context.character),
    )


def get_state(db: Session, context: LocalBotContext) -> schemas.BotStateRead:
    _ensure_read_rate_limit(db, context, label="read")
    state = db.get(models.CharacterState, context.character.id)
    return schemas.BotStateRead(
        state=schemas.BotStateSnapshot.model_validate(state) if state is not None else None
    )


def save_state(
    db: Session, context: LocalBotContext, data: schemas.BotStateWrite
) -> schemas.BotStateRead:
    quota = _ensure_activity_rate_limit(
        db,
        context=context,
        action_types=STATE_ACTION_TYPES,
        cooldown=STATE_COOLDOWN,
        max_per_day=None,
        label="state",
    )
    try:
        with unit_of_work.deferred_commits():
            state = community_service.save_character_state(
                db,
                context.character.id,
                schemas.CharacterStateWrite(
                    mood=data.mood,
                    summary=data.summary,
                    memory_note=data.memory_note,
                ),
            )
            observation_note = (data.observation_note or "").strip()
            if observation_note:
                agent_crud.log_activity(
                    db,
                    user_id=context.user.id,
                    character_id=context.character.id,
                    action_type="observation_note_saved",
                    target_post_id=None,
                    reason="local_bot_state_observation_note",
                    result=observation_note[:1000],
                )
            agent_crud.log_activity(
                db,
                user_id=context.user.id,
                character_id=context.character.id,
                action_type="state_saved",
                target_post_id=None,
                reason="local_bot_state",
                result=(
                    f"Saved local bot state mood={state.mood}; "
                    f"summary={state.summary[:300]}; memory_note={state.memory_note[:700]}"
                ),
            )
            _complete_action_quota(db, quota, labels=("state",), changed=True)
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    return schemas.BotStateRead(state=schemas.BotStateSnapshot.model_validate(state))


def list_feed(
    db: Session,
    context: LocalBotContext,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.BotFeedPage:
    _ensure_read_rate_limit(db, context, label="read")
    return _bot_feed_page(
        community_service.list_feed(db, limit=limit, cursor=cursor, content=content)
    )


def list_following_feed(
    db: Session,
    context: LocalBotContext,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: schemas.FeedContentFilter = "all",
) -> schemas.BotFeedPage:
    _ensure_read_rate_limit(db, context, label="read")
    return _bot_feed_page(
        community_service.list_character_following_feed(
            db,
            context.user,
            context.character.id,
            limit=limit,
            cursor=cursor,
            content=content,
        )
    )


def get_post_thread(
    db: Session, context: LocalBotContext, post_id: str
) -> schemas.BotPostThreadRead:
    _ensure_read_rate_limit(db, context, label="read")
    return _bot_post_thread(community_service.get_post_thread(db, post_id))


def list_notifications(
    db: Session,
    context: LocalBotContext,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> schemas.BotNotificationPage:
    _ensure_read_rate_limit(db, context, label="read")
    return _bot_notification_page(
        community_service.list_notifications_for_character(
            db,
            user_id=context.user.id,
            character_id=context.character.id,
            limit=limit,
            cursor=cursor,
        )
    )


def get_character_profile(
    db: Session, context: LocalBotContext, character_id: str
) -> schemas.BotProfileRead:
    _ensure_read_rate_limit(db, context, label="read")
    return _bot_profile_read(community_service.get_character_profile(db, character_id))


def get_activity(
    db: Session, context: LocalBotContext, *, limit: int = 20
) -> schemas.BotActivityRead:
    _ensure_read_rate_limit(db, context, label="read")
    rows = db.scalars(
        select(models.AgentActivityLog)
        .where(models.AgentActivityLog.character_id == context.character.id)
        .order_by(models.AgentActivityLog.created_at.desc())
        .limit(limit)
    ).all()
    return schemas.BotActivityRead(
        recent_activity=[
            schemas.BotActivityLogRead(
                action_type=row.action_type,
                target_post_id=row.target_post_id,
                created_at=row.created_at,
            )
            for row in rows
        ],
        limits=_bot_activity_limits(db, context),
    )


def mark_notification_read(
    db: Session, context: LocalBotContext, notification_id: int
) -> schemas.BotNotificationRead:
    return _bot_notification_read(
        community_service.mark_character_notification_read(
            db,
            user_id=context.user.id,
            character_id=context.character.id,
            notification_id=notification_id,
        )
    )


def create_post(
    db: Session, context: LocalBotContext, data: schemas.BotPostCreate
) -> schemas.BotPostDetail:
    quota = _ensure_post_rate_limit(db, context)
    now = datetime.now(UTC)
    try:
        with unit_of_work.deferred_commits():
            post = community_service.create_post(
                db,
                context.user,
                schemas.PostCreate(
                    title=data.title,
                    body=data.body,
                    author_character_id=context.character.id,
                ),
                log_manual_activity=False,
                post_info=None,
            )
            agent_crud.log_activity(
                db,
                user_id=context.user.id,
                character_id=context.character.id,
                action_type="post_created",
                target_post_id=post.id,
                reason="local_bot_post",
                result=community_service.build_post_created_activity_result(
                    post_id=post.id,
                    title=post.title,
                    body=post.body,
                    message=f"Created local bot post {post.id}.",
                ),
            )
            _complete_action_quota(db, quota, labels=("post",), changed=True)
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    image_request = None
    if data.request_image and data.image_prompt:
        image_request = post_image_generation.create_local_api_post_image_request(
            db=db,
            user_id=context.user.id,
            local_key_prefix=context.local_key.token_prefix,
            character=context.character,
            post_id=post.id,
            image_prompt=data.image_prompt,
            requested_at=now,
        )
    return _bot_post_detail(post, image_request=image_request)


def create_reply(
    db: Session,
    context: LocalBotContext,
    post_id: str,
    data: schemas.BotReplyCreate,
) -> schemas.BotPostDetail:
    quota = _ensure_activity_rate_limit(
        db,
        context=context,
        action_types=("replied",),
        cooldown=REPLY_COOLDOWN,
        max_per_day=MAX_REPLIES_PER_DAY,
        label="reply",
    )
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                community_service.create_reply(
                    db,
                    context.user,
                    post_id,
                    schemas.TimelineReplyCreate(
                        body=data.body,
                        author_character_id=context.character.id,
                    ),
                    activity_reason="local_bot_reply",
                )
            )
            _complete_action_quota(db, quota, labels=("reply",), changed=True)
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    return result


def like_post(
    db: Session, context: LocalBotContext, post_id: str
) -> schemas.BotPostDetail:
    quota = _ensure_reaction_rate_limit(db, context, label="like")
    changed = _post_like_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                community_service.like_post(
                    db,
                    context.user,
                    post_id,
                    schemas.PostLikeCreate(character_id=context.character.id),
                    activity_reason="local_bot_like",
                )
            )
            _complete_action_quota(
                db,
                quota,
                labels=("reaction", "like"),
                changed=not changed,
            )
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    return result


def unlike_post(
    db: Session, context: LocalBotContext, post_id: str
) -> schemas.BotPostDetail:
    quota = _ensure_reaction_rate_limit(db, context, label="like")
    changed = _post_like_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                community_service.unlike_post(
                    db,
                    context.user,
                    post_id,
                    schemas.PostLikeCreate(character_id=context.character.id),
                )
            )
            _complete_action_quota(
                db,
                quota,
                labels=("reaction", "like"),
                changed=changed,
            )
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    return result


def repost_post(
    db: Session, context: LocalBotContext, post_id: str
) -> schemas.BotPostDetail:
    quota = _ensure_reaction_rate_limit(db, context, label="repost")
    changed = _post_repost_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                community_service.repost_post(
                    db,
                    context.user,
                    post_id,
                    schemas.PostLikeCreate(character_id=context.character.id),
                    activity_reason="local_bot_repost",
                )
            )
            _complete_action_quota(
                db,
                quota,
                labels=("reaction", "repost"),
                changed=not changed,
            )
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    return result


def unrepost_post(
    db: Session, context: LocalBotContext, post_id: str
) -> schemas.BotPostDetail:
    quota = _ensure_reaction_rate_limit(db, context, label="repost")
    changed = _post_repost_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                community_service.unrepost_post(
                    db,
                    context.user,
                    post_id,
                    schemas.PostLikeCreate(character_id=context.character.id),
                )
            )
            _complete_action_quota(
                db,
                quota,
                labels=("reaction", "repost"),
                changed=changed,
            )
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    return result


def follow_profile(
    db: Session,
    context: LocalBotContext,
    data: schemas.BotFollowCreate,
) -> schemas.BotFollowRead:
    quota = _ensure_reaction_rate_limit(db, context, label="follow")
    existing = _profile_follow_exists(db, context, data.target_id)
    try:
        with unit_of_work.deferred_commits():
            result = community_service.follow_profile(
                db,
                context.user,
                schemas.FollowCreate(
                    target_type=data.target_type,
                    target_id=data.target_id,
                    follower_character_id=context.character.id,
                ),
            )
            if not existing:
                agent_crud.log_activity(
                    db,
                    user_id=context.user.id,
                    character_id=context.character.id,
                    action_type="followed",
                    target_post_id=None,
                    reason="local_bot_follow",
                    result=f"Followed {data.target_type}:{data.target_id}.",
                )
            _complete_action_quota(
                db,
                quota,
                labels=("reaction", "follow"),
                changed=not existing,
            )
    except Exception:
        _rollback_action_quota(db, quota)
        raise
    return _bot_follow_read(result)


def unfollow_profile(
    db: Session,
    context: LocalBotContext,
    data: schemas.BotFollowCreate,
) -> None:
    quota = _ensure_reaction_rate_limit(db, context, label="unfollow")
    existing = _profile_follow_exists(db, context, data.target_id)
    try:
        with unit_of_work.deferred_commits():
            community_service.unfollow_profile(
                db,
                context.user,
                schemas.FollowCreate(
                    target_type=data.target_type,
                    target_id=data.target_id,
                    follower_character_id=context.character.id,
                ),
            )
            if existing:
                agent_crud.log_activity(
                    db,
                    user_id=context.user.id,
                    character_id=context.character.id,
                    action_type="unfollowed",
                    target_post_id=None,
                    reason="local_bot_unfollow",
                    result=f"Unfollowed {data.target_type}:{data.target_id}.",
                )
            _complete_action_quota(
                db,
                quota,
                labels=("reaction", "unfollow"),
                changed=existing,
            )
    except Exception:
        _rollback_action_quota(db, quota)
        raise


def _ensure_post_rate_limit(
    db: Session, context: LocalBotContext
) -> local_bot_quota.ActionQuota | None:
    if isinstance(db, Session):
        quota = local_bot_quota.lock_action_quota(
            db,
            character_id=context.character.id,
            labels=("post",),
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
            )
        return quota

    now = datetime.now(UTC)
    recent_post = db.scalar(
        select(models.Post.created_at)
        .where(models.Post.author_character_id == context.character.id)
        .where(models.Post.post_type == "post")
        .where(models.Post.deleted_at.is_(None))
        .where(models.Post.created_at >= now - POST_COOLDOWN)
        .order_by(models.Post.created_at.desc())
        .limit(1)
    )
    if recent_post is not None:
        _raise_rate_limit(
            db,
            context,
            label="post",
            message="Local bot post cooldown is active.",
            retry_after_seconds=_seconds_until(recent_post + POST_COOLDOWN, now),
        )
    day_start = _local_day_start_utc(now)
    today_count = db.scalar(
        select(func.count(models.Post.id))
        .where(models.Post.author_character_id == context.character.id)
        .where(models.Post.post_type == "post")
        .where(models.Post.deleted_at.is_(None))
        .where(models.Post.created_at >= day_start)
    )
    if (today_count or 0) >= MAX_POSTS_PER_DAY:
        _raise_rate_limit(
            db,
            context,
            label="post",
            message="Local bot daily post limit is reached.",
            retry_after_seconds=_seconds_until(_next_local_day_start_utc(now), now),
        )
    return None


def _bot_activity_limits(
    db: Session, context: LocalBotContext
) -> list[schemas.BotActivityLimitRead]:
    now = datetime.now(UTC)
    day_start = _local_day_start_utc(now)
    reaction_used_today = _count_activities_today(
        db, context, action_types=REACTION_ACTION_TYPES, day_start=day_start
    )
    return [
        _post_limit_status(db, context, now=now, day_start=day_start),
        _activity_limit_status(
            db,
            context,
            action="reply",
            action_types=("replied",),
            cooldown=REPLY_COOLDOWN,
            max_per_day=MAX_REPLIES_PER_DAY,
            now=now,
            day_start=day_start,
        ),
        schemas.BotActivityLimitRead(
            action="reaction",
            used_today=reaction_used_today,
            max_per_day=MAX_REACTIONS_PER_DAY,
            cooldown_seconds=0,
            retry_after_seconds=(
                _seconds_until(_next_local_day_start_utc(now), now)
                if reaction_used_today >= MAX_REACTIONS_PER_DAY
                else None
            ),
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
        ),
    ]


def _post_limit_status(
    db: Session, context: LocalBotContext, *, now: datetime, day_start: datetime
) -> schemas.BotActivityLimitRead:
    latest = db.scalar(
        select(models.Post.created_at)
        .where(models.Post.author_character_id == context.character.id)
        .where(models.Post.post_type == "post")
        .where(models.Post.deleted_at.is_(None))
        .order_by(models.Post.created_at.desc())
        .limit(1)
    )
    used_today = db.scalar(
        select(func.count(models.Post.id))
        .where(models.Post.author_character_id == context.character.id)
        .where(models.Post.post_type == "post")
        .where(models.Post.deleted_at.is_(None))
        .where(models.Post.created_at >= day_start)
    ) or 0
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
) -> schemas.BotActivityLimitRead:
    latest = _latest_activity_at(db, context, action_types=action_types)
    used_today = (
        used_today_override
        if used_today_override is not None
        else _count_activities_today(
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


def _latest_activity_at(
    db: Session, context: LocalBotContext, *, action_types: tuple[str, ...]
) -> datetime | None:
    return db.scalar(
        select(models.AgentActivityLog.created_at)
        .where(models.AgentActivityLog.character_id == context.character.id)
        .where(models.AgentActivityLog.action_type.in_(action_types))
        .order_by(models.AgentActivityLog.created_at.desc())
        .limit(1)
    )


def _count_activities_today(
    db: Session,
    context: LocalBotContext,
    *,
    action_types: tuple[str, ...],
    day_start: datetime,
) -> int:
    return (
        db.scalar(
            select(func.count(models.AgentActivityLog.id))
            .where(models.AgentActivityLog.character_id == context.character.id)
            .where(models.AgentActivityLog.action_type.in_(action_types))
            .where(models.AgentActivityLog.created_at >= day_start)
        )
        or 0
    )


def _ensure_reaction_rate_limit(
    db: Session, context: LocalBotContext, *, label: str
) -> local_bot_quota.ActionQuota | None:
    if isinstance(db, Session):
        quota = local_bot_quota.lock_action_quota(
            db,
            character_id=context.character.id,
            labels=("reaction", label),
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
            )
        return quota

    _ensure_reaction_daily_limit(db, context)
    _ensure_activity_rate_limit(
        db,
        context=context,
        action_types=REACTION_COOLDOWN_ACTION_TYPES[label],
        cooldown=REACTION_COOLDOWN,
        max_per_day=None,
        label=label,
    )
    return None


def _ensure_reaction_daily_limit(db: Session, context: LocalBotContext) -> None:
    now = datetime.now(UTC)
    day_start = _local_day_start_utc(now)
    today_count = db.scalar(
        select(func.count(models.AgentActivityLog.id))
        .where(models.AgentActivityLog.character_id == context.character.id)
        .where(models.AgentActivityLog.action_type.in_(REACTION_ACTION_TYPES))
        .where(models.AgentActivityLog.created_at >= day_start)
    )
    if (today_count or 0) >= MAX_REACTIONS_PER_DAY:
        _raise_rate_limit(
            db,
            context,
            label="reaction",
            message="Local bot daily reaction limit is reached.",
            retry_after_seconds=_seconds_until(_next_local_day_start_utc(now), now),
        )


def _ensure_activity_rate_limit(
    db: Session,
    *,
    context: LocalBotContext,
    action_types: tuple[str, ...],
    cooldown: timedelta,
    max_per_day: int | None,
    label: str,
) -> local_bot_quota.ActionQuota | None:
    if isinstance(db, Session):
        quota = local_bot_quota.lock_action_quota(
            db,
            character_id=context.character.id,
            labels=(label,),
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
            )
        return quota

    now = datetime.now(UTC)
    recent_activity = db.scalar(
        select(models.AgentActivityLog.created_at)
        .where(models.AgentActivityLog.character_id == context.character.id)
        .where(models.AgentActivityLog.action_type.in_(action_types))
        .where(models.AgentActivityLog.created_at >= now - cooldown)
        .order_by(models.AgentActivityLog.created_at.desc())
        .limit(1)
    )
    if recent_activity is not None:
        _raise_rate_limit(
            db,
            context,
            label=label,
            message=f"Local bot {label} cooldown is active.",
            retry_after_seconds=_seconds_until(recent_activity + cooldown, now),
        )
    if max_per_day is not None:
        day_start = _local_day_start_utc(now)
        today_count = db.scalar(
            select(func.count(models.AgentActivityLog.id))
            .where(models.AgentActivityLog.character_id == context.character.id)
            .where(models.AgentActivityLog.action_type.in_(action_types))
            .where(models.AgentActivityLog.created_at >= day_start)
        )
        if (today_count or 0) >= max_per_day:
            _raise_rate_limit(
                db,
                context,
                label=label,
                message=f"Local bot daily {label} limit is reached.",
                retry_after_seconds=_seconds_until(_next_local_day_start_utc(now), now),
            )
    return None


def _ensure_read_rate_limit(db: Session, context: LocalBotContext, *, label: str) -> None:
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


def _post_like_exists(
    db: Session, context: LocalBotContext, post_id: str
) -> bool:
    if not isinstance(db, Session):
        return False
    return (
        db.scalar(
            select(models.PostLike.id).where(
                models.PostLike.post_id == post_id,
                models.PostLike.character_id == context.character.id,
            )
        )
        is not None
    )


def _post_repost_exists(
    db: Session, context: LocalBotContext, post_id: str
) -> bool:
    if not isinstance(db, Session):
        return False
    return (
        db.scalar(
            select(models.PostRepost.id).where(
                models.PostRepost.post_id == post_id,
                models.PostRepost.character_id == context.character.id,
            )
        )
        is not None
    )


def _profile_follow_exists(
    db: Session, context: LocalBotContext, target_character_id: str
) -> bool:
    if not isinstance(db, Session):
        return False
    return (
        db.scalar(
            select(models.ProfileFollow.id).where(
                models.ProfileFollow.follower_user_id.is_(None),
                models.ProfileFollow.follower_character_id == context.character.id,
                models.ProfileFollow.target_user_id.is_(None),
                models.ProfileFollow.target_character_id == target_character_id,
            )
        )
        is not None
    )


def _raise_rate_limit(
    db: Session,
    context: LocalBotContext,
    *,
    label: str,
    message: str,
    retry_after_seconds: int,
) -> None:
    _log_rate_limit(db, context, label=label, retry_after_seconds=retry_after_seconds)
    raise LocalBotRateLimitError(message, retry_after_seconds=retry_after_seconds)


def _log_rate_limit(
    db: Session,
    context: LocalBotContext,
    *,
    label: str,
    retry_after_seconds: int,
) -> None:
    now = datetime.now(UTC)
    recent_log = db.scalar(
        select(models.AgentActivityLog.id)
        .where(models.AgentActivityLog.character_id == context.character.id)
        .where(models.AgentActivityLog.action_type == "local_bot_rate_limited")
        .where(models.AgentActivityLog.created_at >= now - RATE_LIMIT_LOG_DEDUPE_WINDOW)
        .where(models.AgentActivityLog.result.like(f"label={label};%"))
        .order_by(models.AgentActivityLog.created_at.desc())
        .limit(1)
    )
    if recent_log is not None:
        return
    agent_crud.log_activity(
        db,
        user_id=context.user.id,
        character_id=context.character.id,
        action_type="local_bot_rate_limited",
        target_post_id=None,
        reason="local_bot_rate_limit",
        result=(
            f"label={label}; retry_after_seconds={retry_after_seconds}; "
            f"token_prefix={context.local_key.token_prefix}"
        ),
    )
