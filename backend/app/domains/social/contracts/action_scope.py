"""Lazy same-Session scope reads and execution-owner writes for Social actions."""

from typing import Protocol
from app.domains.social.contracts.source_writes import SourceWorldCharacter
from app.domains.social.contracts.subjective_persistence import SubjectiveExecution


class ActionIdentity(Protocol):
    @property
    def id(self) -> str: ...


class WorldFeedActionProfile(Protocol):
    @property
    def world(self) -> ActionIdentity: ...
    @property
    def character(self) -> ActionIdentity: ...
    @property
    def world_character(self) -> ActionIdentity: ...


class ActionResponseDecision(Protocol):
    @property
    def decision(self) -> str: ...


class PublicActionProposalResponse(Protocol):
    @property
    def response(self) -> ActionResponseDecision: ...


class ActionScopeReferences(Protocol):
    def active_world_character(self, *, character_id: str) -> SourceWorldCharacter: ...
    def get_world_character(
        self, world_character_id: str
    ) -> SourceWorldCharacter | None: ...
    def world_character_for_character(
        self, *, world_id: str, character_id: str
    ) -> SourceWorldCharacter: ...
    def set_execution_scope(
        self,
        execution: SubjectiveExecution,
        *,
        world_id: str,
        actor_world_character_id: str,
    ) -> None: ...
