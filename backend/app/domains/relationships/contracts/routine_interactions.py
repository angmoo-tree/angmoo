"""Readonly source facts consumed at the original canonical event lookup positions."""

from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session
from app.domains.relationships.contracts.events import EventPost
from app.domains.social.contracts.inbox import (
    ManualInboxReferences,
    ManualInboxInteractionCandidate,
)


class InteractionPost(EventPost, Protocol):
    @property
    def id(self) -> str: ...
    @property
    def body(self) -> str: ...
    @property
    def author_world_character_id(self) -> str | None: ...
    @property
    def reply_to_post_id(self) -> str | None: ...
    @property
    def activity_episode_id(self) -> str | None: ...


class RoutineInteractionReferences(ManualInboxReferences, Protocol):
    def get_post(self, db: Session, post_id: str) -> InteractionPost | None: ...
    def pair_blocked(
        self, db: Session, *, world_id: str, first_id: str, second_id: str
    ) -> bool: ...
    def manual_inbox_candidates(
        self,
        db: Session,
        *,
        world_id: str,
        consumer_world_character_id: str,
        episode_id: str,
        after: datetime,
        before: datetime,
    ) -> list[ManualInboxInteractionCandidate]: ...
