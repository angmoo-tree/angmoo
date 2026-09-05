"""Other-owner operations used inside the current Social transaction."""
from datetime import datetime
from typing import Literal, Protocol
from sqlalchemy.orm import Session


class SocialWriteWorkflows(Protocol):
    def log_activity(self, db: Session, *, user_id: str, character_id: str, action_type: str, target_post_id: str | None, reason: str, result: str) -> object: ...

    def consume_quota(self, db: Session, *, user_id: str, action: str) -> None: ...

    def exclude_events_for_posts(self, db: Session, *, post_ids: list[str], reason: Literal["source_deleted", "source_hidden"], invalidated_at: datetime) -> int: ...
