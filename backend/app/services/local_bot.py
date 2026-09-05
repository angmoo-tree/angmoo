from functools import partial
from app.domains.local_bot.service import rate_limits
from app.runtime.local_bot.rate_limits import build_rate_limit_workflows
_ensure_post_rate_limit = partial(rate_limits._ensure_post_rate_limit, workflows=build_rate_limit_workflows())
_bot_activity_limits = partial(rate_limits._bot_activity_limits, workflows=build_rate_limit_workflows())
_post_limit_status = partial(rate_limits._post_limit_status, workflows=build_rate_limit_workflows())
_activity_limit_status = partial(rate_limits._activity_limit_status, workflows=build_rate_limit_workflows())
_ensure_reaction_rate_limit = partial(rate_limits._ensure_reaction_rate_limit, workflows=build_rate_limit_workflows())
_ensure_reaction_daily_limit = partial(rate_limits._ensure_reaction_daily_limit, workflows=build_rate_limit_workflows())
_ensure_activity_rate_limit = partial(rate_limits._ensure_activity_rate_limit, workflows=build_rate_limit_workflows())
_ensure_read_rate_limit = partial(rate_limits._ensure_read_rate_limit, workflows=build_rate_limit_workflows())
_complete_action_quota = rate_limits._complete_action_quota
_rollback_action_quota = rate_limits._rollback_action_quota
_raise_rate_limit = partial(rate_limits._raise_rate_limit, workflows=build_rate_limit_workflows())
_log_rate_limit = partial(rate_limits._log_rate_limit, workflows=build_rate_limit_workflows())
from app.runtime.local_bot import queries as local_bot_queries
from app.runtime.local_bot.queries import (_latest_activity_at, _count_activities_today, _post_like_exists, _post_repost_exists, _profile_follow_exists)
from app.domains.local_bot.contracts.authentication import LocalBotContext
from app.domains.local_bot.service.presentation import (_bot_post_reference, _bot_post_summary, _bot_post_detail, _bot_feed_page, _bot_post_thread, _bot_notification_read, _bot_notification_page, _bot_profile_ref, _bot_follow_read, _bot_profile_read)
from app.domains.local_bot.policies.rate_limit_clock import (_remaining_seconds, _local_day_start_utc, _next_local_day_start_utc, _seconds_until)
from app.domains.local_bot.exceptions import LocalBotAuthError, LocalBotError, LocalBotForbiddenError, LocalBotModeError, LocalBotRateLimitError
from app.domains.local_bot.constants import MAX_POSTS_PER_DAY, MAX_REACTIONS_PER_DAY, MAX_READS_PER_WINDOW, MAX_REPLIES_PER_DAY, POST_COOLDOWN, RATE_LIMIT_LOG_DEDUPE_WINDOW, REACTION_ACTION_TYPES, REACTION_COOLDOWN, REACTION_COOLDOWN_ACTION_TYPES, READ_WINDOW, REPLY_COOLDOWN, STATE_ACTION_TYPES, STATE_COOLDOWN
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import schemas
from app.core import unit_of_work
from app.cruds import agents as agent_crud
from app.services import community as community_service
from app.services import post_image_generation


def get_me(db: Session, context: LocalBotContext) -> schemas.BotMeRead:
    _ensure_read_rate_limit(db, context, label="read")
    return schemas.BotMeRead(
        character=schemas.BotCharacterRead.model_validate(context.character),
    )


def get_state(db: Session, context: LocalBotContext) -> schemas.BotStateRead:
    _ensure_read_rate_limit(db, context, label="read")
    state = local_bot_queries.read_character_state(db, context)
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
    rows = local_bot_queries.list_activity(db, context, limit=limit)
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







































