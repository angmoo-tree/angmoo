"""Inbox pages, missing-notification decisions and read-state workflows."""
from sqlalchemy.orm import Session
from app.domains.social.contracts.actors import SocialUser
from app.domains.social.contracts.inbox_reads import UserInboxReads
from app.domains.social.schemas import community as schemas
from app.domains.social.exceptions import NotificationNotFoundError
from app.domains.social.repository import inbox as inbox_repository
from app.domains.social.service import notifications as notification_writes
from app.domains.social.service.presentation import _notification_read


class SocialInboxService:
    def __init__(self, reads: UserInboxReads):
        self.reads = reads

    def list_notifications(
        self, db: Session, user: SocialUser, *, limit: int = 50, cursor: str | None = None
    ) -> schemas.NotificationPage:
        notifications, next_cursor = self.reads.list_notifications(
            db, user=user, limit=max(1, min(limit, 100)), cursor=cursor
        )
        return schemas.NotificationPage(
            items=[_notification_read(db, item) for item in notifications],
            next_cursor=next_cursor,
        )


    def mark_notification_read(
        self, db: Session, user: SocialUser, notification_id: int
    ) -> schemas.NotificationRead:
        notification = self.reads.get_notification_for_user(
            db, user=user, notification_id=notification_id
        )
        if notification is None:
            raise NotificationNotFoundError(notification_id)
        return _notification_read(db, notification_writes.mark_notification_read(db, notification))


def list_notifications_for_character(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    limit: int = 50,
    cursor: str | None = None,
) -> schemas.NotificationPage:
    notifications, next_cursor = inbox_repository.list_notifications_for_agent_page(
        db,
        user_id=user_id,
        character_id=character_id,
        limit=max(1, min(limit, 100)),
        cursor=cursor,
    )
    return schemas.NotificationPage(
        items=[_notification_read(db, item) for item in notifications],
        next_cursor=next_cursor,
    )


def mark_character_notification_read(
    db: Session, *, user_id: str, character_id: str, notification_id: int
) -> schemas.NotificationRead:
    notification = inbox_repository.get_notification_for_agent(
        db, user_id=user_id, character_id=character_id, notification_id=notification_id
    )
    if notification is None:
        raise NotificationNotFoundError(notification_id)
    return _notification_read(db, notification_writes.mark_notification_read(db, notification))
