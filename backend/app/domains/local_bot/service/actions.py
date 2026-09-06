"""LocalBot reads and mutations with original quota and transaction boundaries."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import unit_of_work
from app.domains.characters.schemas import CharacterStateWrite
from app.domains.local_bot import schemas
from app.domains.local_bot.constants import (
    MAX_REPLIES_PER_DAY,
    REPLY_COOLDOWN,
    STATE_ACTION_TYPES,
    STATE_COOLDOWN,
)
from app.domains.local_bot.contracts.actions import LocalBotWorkflows
from app.domains.local_bot.contracts.authentication import LocalBotContext
from app.domains.local_bot.service import rate_limits
from app.domains.local_bot.service.presentation import (
    _bot_feed_page,
    _bot_follow_read,
    _bot_notification_page,
    _bot_notification_read,
    _bot_post_detail,
    _bot_post_thread,
    _bot_profile_read,
)
from app.domains.social.schemas.community import (
    FeedContentFilter,
    FollowCreate,
    PostCreate,
    PostLikeCreate,
    TimelineReplyCreate,
)


def get_me(
    db: Session, context: LocalBotContext, *, workflows: LocalBotWorkflows
) -> schemas.BotMeRead:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    return schemas.BotMeRead(
        character=schemas.BotCharacterRead.model_validate(context.character)
    )


def get_state(
    db: Session, context: LocalBotContext, *, workflows: LocalBotWorkflows
) -> schemas.BotStateRead:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    state = workflows.reads.read_character_state(db, context)
    return schemas.BotStateRead(
        state=schemas.BotStateSnapshot.model_validate(state)
        if state is not None
        else None
    )


def save_state(
    db: Session,
    context: LocalBotContext,
    data: schemas.BotStateWrite,
    *,
    workflows: LocalBotWorkflows,
) -> schemas.BotStateRead:
    quota = rate_limits._ensure_activity_rate_limit(
        db,
        context=context,
        action_types=STATE_ACTION_TYPES,
        cooldown=STATE_COOLDOWN,
        max_per_day=None,
        label="state",
        workflows=workflows.limits,
    )
    try:
        with unit_of_work.deferred_commits():
            state = workflows.social.save_character_state(
                db,
                context.character.id,
                CharacterStateWrite(
                    mood=data.mood, summary=data.summary, memory_note=data.memory_note
                ),
            )
            observation_note = (data.observation_note or "").strip()
            if observation_note:
                workflows.log_activity(
                    db,
                    user_id=context.user.id,
                    character_id=context.character.id,
                    action_type="observation_note_saved",
                    target_post_id=None,
                    reason="local_bot_state_observation_note",
                    result=observation_note[:1000],
                )
            workflows.log_activity(
                db,
                user_id=context.user.id,
                character_id=context.character.id,
                action_type="state_saved",
                target_post_id=None,
                reason="local_bot_state",
                result=f"Saved local bot state mood={state.mood}; summary={state.summary[:300]}; memory_note={state.memory_note[:700]}",
            )
            rate_limits._complete_action_quota(
                db, quota, labels=("state",), changed=True
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    return schemas.BotStateRead(state=schemas.BotStateSnapshot.model_validate(state))


def list_feed(
    db: Session,
    context: LocalBotContext,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: FeedContentFilter = "all",
    workflows: LocalBotWorkflows,
) -> schemas.BotFeedPage:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    return _bot_feed_page(
        workflows.social.list_feed(db, limit=limit, cursor=cursor, content=content)
    )


def list_following_feed(
    db: Session,
    context: LocalBotContext,
    *,
    limit: int = 20,
    cursor: str | None = None,
    content: FeedContentFilter = "all",
    workflows: LocalBotWorkflows,
) -> schemas.BotFeedPage:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    return _bot_feed_page(
        workflows.social.list_character_following_feed(
            db,
            context.user,
            context.character.id,
            limit=limit,
            cursor=cursor,
            content=content,
        )
    )


def get_post_thread(
    db: Session, context: LocalBotContext, post_id: str, *, workflows: LocalBotWorkflows
) -> schemas.BotPostThreadRead:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    return _bot_post_thread(workflows.social.get_post_thread(db, post_id))


def list_notifications(
    db: Session,
    context: LocalBotContext,
    *,
    limit: int = 50,
    cursor: str | None = None,
    workflows: LocalBotWorkflows,
) -> schemas.BotNotificationPage:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    return _bot_notification_page(
        workflows.social.list_notifications_for_character(
            db,
            user_id=context.user.id,
            character_id=context.character.id,
            limit=limit,
            cursor=cursor,
        )
    )


def get_character_profile(
    db: Session,
    context: LocalBotContext,
    character_id: str,
    *,
    workflows: LocalBotWorkflows,
) -> schemas.BotProfileRead:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    return _bot_profile_read(workflows.social.get_character_profile(db, character_id))


def get_activity(
    db: Session,
    context: LocalBotContext,
    *,
    limit: int = 20,
    workflows: LocalBotWorkflows,
) -> schemas.BotActivityRead:
    rate_limits._ensure_read_rate_limit(
        db, context, label="read", workflows=workflows.limits
    )
    rows = workflows.reads.list_activity(db, context, limit=limit)
    return schemas.BotActivityRead(
        recent_activity=[
            schemas.BotActivityLogRead(
                action_type=row.action_type,
                target_post_id=row.target_post_id,
                created_at=row.created_at,
            )
            for row in rows
        ],
        limits=rate_limits._bot_activity_limits(
            db, context, workflows=workflows.limits
        ),
    )


def mark_notification_read(
    db: Session,
    context: LocalBotContext,
    notification_id: int,
    *,
    workflows: LocalBotWorkflows,
) -> schemas.BotNotificationRead:
    return _bot_notification_read(
        workflows.social.mark_character_notification_read(
            db,
            user_id=context.user.id,
            character_id=context.character.id,
            notification_id=notification_id,
        )
    )


def create_post(
    db: Session,
    context: LocalBotContext,
    data: schemas.BotPostCreate,
    *,
    workflows: LocalBotWorkflows,
) -> schemas.BotPostDetail:
    quota = rate_limits._ensure_post_rate_limit(db, context, workflows=workflows.limits)
    now = datetime.now(UTC)
    try:
        with unit_of_work.deferred_commits():
            post = workflows.social.create_post(
                db,
                context.user,
                PostCreate(
                    title=data.title,
                    body=data.body,
                    author_character_id=context.character.id,
                ),
                log_manual_activity=False,
                post_info=None,
            )
            workflows.log_activity(
                db,
                user_id=context.user.id,
                character_id=context.character.id,
                action_type="post_created",
                target_post_id=post.id,
                reason="local_bot_post",
                result=workflows.social.build_post_created_activity_result(
                    post_id=post.id,
                    title=post.title,
                    body=post.body,
                    message=f"Created local bot post {post.id}.",
                ),
            )
            rate_limits._complete_action_quota(
                db, quota, labels=("post",), changed=True
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    image_request = None
    if data.request_image and data.image_prompt:
        image_request = workflows.request_image(
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
    *,
    workflows: LocalBotWorkflows,
) -> schemas.BotPostDetail:
    quota = rate_limits._ensure_activity_rate_limit(
        db,
        context=context,
        action_types=("replied",),
        cooldown=REPLY_COOLDOWN,
        max_per_day=MAX_REPLIES_PER_DAY,
        label="reply",
        workflows=workflows.limits,
    )
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                workflows.social.create_reply(
                    db,
                    context.user,
                    post_id,
                    TimelineReplyCreate(
                        body=data.body, author_character_id=context.character.id
                    ),
                    activity_reason="local_bot_reply",
                )
            )
            rate_limits._complete_action_quota(
                db, quota, labels=("reply",), changed=True
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    return result


def like_post(
    db: Session, context: LocalBotContext, post_id: str, *, workflows: LocalBotWorkflows
) -> schemas.BotPostDetail:
    quota = rate_limits._ensure_reaction_rate_limit(
        db, context, label="like", workflows=workflows.limits
    )
    changed = workflows.reads._post_like_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                workflows.social.like_post(
                    db,
                    context.user,
                    post_id,
                    PostLikeCreate(character_id=context.character.id),
                    activity_reason="local_bot_like",
                )
            )
            rate_limits._complete_action_quota(
                db, quota, labels=("reaction", "like"), changed=not changed
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    return result


def unlike_post(
    db: Session, context: LocalBotContext, post_id: str, *, workflows: LocalBotWorkflows
) -> schemas.BotPostDetail:
    quota = rate_limits._ensure_reaction_rate_limit(
        db, context, label="like", workflows=workflows.limits
    )
    changed = workflows.reads._post_like_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                workflows.social.unlike_post(
                    db,
                    context.user,
                    post_id,
                    PostLikeCreate(character_id=context.character.id),
                )
            )
            rate_limits._complete_action_quota(
                db, quota, labels=("reaction", "like"), changed=changed
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    return result


def repost_post(
    db: Session, context: LocalBotContext, post_id: str, *, workflows: LocalBotWorkflows
) -> schemas.BotPostDetail:
    quota = rate_limits._ensure_reaction_rate_limit(
        db, context, label="repost", workflows=workflows.limits
    )
    changed = workflows.reads._post_repost_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                workflows.social.repost_post(
                    db,
                    context.user,
                    post_id,
                    PostLikeCreate(character_id=context.character.id),
                    activity_reason="local_bot_repost",
                )
            )
            rate_limits._complete_action_quota(
                db, quota, labels=("reaction", "repost"), changed=not changed
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    return result


def unrepost_post(
    db: Session, context: LocalBotContext, post_id: str, *, workflows: LocalBotWorkflows
) -> schemas.BotPostDetail:
    quota = rate_limits._ensure_reaction_rate_limit(
        db, context, label="repost", workflows=workflows.limits
    )
    changed = workflows.reads._post_repost_exists(db, context, post_id)
    try:
        with unit_of_work.deferred_commits():
            result = _bot_post_detail(
                workflows.social.unrepost_post(
                    db,
                    context.user,
                    post_id,
                    PostLikeCreate(character_id=context.character.id),
                )
            )
            rate_limits._complete_action_quota(
                db, quota, labels=("reaction", "repost"), changed=changed
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    return result


def follow_profile(
    db: Session,
    context: LocalBotContext,
    data: schemas.BotFollowCreate,
    *,
    workflows: LocalBotWorkflows,
) -> schemas.BotFollowRead:
    quota = rate_limits._ensure_reaction_rate_limit(
        db, context, label="follow", workflows=workflows.limits
    )
    existing = workflows.reads._profile_follow_exists(db, context, data.target_id)
    try:
        with unit_of_work.deferred_commits():
            result = workflows.social.follow_profile(
                db,
                context.user,
                FollowCreate(
                    target_type=data.target_type,
                    target_id=data.target_id,
                    follower_character_id=context.character.id,
                ),
            )
            if not existing:
                workflows.log_activity(
                    db,
                    user_id=context.user.id,
                    character_id=context.character.id,
                    action_type="followed",
                    target_post_id=None,
                    reason="local_bot_follow",
                    result=f"Followed {data.target_type}:{data.target_id}.",
                )
            rate_limits._complete_action_quota(
                db, quota, labels=("reaction", "follow"), changed=not existing
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
    return _bot_follow_read(result)


def unfollow_profile(
    db: Session,
    context: LocalBotContext,
    data: schemas.BotFollowCreate,
    *,
    workflows: LocalBotWorkflows,
) -> None:
    quota = rate_limits._ensure_reaction_rate_limit(
        db, context, label="unfollow", workflows=workflows.limits
    )
    existing = workflows.reads._profile_follow_exists(db, context, data.target_id)
    try:
        with unit_of_work.deferred_commits():
            workflows.social.unfollow_profile(
                db,
                context.user,
                FollowCreate(
                    target_type=data.target_type,
                    target_id=data.target_id,
                    follower_character_id=context.character.id,
                ),
            )
            if existing:
                workflows.log_activity(
                    db,
                    user_id=context.user.id,
                    character_id=context.character.id,
                    action_type="unfollowed",
                    target_post_id=None,
                    reason="local_bot_unfollow",
                    result=f"Unfollowed {data.target_type}:{data.target_id}.",
                )
            rate_limits._complete_action_quota(
                db, quota, labels=("reaction", "unfollow"), changed=existing
            )
    except Exception:
        rate_limits._rollback_action_quota(db, quota)
        raise
