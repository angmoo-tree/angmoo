"""Create canonical source rows with the caller's existing write boundary."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.contracts.actors import SocialUser, SocialCharacter
from app.core.search_text import build_post_search_document
from app.domains.social.utils.text import sanitize_visible_post_title, sanitize_visible_post_body


def create_post(
    db: Session,
    *,
    post_id: str,
    user: SocialUser,
    character: SocialCharacter | None,
    data: schemas.PostCreate,
    post_info: schemas.PostInfoMetadata | None = None,
    world_id: str | None = None,
    author_world_character_id: str | None = None,
) -> models.Post:
    title = sanitize_visible_post_title(data.title)
    body = sanitize_visible_post_body(data.body)
    post = models.Post(
        id=post_id,
        author_user_id=user.id,
        author_character_id=character.id if character else None,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
        author_name=character.name if character else user.display_name,
        title=title,
        body=body,
        search_document=build_post_search_document(
            title=title, body=body, topic_signature=None
        ),
        info_kind=post_info.info_kind if post_info else None,
        source_name=post_info.source_name if post_info else None,
        source_url=post_info.source_url if post_info else None,
        observed_at=post_info.observed_at if post_info else None,
        location_label=post_info.location_label if post_info else None,
    )
    db.add(post)
    unit_of_work.finish_write(db, post)
    return post


def create_timeline_post(
    db: Session,
    *,
    post_id: str,
    user: SocialUser,
    character: SocialCharacter | None,
    title: str,
    body: str,
    post_type: str,
    reply_to_post_id: str | None = None,
    quote_post_id: str | None = None,
    repost_of_post_id: str | None = None,
    world_id: str | None = None,
    author_world_character_id: str | None = None,
) -> models.Post:
    safe_title = sanitize_visible_post_title(title)
    safe_body = sanitize_visible_post_body(body)
    post = models.Post(
        id=post_id,
        author_user_id=user.id,
        author_character_id=character.id if character else None,
        author_name=character.name if character else user.display_name,
        world_id=world_id,
        author_world_character_id=author_world_character_id,
        title=safe_title,
        body=safe_body,
        search_document=build_post_search_document(
            title=safe_title, body=safe_body, topic_signature=None
        ),
        post_type=post_type,
        reply_to_post_id=reply_to_post_id,
        quote_post_id=quote_post_id,
        repost_of_post_id=repost_of_post_id,
    )
    db.add(post)
    unit_of_work.finish_write(db, post)
    return post


def create_comment(
    db: Session, post: models.Post, character: SocialCharacter, data: schemas.CommentCreate
) -> models.Comment:
    comment = models.Comment(
        post_id=post.id,
        author_character_id=character.id,
        content=data.content,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment
