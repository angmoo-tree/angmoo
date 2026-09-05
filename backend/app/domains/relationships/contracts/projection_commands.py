"""Database-neutral commands accepted by a relationship projection adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, TypeAlias


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
    actor_world_character_id: str
    actor_character_id: str
    target_world_character_id: str
    target_character_id: str
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


class ProjectionOutboxPayload(Protocol):
    @property
    def payload(self) -> object: ...
    @property
    def payload_version(self) -> str: ...
    @property
    def projection_type(self) -> str: ...
    @property
    def source_signature(self) -> str: ...
    @property
    def world_id(self) -> str: ...
    @property
    def source_event_id(self) -> str: ...


class ProjectionWorldCharacter(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def character_id(self) -> str: ...


class ProjectionPost(Protocol):
    @property
    def world_id(self) -> str | None: ...
    @property
    def deleted_at(self) -> datetime | None: ...
    @property
    def report_hidden_at(self) -> datetime | None: ...
    @property
    def visibility(self) -> str: ...


class ProjectionCommandReferences(Protocol):
    """Nullable current sources and historical membership in the caller Session."""
    def world_character(self, *, world_id: str, world_character_id: str) -> ProjectionWorldCharacter: ...
    def get_post(self, post_id: str) -> ProjectionPost | None: ...
