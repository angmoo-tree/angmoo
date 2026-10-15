"""Notification admission and persistence in the caller's current write context."""
from collections.abc import Iterable
from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.domains.social.models import posts as models
from app.domains.social.service.presentation import _mentioned_characters_for_texts


def create_notification(
    db: Session,
    *,
    notification_type: str,
    recipient_user_id: str | None = None,
    recipient_character_id: str | None = None,
    actor_user_id: str | None = None,
    actor_character_id: str | None = None,
    post_id: str | None = None,
    source_post_id: str | None = None,
    data: str | None = None,
) -> models.Notification | None:
    if recipient_user_id is None and recipient_character_id is None:
        return None
    if actor_user_id and actor_user_id == recipient_user_id and recipient_character_id is None:
        return None
    if (
        actor_character_id
        and actor_character_id == recipient_character_id
        and recipient_user_id is None
    ):
        return None
    notification = models.Notification(
        notification_type=notification_type,
        recipient_user_id=recipient_user_id,
        recipient_character_id=recipient_character_id,
        actor_user_id=actor_user_id,
        actor_character_id=actor_character_id,
        post_id=post_id,
        source_post_id=source_post_id,
        data=data,
    )
    db.add(notification)
    unit_of_work.finish_write(db, notification)
    return notification


def ensure_joint_started_notification(
    db: Session,
    *,
    joint_activity_id: str,
    world_id: str,
    recipient_world_character_id: str,
    actor_world_character_id: str,
    recipient_character_id: str,
    actor_character_id: str,
    source_social_event_id: str,
    post_id: str,
) -> None:
    existing_notification = db.scalar(
        select(models.Notification).where(
            models.Notification.notification_type == "joint_activity_started",
            models.Notification.source_joint_activity_id == joint_activity_id,
            models.Notification.recipient_world_character_id == recipient_world_character_id,
        )
    )
    if existing_notification is None:
        db.add(
            models.Notification(
                recipient_character_id=recipient_character_id,
                actor_character_id=actor_character_id,
                world_id=world_id,
                recipient_world_character_id=recipient_world_character_id,
                actor_world_character_id=actor_world_character_id,
                source_social_event_id=source_social_event_id,
                source_joint_activity_id=joint_activity_id,
                notification_type="joint_activity_started",
                post_id=post_id,
                source_post_id=post_id,
                data=json.dumps(
                    {"joint_activity_id": joint_activity_id, "opening_post_id": post_id},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )


def _notify_post_owner(
    db: Session,
    *,
    notification_type: str,
    post: models.Post,
    source_post_id: str | None,
    actor_user_id: str | None,
    actor_character_id: str | None,
) -> models.Notification | None:
    if post.world_id is not None:
        # Reply/quote sources have immutable Post identities. Reactions,
        # including reposts, are delivered by the canonical successful event.
        if source_post_id is None or notification_type == "repost":
            return None
        source = db.get(models.Post, source_post_id)
        if source is None or source.world_id != post.world_id or source.author_character_id != actor_character_id:
            raise ValueError("notification_source_scope_invalid")
        from app.domains.social.service.world_notification_delivery import deliver_world_notification
        return deliver_world_notification(db, world_id=post.world_id,
            recipient_world_character_id=post.author_world_character_id, recipient_character_id=post.author_character_id,
            actor_world_character_id=source.author_world_character_id, actor_character_id=actor_character_id,
            notification_type=notification_type, source_kind="post", source_id=source.id,
            post_id=post.id, source_post_id=source.id)
    create_notification(
        db,
        notification_type=notification_type,
        recipient_user_id=post.author_user_id if post.author_character_id is None else None,
        recipient_character_id=post.author_character_id,
        actor_user_id=actor_user_id,
        actor_character_id=actor_character_id,
        post_id=post.id,
        source_post_id=source_post_id,
    )


def _notify_mentioned_characters(
    db: Session,
    *,
    post: models.Post,
    actor_user_id: str | None,
    actor_character_id: str | None,
    skip_character_ids: Iterable[str | None] = (),
    world_recipients=(),
) -> None:
    skipped = {character_id for character_id in skip_character_ids if character_id}
    if actor_character_id:
        skipped.add(actor_character_id)
    if post.world_id is not None:
        from app.domains.social.service.world_notification_delivery import deliver_world_notification
        for recipient in world_recipients:
            if recipient.character_id in skipped:
                continue
            deliver_world_notification(db, world_id=post.world_id,
                recipient_world_character_id=recipient.world_character_id, recipient_character_id=recipient.character_id,
                actor_world_character_id=post.author_world_character_id, actor_character_id=actor_character_id,
                notification_type="mention", source_kind="post", source_id=post.id,
                post_id=post.id, source_post_id=post.id)
        return
    for mention in _mentioned_characters_for_texts(db, post.title, post.body):
        if mention.character_id in skipped:
            continue
        create_notification(
            db,
            notification_type="mention",
            recipient_character_id=mention.character_id,
            actor_user_id=actor_user_id,
            actor_character_id=actor_character_id,
            post_id=post.id,
            source_post_id=None,
        )


def mark_notification_read(
    db: Session, notification: models.Notification
) -> models.Notification:
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(notification)
    return notification
