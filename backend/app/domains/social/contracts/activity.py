"""Values and same-Session activity reads used by public profile projection."""
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from app.domains.social.contracts.actors import SocialCharacter


class ActivityCharacter(SocialCharacter, Protocol):
    @property
    def state(self) -> object | None: ...


class PublicActivityLog(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def action_type(self) -> str: ...

    @property
    def target_post_id(self) -> str | None: ...

    @property
    def created_at(self) -> datetime: ...


class ProfileActivityReads(Protocol):
    def recent_activity_logs(self, db: Session, *, character_id: str) -> list[PublicActivityLog]: ...
