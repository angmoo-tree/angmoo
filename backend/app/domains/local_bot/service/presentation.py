"""Public LocalBot response projection without private Character state."""

from app.core.profile_ref import ProfileRef
from app.domains.local_bot import schemas
from app.domains.social.schemas.community import (
    FeedPage,
    FollowRead,
    NotificationPage,
    NotificationRead,
    PostDetail,
    PostReference,
    PostSummary,
    PostThreadRead,
    ProfileRead,
)


def _bot_post_reference(post: PostReference | None) -> schemas.BotPostReference | None:
    if post is None:
        return None
    return schemas.BotPostReference(
        id=post.id,
        author_name=post.author_name,
        author_handle=post.author_handle,
        author_avatar_url=post.author_avatar_url,
        title=post.title,
        body=post.body,
        created_at=post.created_at,
        post_type=post.post_type,
        author_character_id=post.author_character_id,
        media=post.media,
    )


def _bot_post_summary(post: PostSummary) -> schemas.BotPostSummary:
    return schemas.BotPostSummary(
        id=post.id,
        author_name=post.author_name,
        author_handle=post.author_handle,
        author_avatar_url=post.author_avatar_url,
        title=post.title,
        body=post.body,
        created_at=post.created_at,
        post_type=post.post_type,
        author_character_id=post.author_character_id,
        reply_to_post_id=post.reply_to_post_id,
        quote_post_id=post.quote_post_id,
        repost_of_post_id=post.repost_of_post_id,
        comment_count=post.comment_count,
        like_count=post.like_count,
        reply_count=post.reply_count,
        repost_count=post.repost_count,
        quote_count=post.quote_count,
        quoted_post=_bot_post_reference(post.quoted_post),
        reposted_post=_bot_post_reference(post.reposted_post),
        report_hidden=post.report_hidden,
        media=post.media,
    )


def _bot_post_detail(
    post: PostDetail,
    *,
    image_request: schemas.BotImageRequestRead | None = None,
) -> schemas.BotPostDetail:
    return schemas.BotPostDetail(
        id=post.id,
        author_name=post.author_name,
        author_handle=post.author_handle,
        author_avatar_url=post.author_avatar_url,
        title=post.title,
        body=post.body,
        created_at=post.created_at,
        post_type=post.post_type,
        author_character_id=post.author_character_id,
        reply_to_post_id=post.reply_to_post_id,
        quote_post_id=post.quote_post_id,
        repost_of_post_id=post.repost_of_post_id,
        comments=post.comments,
        like_count=post.like_count,
        reply_count=post.reply_count,
        repost_count=post.repost_count,
        quote_count=post.quote_count,
        quoted_post=_bot_post_reference(post.quoted_post),
        reposted_post=_bot_post_reference(post.reposted_post),
        report_hidden=post.report_hidden,
        media=post.media,
        image_request=image_request,
    )


def _bot_feed_page(page: FeedPage) -> schemas.BotFeedPage:
    return schemas.BotFeedPage(
        items=[_bot_post_summary(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def _bot_post_thread(thread: PostThreadRead) -> schemas.BotPostThreadRead:
    return schemas.BotPostThreadRead(
        post=_bot_post_detail(thread.post),
        replies=[_bot_post_summary(reply) for reply in thread.replies],
    )


def _bot_notification_read(
    notification: NotificationRead,
) -> schemas.BotNotificationRead:
    return schemas.BotNotificationRead(
        id=notification.id,
        notification_type=notification.notification_type,
        post_id=notification.post_id,
        source_post_id=notification.source_post_id,
        actor_character_id=notification.actor_character_id,
        actor_name=notification.actor_name,
        actor_handle=notification.actor_handle,
        actor_avatar_url=notification.actor_avatar_url,
        post_title=notification.post_title,
        post_body=notification.post_body,
        source_post_title=notification.source_post_title,
        source_post_body=notification.source_post_body,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def _bot_notification_page(
    page: NotificationPage,
) -> schemas.BotNotificationPage:
    return schemas.BotNotificationPage(
        items=[_bot_notification_read(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def _bot_profile_ref(profile: ProfileRef) -> schemas.BotProfileRef:
    return schemas.BotProfileRef.model_validate(profile.model_dump())


def _bot_follow_read(follow: FollowRead) -> schemas.BotFollowRead:
    return schemas.BotFollowRead(
        follower=_bot_profile_ref(follow.follower),
        target=_bot_profile_ref(follow.target),
        created_at=follow.created_at,
    )


def _bot_profile_read(profile: ProfileRead) -> schemas.BotProfileRead:
    return schemas.BotProfileRead(
        profile=_bot_profile_ref(profile.profile),
        execution_mode=profile.execution_mode,
        post_count=profile.post_count,
        reply_count=profile.reply_count,
        liked_post_count=profile.liked_post_count,
        received_like_count=profile.received_like_count,
        follower_count=profile.follower_count,
        character_follower_count=profile.character_follower_count,
        following_count=profile.following_count,
        one_liner=profile.one_liner,
    )
