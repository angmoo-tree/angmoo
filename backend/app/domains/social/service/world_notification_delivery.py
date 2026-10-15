"""Exact World delivery identities in the source owner's existing transaction."""
import hashlib
import json
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from app.domains.social.models.posts import Notification


def deliver_world_notification(db, *, world_id, recipient_world_character_id, recipient_character_id,
        actor_world_character_id, actor_character_id, notification_type, source_kind, source_id,
        post_id=None, source_post_id=None, social_event_id=None, data=None):
    if actor_world_character_id == recipient_world_character_id or actor_character_id == recipient_character_id:
        return None
    if not all((world_id, recipient_world_character_id, recipient_character_id, actor_world_character_id, actor_character_id, source_kind, source_id)):
        raise ValueError("notification_delivery_scope_missing")
    key = hashlib.sha256(json.dumps([1, world_id, recipient_world_character_id, notification_type, source_kind, str(source_id)],
        ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    values = dict(delivery_key=key, world_id=world_id, recipient_world_character_id=recipient_world_character_id,
        recipient_character_id=recipient_character_id, actor_world_character_id=actor_world_character_id,
        actor_character_id=actor_character_id, notification_type=notification_type, post_id=post_id,
        source_post_id=source_post_id, source_social_event_id=social_event_id, data=data)
    # SQLite is canonical. Conflict handling must not roll back the source UoW.
    db.execute(insert(Notification).values(**values).on_conflict_do_nothing(index_elements=["delivery_key"]))
    row = db.scalar(select(Notification).where(Notification.delivery_key == key))
    for field in ("world_id", "recipient_world_character_id", "recipient_character_id", "actor_world_character_id",
                  "actor_character_id", "notification_type", "post_id", "source_post_id"):
        if getattr(row, field) != values[field]:
            raise ValueError("notification_delivery_conflict")
    if social_event_id is not None:
        if row.source_social_event_id not in (None, social_event_id):
            raise ValueError("notification_delivery_event_conflict")
        row.source_social_event_id = social_event_id
    if data is not None:
        row.data = data
    db.flush()
    return row


def bind_post_notifications(db, *, world_id, actor_id, source_post_id, event_id):
    db.execute(update(Notification).where(Notification.world_id == world_id,
        Notification.actor_world_character_id == actor_id, Notification.source_post_id == source_post_id,
        Notification.delivery_key.is_not(None), Notification.source_social_event_id.is_(None))
        .values(source_social_event_id=event_id).execution_options(synchronize_session="fetch"))
