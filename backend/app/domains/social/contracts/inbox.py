"""Canonical owner-reply inbox candidate contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ManualInboxInteractionCandidate:
    source_event_id: str
    world_id: str
    consumer_world_character_id: str
    actor_world_character_id: str
    excerpt: str
    occurred_at: datetime
    directness: int
    episode_relevance: int
    relationship_band: str


__all__ = ["ManualInboxInteractionCandidate"]


class ManualInboxRuntimeError(Exception):
    pass


class InboxWorldCharacter(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def membership_id(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def control_mode(self) -> str: ...
    @property
    def activity_runtime_mode(self) -> str: ...


class InboxMembership(Protocol):
    @property
    def world_id(self) -> str: ...
    @property
    def status(self) -> str: ...


class ManualInboxReferences(Protocol):
    def get_world_character(
        self, db: Session, world_character_id: str
    ) -> InboxWorldCharacter | None: ...
    def get_membership(
        self, db: Session, membership_id: str
    ) -> InboxMembership | None: ...
