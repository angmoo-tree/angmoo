"""Same-Session cross-owner inbox selection; Social retains mutation decisions."""
from typing import Protocol
from sqlalchemy.orm import Session
from app.domains.social.contracts.actors import SocialUser
from app.domains.social.models.posts import Notification


class UserInboxReads(Protocol):
    def list_notifications(self, db: Session, *, user: SocialUser, limit: int, cursor: str | None = None) -> tuple[list[Notification], str | None]: ...

    def get_notification_for_user(self, db: Session, *, user: SocialUser, notification_id: int) -> Notification | None: ...
