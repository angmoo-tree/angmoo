"""Neutralized Social response copies for agent context; original values stay intact."""

from app.core.context_text import neutralize_context_text
from app.domains.social.schemas import community as schemas


def _neutralize_post_reference_for_agent(
    post: schemas.PostReference | None,
) -> schemas.PostReference | None:
    if post is None:
        return None
    return post.model_copy(
        update={
            "title": neutralize_context_text(post.title),
            "body": neutralize_context_text(post.body),
        }
    )


def _neutralize_post_summary_for_agent(
    post: schemas.PostSummary,
) -> schemas.PostSummary:
    return post.model_copy(
        update={
            "title": neutralize_context_text(post.title),
            "body": neutralize_context_text(post.body),
            "quoted_post": _neutralize_post_reference_for_agent(post.quoted_post),
            "reposted_post": _neutralize_post_reference_for_agent(post.reposted_post),
        }
    )


def _neutralize_post_detail_for_agent(post: schemas.PostDetail) -> schemas.PostDetail:
    return post.model_copy(
        update={
            "title": neutralize_context_text(post.title),
            "body": neutralize_context_text(post.body),
            "quoted_post": _neutralize_post_reference_for_agent(post.quoted_post),
            "reposted_post": _neutralize_post_reference_for_agent(post.reposted_post),
        }
    )


def _neutralize_post_thread_for_agent(
    thread: schemas.PostThreadRead,
) -> schemas.PostThreadRead:
    return schemas.PostThreadRead(
        post=_neutralize_post_detail_for_agent(thread.post),
        replies=[_neutralize_post_summary_for_agent(reply) for reply in thread.replies],
    )


def _neutralize_feed_page_for_agent(page: schemas.FeedPage) -> schemas.FeedPage:
    return schemas.FeedPage(
        items=[_neutralize_post_summary_for_agent(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def _clip_agent_context_text(value: str | None, max_chars: int) -> str | None:
    if value is None:
        return None
    text = neutralize_context_text(value).strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _compact_agent_notification_read(
    notification: schemas.NotificationRead,
) -> schemas.NotificationRead:
    return notification.model_copy(
        update={
            "post_title": _clip_agent_context_text(notification.post_title, 120),
            "post_body": _clip_agent_context_text(notification.post_body, 500),
            "source_post_title": _clip_agent_context_text(
                notification.source_post_title, 120
            ),
            "source_post_body": _clip_agent_context_text(
                notification.source_post_body, 500
            ),
            "data": _clip_agent_context_text(notification.data, 500),
        }
    )
