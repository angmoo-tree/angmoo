"""Read posts and threads only after canonical visibility checks."""
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.repository import posts as post_repository
from app.domains.social.exceptions import PostNotFoundError
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.service.presentation import _post_detail, _hidden_post_detail, _post_summary


def get_post(db: Session, post_id: str) -> schemas.PostDetail:
    post = post_repository.get_post_including_report_hidden(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    if not _is_post_public_context_visible(db, post):
        return _hidden_post_detail(db, post)
    return _post_detail(db, post)


def get_post_thread(db: Session, post_id: str) -> schemas.PostThreadRead:
    post = post_repository.get_post_including_report_hidden(db, post_id)
    if post is None:
        raise PostNotFoundError(post_id)
    if not _is_post_public_context_visible(db, post):
        return schemas.PostThreadRead(post=_hidden_post_detail(db, post), replies=[])
    replies = post_repository.list_post_thread_replies(db, post_id)
    return schemas.PostThreadRead(
        post=_post_detail(db, post),
        replies=[
            _post_summary(db, reply)
            for reply in replies
            if _is_post_public_context_visible(db, reply)
        ],
    )
