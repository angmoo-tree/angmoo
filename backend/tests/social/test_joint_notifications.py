from app import models as _registered_models  # Register the current complete ORM metadata before partial DDL.

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.domains.social.models.posts import Notification
from app.domains.social.service.notifications import ensure_joint_started_notification


def test_joint_notification_keeps_exact_dedupe_payload_and_caller_write_boundary():
    engine = create_engine("sqlite://")
    Notification.__table__.create(engine)
    with Session(engine, autoflush=False) as db:
        changes = []
        event.listen(db, "before_flush", lambda *args: changes.append("flush"))
        event.listen(db, "before_commit", lambda *args: changes.append("commit"))
        values = dict(joint_activity_id="joint-1", world_id="world-1", recipient_world_character_id="wc-recipient", actor_world_character_id="wc-actor", recipient_character_id="character-recipient", actor_character_id="character-actor", source_social_event_id="event-1", post_id="opening-1")
        ensure_joint_started_notification(db, **values)
        assert changes == []
        assert len(db.new) == 1
        notification = next(iter(db.new))
        assert notification.notification_type == "joint_activity_started"
        assert notification.world_id == "world-1"
        assert notification.recipient_world_character_id == "wc-recipient"
        assert notification.actor_world_character_id == "wc-actor"
        assert notification.recipient_character_id == "character-recipient"
        assert notification.actor_character_id == "character-actor"
        assert notification.source_social_event_id == "event-1"
        assert notification.source_joint_activity_id == "joint-1"
        assert notification.post_id == notification.source_post_id == "opening-1"
        assert notification.data == '{"joint_activity_id":"joint-1","opening_post_id":"opening-1"}'
        db.flush()
        assert changes == ["flush"]
        ensure_joint_started_notification(db, **{**values, "source_social_event_id": "later-event"})
        assert changes == ["flush"]
        assert not db.new
        assert db.scalars(select(Notification)).all() == [notification]
        assert notification.source_social_event_id == "event-1"
        ensure_joint_started_notification(db, **{**values, "recipient_world_character_id": "another-recipient"})
        assert len(db.new) == 1
        assert changes == ["flush"]
        db.rollback()
        assert db.scalars(select(Notification)).all() == []
    engine.dispose()
