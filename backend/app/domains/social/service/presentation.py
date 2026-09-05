"""Public Social response assembly with owned identity/profile lookups."""
from sqlalchemy.orm import Session
from app.domains.social.models import posts as models
from app.domains.social.schemas import community as schemas
from app.domains.social.repository import posts as post_repository, media as media_repository
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.constants import DELETED_CHARACTER_NAME, REPORT_HIDDEN_TITLE, REPORT_HIDDEN_MESSAGE, MENTION_HANDLE_RE
from app.domains.characters.service import profile as character_profiles
from app.domains.identity.service import profile as identity_profiles


def _notification_read(
    db: Session, notification: models.Notification
) -> schemas.NotificationRead:
    actor = _notification_actor_identity(db, notification)
    recipient = _notification_recipient_identity(db, notification)
    post_preview = _notification_post_preview(db, notification.post_id)
    source_post_preview = _notification_post_preview(db, notification.source_post_id)
    return schemas.NotificationRead.model_validate(
        {
            "id": notification.id,
            "notification_type": notification.notification_type,
            "post_id": notification.post_id,
            "source_post_id": notification.source_post_id,
            "actor_user_id": notification.actor_user_id,
            "actor_character_id": notification.actor_character_id,
            "recipient_user_id": notification.recipient_user_id,
            "recipient_character_id": notification.recipient_character_id,
            "data": notification.data,
            "actor_name": actor["name"],
            "actor_handle": actor["handle"],
            "actor_avatar_url": actor["avatar_url"],
            "recipient_name": recipient["name"],
            "recipient_handle": recipient["handle"],
            "recipient_avatar_url": recipient["avatar_url"],
            "post_title": post_preview["title"],
            "post_body": post_preview["body"],
            "source_post_title": source_post_preview["title"],
            "source_post_body": source_post_preview["body"],
            "read_at": notification.read_at,
            "created_at": notification.created_at,
        }
    )


def _notification_actor_identity(
    db: Session, notification: models.Notification
) -> dict[str, str | None]:
    if notification.actor_character_id:
        character = character_profiles.get_character(db, notification.actor_character_id)
        if character is not None:
            if character.deleted_at is not None:
                return {
                    "name": DELETED_CHARACTER_NAME,
                    "handle": None,
                    "avatar_url": None,
                }
            return {
                "name": character.name,
                "handle": character.handle,
                "avatar_url": character.avatar_url,
            }
    if notification.actor_user_id:
        user = identity_profiles.get_user(db, notification.actor_user_id)
        if user is not None:
            return {"name": user.display_name, "handle": None, "avatar_url": None}
    return {"name": None, "handle": None, "avatar_url": None}


def _notification_recipient_identity(
    db: Session, notification: models.Notification
) -> dict[str, str | None]:
    if notification.recipient_character_id:
        character = character_profiles.get_character(db, notification.recipient_character_id)
        if character is not None:
            if character.deleted_at is not None:
                return {
                    "name": DELETED_CHARACTER_NAME,
                    "handle": None,
                    "avatar_url": None,
                }
            return {
                "name": character.name,
                "handle": character.handle,
                "avatar_url": character.avatar_url,
            }
    if notification.recipient_user_id:
        user = identity_profiles.get_user(db, notification.recipient_user_id)
        if user is not None:
            return {"name": user.display_name, "handle": None, "avatar_url": None}
    return {"name": None, "handle": None, "avatar_url": None}


def _notification_post_preview(
    db: Session, post_id: str | None
) -> dict[str, str | None]:
    if post_id is None:
        return {"title": None, "body": None}
    post = post_repository.get_post_including_report_hidden(db, post_id)
    if post is None:
        return {"title": None, "body": None}
    if not _is_post_public_context_visible(db, post):
        return {"title": REPORT_HIDDEN_TITLE, "body": REPORT_HIDDEN_MESSAGE}
    return {"title": post.title, "body": post.body}


def _post_summary(db: Session, post: models.Post) -> schemas.PostSummary:
    comment_count = post_repository.count_post_comments(db, post.id)
    author = _post_author_identity(db, post)
    media = _post_media_reads(db, post)
    return schemas.PostSummary.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": post.title,
            "body": post.body,
            "info_kind": post.info_kind,
            "source_name": post.source_name,
            "source_url": post.source_url,
            "observed_at": post.observed_at,
            "location_label": post.location_label,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": _mentioned_characters_for_texts(
                db, post.title, post.body
            ),
            "reply_to_post_id": post.reply_to_post_id,
            "quote_post_id": post.quote_post_id,
            "repost_of_post_id": post.repost_of_post_id,
            "comment_count": comment_count,
            "like_count": post_repository.count_post_likes(db, post.id),
            "reply_count": post_repository.count_post_replies(db, post.id),
            "repost_count": post_repository.count_post_reposts(db, post.id),
            "quote_count": post_repository.count_post_quotes(db, post.id),
            "quoted_post": _post_reference(db, post.quote_post_id),
            "reposted_post": _post_reference(db, post.repost_of_post_id),
            "report_hidden": post_repository.is_report_hidden(post),
            "media": media,
        }
    )


def _post_detail(db: Session, post) -> schemas.PostDetail:
    author = _post_author_identity(db, post)
    media = _post_media_reads(db, post)
    return schemas.PostDetail.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": post.title,
            "body": post.body,
            "info_kind": post.info_kind,
            "source_name": post.source_name,
            "source_url": post.source_url,
            "observed_at": post.observed_at,
            "location_label": post.location_label,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": _mentioned_characters_for_texts(
                db, post.title, post.body
            ),
            "reply_to_post_id": post.reply_to_post_id,
            "quote_post_id": post.quote_post_id,
            "repost_of_post_id": post.repost_of_post_id,
            "comments": [],
            "like_count": post_repository.count_post_likes(db, post.id),
            "reply_count": post_repository.count_post_replies(db, post.id),
            "repost_count": post_repository.count_post_reposts(db, post.id),
            "quote_count": post_repository.count_post_quotes(db, post.id),
            "quoted_post": _post_reference(db, post.quote_post_id),
            "reposted_post": _post_reference(db, post.repost_of_post_id),
            "report_hidden": post_repository.is_report_hidden(post),
            "media": media,
        }
    )


def _hidden_post_detail(db: Session, post: models.Post) -> schemas.PostDetail:
    author = _post_author_identity(db, post)
    return schemas.PostDetail.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": REPORT_HIDDEN_TITLE,
            "body": REPORT_HIDDEN_MESSAGE,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": [],
            "reply_to_post_id": post.reply_to_post_id,
            "quote_post_id": None,
            "repost_of_post_id": None,
            "comments": [],
            "like_count": 0,
            "reply_count": 0,
            "repost_count": 0,
            "quote_count": 0,
            "quoted_post": None,
            "reposted_post": None,
            "report_hidden": True,
        }
    )


def _post_reference(db: Session, post_id: str | None) -> schemas.PostReference | None:
    if post_id is None:
        return None
    post = post_repository.get_post(db, post_id)
    if post is None or not _is_post_public_context_visible(db, post):
        return None
    author = _post_author_identity(db, post)
    return schemas.PostReference.model_validate(
        {
            "id": post.id,
            "author_name": author["name"],
            "author_handle": author["handle"],
            "author_avatar_url": author["avatar_url"],
            "title": post.title,
            "body": post.body,
            "info_kind": post.info_kind,
            "source_name": post.source_name,
            "source_url": post.source_url,
            "observed_at": post.observed_at,
            "location_label": post.location_label,
            "created_at": post.created_at,
            "post_type": post.post_type,
            "author_user_id": post.author_user_id,
            "author_character_id": post.author_character_id,
            "world_id": getattr(post, "world_id", None),
            "author_world_character_id": getattr(
                post, "author_world_character_id", None
            ),
            "mentioned_characters": _mentioned_characters_for_texts(
                db, post.title, post.body
            ),
            "media": _post_media_reads(db, post),
        }
    )


def _post_media_reads(db: Session, post: models.Post) -> list[schemas.PostMediaRead]:
    if post_repository.is_report_hidden(post):
        return []
    return [
        schemas.PostMediaRead.model_validate(media)
        for media in media_repository.list_post_media(db, post.id)
    ]


def _post_author_identity(db: Session, post: models.Post) -> dict[str, str | None]:
    if post.author_character_id:
        character = character_profiles.get_character(db, post.author_character_id)
        if character is not None:
            if character.deleted_at is not None:
                return {
                    "name": DELETED_CHARACTER_NAME,
                    "handle": None,
                    "avatar_url": None,
                }
            return {
                "name": character.name,
                "handle": character.handle,
                "avatar_url": character.avatar_url,
            }
    return {"name": post.author_name, "handle": None, "avatar_url": None}


def _mentioned_characters_for_texts(
    db: Session, *texts: str | None
) -> list[schemas.MentionedCharacterRef]:
    handles: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in MENTION_HANDLE_RE.finditer(text):
            handle = match.group(1)
            if handle in seen:
                continue
            seen.add(handle)
            handles.append(handle)
    if not handles:
        return []

    characters = character_profiles.list_mentionable_characters(db, handles)
    by_handle = {character.handle: character for character in characters}
    return [
        schemas.MentionedCharacterRef(
            handle=handle,
            character_id=character.id,
            name=character.name,
        )
        for handle in handles
        if (character := by_handle.get(handle)) is not None
    ]
