from uuid import uuid4

from sqlalchemy.orm import Session

from app import models, schemas
from app.cruds import community as community_crud
from app.cruds import tree as tree_crud


CATEGORIES = {"notice", "bug", "suggestion", "question", "free"}
WRITABLE_CATEGORIES = {"bug", "suggestion", "question", "free"}
DELETED_CHARACTER_NAME = "삭제한 앵무"


class TreeServiceError(Exception):
    pass


class TreePostNotFoundError(TreeServiceError):
    pass


class TreeCategoryError(TreeServiceError):
    pass


class TreeNoticeWriteForbiddenError(TreeServiceError):
    pass


class TreeRelatedCharacterError(TreeServiceError):
    pass


def list_posts(
    db: Session,
    *,
    category: str,
    limit: int = 20,
    cursor: str | None = None,
    query: str | None = None,
) -> schemas.TreeFeedPage:
    safe_category = _safe_category(category)
    posts, next_cursor = tree_crud.list_tree_posts(
        db,
        category=safe_category,
        limit=_safe_limit(limit),
        cursor=cursor,
        query=query,
    )
    return schemas.TreeFeedPage(
        items=[_post_summary(db, post) for post in posts],
        next_cursor=next_cursor,
    )


def get_post(db: Session, post_id: str) -> schemas.TreePostDetail:
    post = tree_crud.get_tree_post(db, post_id)
    if post is None:
        raise TreePostNotFoundError(post_id)
    return _post_detail(db, post)


def create_post(
    db: Session, user: models.User, data: schemas.TreePostCreate
) -> schemas.TreePostDetail:
    if data.category not in WRITABLE_CATEGORIES:
        raise TreeNoticeWriteForbiddenError("공지 작성은 운영자 전용입니다.")
    related_character_id = _validate_related_character(
        db, user=user, character_id=data.related_character_id
    )
    post = tree_crud.create_tree_post(
        db,
        post_id=f"tree-{uuid4().hex[:12]}",
        user=user,
        category=data.category,
        title=data.title,
        body=data.body,
        related_character_id=related_character_id,
    )
    return get_post(db, post.id)


def create_comment(
    db: Session, user: models.User, post_id: str, data: schemas.TreeCommentCreate
) -> schemas.TreePostDetail:
    post = tree_crud.get_tree_post(db, post_id)
    if post is None:
        raise TreePostNotFoundError(post_id)
    tree_crud.create_tree_comment(db, post=post, user=user, content=data.content)
    return get_post(db, post_id)


def _safe_category(category: str) -> str:
    if category not in CATEGORIES:
        raise TreeCategoryError(category)
    return category


def _safe_limit(limit: int) -> int:
    return max(1, min(limit, 100))


def _validate_related_character(
    db: Session, *, user: models.User, character_id: str | None
) -> str | None:
    if character_id is None:
        return None
    character = community_crud.get_character(db, character_id)
    if character is None or character.deleted_at is not None or character.owner_id != user.id:
        raise TreeRelatedCharacterError(character_id)
    return character.id


def _author_read(user: models.User) -> schemas.TreeAuthorRead:
    return schemas.TreeAuthorRead(
        id=user.id,
        display_name=user.display_name,
        handle=None,
        avatar_url=None,
    )


def _related_character_read(
    character: models.Character | None,
) -> schemas.TreeRelatedCharacterRead | None:
    if character is None:
        return None
    if character.deleted_at is not None:
        return schemas.TreeRelatedCharacterRead(
            id=character.id,
            name=DELETED_CHARACTER_NAME,
            handle=None,
            avatar_url=None,
        )
    return schemas.TreeRelatedCharacterRead(
        id=character.id,
        name=character.name,
        handle=character.handle,
        avatar_url=character.avatar_url,
    )


def _comment_read(comment: models.TreeComment) -> schemas.TreeCommentRead:
    return schemas.TreeCommentRead(
        id=comment.id,
        post_id=comment.post_id,
        author=_author_read(comment.author),
        content=comment.content,
        created_at=comment.created_at,
    )


def _post_summary(db: Session, post: models.TreePost) -> schemas.TreePostSummary:
    return schemas.TreePostSummary(
        id=post.id,
        category=post.category,
        title=post.title,
        body=post.body,
        author=_author_read(post.author),
        related_character=_related_character_read(post.related_character),
        comment_count=tree_crud.count_tree_comments(db, post.id),
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def _post_detail(db: Session, post: models.TreePost) -> schemas.TreePostDetail:
    summary = _post_summary(db, post)
    comments = [
        _comment_read(comment)
        for comment in sorted(post.comments, key=lambda item: (item.created_at, item.id))
        if comment.hidden_at is None
    ]
    return schemas.TreePostDetail(**summary.model_dump(), comments=comments)
