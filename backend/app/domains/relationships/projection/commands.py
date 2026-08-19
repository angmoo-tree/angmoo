"""Database-neutral commands accepted by a relationship projection adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeAlias


class ProjectionCommandError(RuntimeError):
    def __init__(
        self,
        error_class: str,
        *,
        terminal: bool = True,
        cancelled: bool = False,
    ) -> None:
        super().__init__(error_class)
        self.error_class = error_class
        self.terminal = terminal
        self.cancelled = cancelled


@dataclass(frozen=True)
class SocialEventProjectionCommand:
    world_id: str
    event_id: str
    event_type: str
    occurred_at: datetime
    schema_version: str
    actor_world_character_id: str
    actor_character_id: str
    target_world_character_id: str | None
    target_character_id: str | None


@dataclass(frozen=True)
class RelationshipStateProjectionCommand:
    event: SocialEventProjectionCommand
    relationship_state_id: str
    familiarity: int
    affinity: int
    trust: int
    tension: int
    interaction_count: int
    last_event_id: str | None
    last_event_at: datetime | None
    updated_at: datetime
    relationship_version: int


@dataclass(frozen=True)
class SourceExclusionProjectionCommand:
    world_id: str
    event_id: str
    reason: Literal["source_deleted", "source_hidden"]


@dataclass(frozen=True)
class NoGraphMutationCommand:
    world_id: str
    event_id: str
    reason: str


ProjectionCommand: TypeAlias = (
    SocialEventProjectionCommand
    | RelationshipStateProjectionCommand
    | SourceExclusionProjectionCommand
    | NoGraphMutationCommand
)


__all__ = [
    "NoGraphMutationCommand",
    "ProjectionCommand",
    "ProjectionCommandError",
    "RelationshipStateProjectionCommand",
    "SocialEventProjectionCommand",
    "SourceExclusionProjectionCommand",
]
