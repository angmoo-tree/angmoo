"""Join Character ownership and Notification rows without extra queries or writes."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.domains.characters.models import Character
from app.domains.social.models.posts import Notification
from app.domains.social.contracts.actors import SocialUser
from app.domains.social.utils.cursors import _parse_int_cursor
from app.domains.social.service.inbox import SocialInboxService


class SqlAlchemyUserInboxReads:
    def list_notifications(
        self, db: Session, *, user: SocialUser, limit: int, cursor: str | None = None
    ) -> tuple[list[Notification], str | None]:
        owned_character_ids = select(Character.id).where(
            Character.owner_id == user.id,
            Character.deleted_at.is_(None),
        )
        query = (
            select(Notification)
            .where(
                or_(
                    Notification.recipient_user_id == user.id,
                    Notification.recipient_character_id.in_(owned_character_ids),
                )
            )
            .order_by(
                Notification.id.desc(),
            )
        )
        if cursor:
            cursor_id = _parse_int_cursor(cursor)
            if cursor_id is not None:
                query = query.where(Notification.id < cursor_id)
        rows = list(db.scalars(query.limit(limit + 1)))
        return rows[:limit], str(rows[limit - 1].id) if len(rows) > limit else None

    def get_notification_for_user(
        self, db: Session, *, user: SocialUser, notification_id: int
    ) -> Notification | None:
        owned_character_ids = select(Character.id).where(
            Character.owner_id == user.id,
            Character.deleted_at.is_(None),
        )
        return db.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                or_(
                    Notification.recipient_user_id == user.id,
                    Notification.recipient_character_id.in_(owned_character_ids),
                ),
            )
        )


user_inbox_reads = SqlAlchemyUserInboxReads()
inbox_service = SocialInboxService(user_inbox_reads)
