"""Bounded query facts used by the Today policy without foreign ORM imports."""

from datetime import datetime
from typing import Protocol
from app.domains.social.contracts.source_writes import (
    SourceWorldCharacter,
    SourceMembership,
)
from app.domains.social.contracts.subjective_persistence import (
    SubjectiveWorld,
    SubjectiveEvent,
    SubjectiveExecution,
    SubjectiveEvidence,
)


class TodayEvent(SubjectiveEvent, Protocol):
    @property
    def target_world_character_id(self) -> str | None: ...
    @property
    def event_type(self) -> str: ...
    @property
    def retrieval_status(self) -> str: ...
    @property
    def occurred_at(self) -> datetime: ...


class TodayEvidence(SubjectiveEvidence, Protocol):
    @property
    def id(self) -> str: ...
    @property
    def social_event_id(self) -> str: ...
    @property
    def public_action_execution_id(self) -> int | None: ...


class TodayReferences(Protocol):
    def scope(
        self, world_id: str, subject_id: str
    ) -> tuple[
        SubjectiveWorld | None, SourceWorldCharacter | None, SourceMembership | None
    ]: ...
    def _active_world_character_ids(self, world_id: str) -> set[str]: ...
    def events(
        self,
        world_id: str,
        subject_world_character_id: str,
        start: datetime,
        end: datetime,
    ) -> tuple[list[TodayEvent], bool]: ...
    def evidence(self, event_ids: list[str]) -> list[TodayEvidence]: ...
    def executions(self, execution_ids: list[int]) -> list[SubjectiveExecution]: ...
    def represented_post_ids(self, world_id: str, post_ids: list[str]) -> list[str]: ...
