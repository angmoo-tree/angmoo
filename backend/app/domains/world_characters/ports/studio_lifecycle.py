from __future__ import annotations

from typing import Protocol

from app.domains.world_characters.domain.studio_lifecycle import (
    StudioCharacterCandidate,
    WorldCharacterLeaveResult,
)


class WorldCharacterLeaveRuntimeGuard(Protocol):
    def require_idle(
        self,
        *,
        owner_user_id: str,
        character_id: str,
        world_character_id: str,
        selected_active_world: bool,
    ) -> None: ...


class StudioWorldCharacterLifecycleRepository(Protocol):
    def list_candidates(
        self,
        *,
        world_id: str,
        current_user_id: str,
    ) -> tuple[StudioCharacterCandidate, ...]: ...

    def leave(
        self,
        *,
        world_id: str,
        character_id: str,
        current_user_id: str,
        world_character_id: str,
        expected_version: int,
        confirmation_name: str,
        idempotency_key: str,
    ) -> WorldCharacterLeaveResult: ...


__all__ = [
    "StudioWorldCharacterLifecycleRepository",
    "WorldCharacterLeaveRuntimeGuard",
]
