"""Same-Session references used by the routines-owned planning transaction.

Reference records remain attached to the caller's Session. Planning reads their
existing attributes; the sole cross-owner mutation is delegated to WorldCharacter.
Implementations do not create Sessions, explicitly flush, commit, or choose plan
policy. Existing query-triggered autoflush remains part of the caller's Session.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class PlanOwner(Protocol):
    id: str


@dataclass(frozen=True)
class PlanScope:
    world: Any
    membership: Any
    world_character: Any
    character: Any


class PlanReferences(Protocol):
    def get_character(self, character_id: str) -> Any: ...
    def character_contract_hash(self, character: Any) -> str: ...
    def find_world_character(
        self, *, character_id: str, world_id: str, lock_for_update: bool = False
    ) -> Any: ...
    def get_membership(self, membership_id: str) -> Any: ...
    def get_world(self, world_id: str) -> Any: ...
    def get_ready_repertoire(self, world_character_id: str) -> Any: ...
    def get_profile(self, profile_id: str) -> Any: ...
    def list_enabled_candidates(self, repertoire_id: str) -> list[Any]: ...
    def get_credential(self, credential_id: str) -> Any: ...
    def set_activity_runtime_mode(
        self, world_character: Any, *, activity_runtime_mode: str
    ) -> None: ...


PlanReferencesFactory = Callable[[Any], PlanReferences]
