"""Social-owned SQL; original caller transaction/flush/finish_write behavior is preserved."""

from datetime import date, datetime, timezone
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, aliased, selectinload
from app.domains.social.models import posts as models
from app.core import unit_of_work
from app.domains.social.utils.cursors import _parse_int_cursor




def list_notifications_for_agent(
    db: Session, *, user_id: str, character_id: str, limit: int
) -> list[models.Notification]:
    return list(
        db.scalars(
            select(models.Notification)
            .where(
                or_(
                    models.Notification.recipient_user_id == user_id,
                    models.Notification.recipient_character_id == character_id,
                )
            )
            .order_by(
                models.Notification.created_at.desc(),
                models.Notification.id.desc(),
            )
            .limit(limit)
        )
    )

def list_notifications_for_agent_page(
    db: Session,
    *,
    user_id: str,
    character_id: str,
    limit: int,
    cursor: str | None = None,
) -> tuple[list[models.Notification], str | None]:
    query = (
        select(models.Notification)
        .where(
            or_(
                models.Notification.recipient_user_id == user_id,
                models.Notification.recipient_character_id == character_id,
            )
        )
        .order_by(models.Notification.id.desc())
    )
    if cursor:
        cursor_id = _parse_int_cursor(cursor)
        if cursor_id is not None:
            query = query.where(models.Notification.id < cursor_id)
    rows = list(db.scalars(query.limit(limit + 1)))
    return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None

def list_unread_reply_notifications_for_character(
    db: Session, *, character_id: str, limit: int
) -> list[models.Notification]:
    return list_unread_notifications_for_character(
        db,
        character_id=character_id,
        notification_type="reply",
        limit=limit,
    )

def list_unread_notifications_for_character(
    db: Session, *, character_id: str, notification_type: str, limit: int
) -> list[models.Notification]:
    return list(
        db.scalars(
            select(models.Notification)
            .where(
                models.Notification.recipient_character_id == character_id,
                models.Notification.notification_type == notification_type,
                models.Notification.read_at.is_(None),
            )
            .order_by(
                models.Notification.created_at.desc(),
                models.Notification.id.desc(),
            )
            .limit(limit)
        )
    )

def get_notification_for_agent(
    db: Session, *, user_id: str, character_id: str, notification_id: int
) -> models.Notification | None:
    return db.scalar(
        select(models.Notification).where(
            models.Notification.id == notification_id,
            or_(
                models.Notification.recipient_user_id == user_id,
                models.Notification.recipient_character_id == character_id,
            ),
        )
    )

def mark_notification_read(
    db: Session, notification: models.Notification
) -> models.Notification:
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(notification)
    return notification
