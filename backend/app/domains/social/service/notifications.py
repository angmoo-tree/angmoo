"""Notification admission and persistence in the caller's current write context."""
from sqlalchemy.orm import Session
from app.core import unit_of_work
from app.domains.social.models import posts as models


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
