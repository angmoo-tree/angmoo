"""Canonical post ancestry visibility; search output never grants access."""
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.repository import posts as post_repository


def is_post_public_context_visible(db: Session, post: models.Post) -> bool:
    return _is_post_public_context_visible(db, post)


def _is_post_public_context_visible(db: Session, post: models.Post) -> bool:
    if post.deleted_at is not None or post_repository.is_report_hidden(post):
        return False
    if (
        post.quote_post_id is not None
        and post_repository.get_post(db, post.quote_post_id) is None
    ):
        return False
    if (
        post.repost_of_post_id is not None
        and post_repository.get_post(db, post.repost_of_post_id) is None
    ):
        return False
    seen = {post.id}
    current = post
    while current.reply_to_post_id is not None:
        parent = post_repository.get_post(db, current.reply_to_post_id)
        if parent is None or parent.id in seen:
            return False
        seen.add(parent.id)
        current = parent
    return True
