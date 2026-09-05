from __future__ import annotations

from app.domains.world_characters.contracts.studio_lifecycle import (
    StudioCharacterCandidate,
    WorldCharacterLeaveResult,
)
from app.domains.world_characters.ports.studio_lifecycle import (
    StudioWorldCharacterLifecycleRepository,
)


def list_studio_character_candidates(
    repository: StudioWorldCharacterLifecycleRepository,
    *,
    world_id: str,
    current_user_id: str,
) -> tuple[StudioCharacterCandidate, ...]:
    return repository.list_candidates(
        world_id=world_id,
        current_user_id=current_user_id,
    )


def leave_studio_world_character(
    repository: StudioWorldCharacterLifecycleRepository,
    *,
    world_id: str,
    character_id: str,
    current_user_id: str,
    world_character_id: str,
    expected_version: int,
    confirmation_name: str,
    idempotency_key: str,
) -> WorldCharacterLeaveResult:
    return repository.leave(
        world_id=world_id,
        character_id=character_id,
        current_user_id=current_user_id,
        world_character_id=world_character_id,
        expected_version=expected_version,
        confirmation_name=confirmation_name,
        idempotency_key=idempotency_key,
    )


__all__ = [
    "leave_studio_world_character",
    "list_studio_character_candidates",
]
