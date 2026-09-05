from __future__ import annotations

from app.domains.world_characters.exceptions import (
    StudioWorldCharacterLifecycleError,
    StudioWorldCharacterNotFoundError,
    StudioWorldCharacterForbiddenError,
    StudioWorldCharacterConflictError,
    StudioWorldCharacterValidationError,
    StudioWorldCharacterBusyError,
)
from dataclasses import dataclass
from typing import Literal


CandidateReason = Literal[
    "already_linked",
    "character_moderation_inactive",
    "local_execution_mode_unsupported",
    "world_character_ineligible",
    "world_character_left_restore_unsupported",
]


@dataclass(frozen=True, slots=True)
class StudioCharacterCandidate:
    character_id: str
    display_name: str
    handle: str | None
    avatar_url: str | None
    current_world_status: str | None
    eligible: bool
    reason_code: CandidateReason | None


@dataclass(frozen=True, slots=True)
class WorldCharacterLeaveResult:
    world_character_id: str
    world_id: str
    character_id: str
    status: Literal["left"]
    autonomous_enabled: Literal[False]
    version: int
    scheduler_assignment_released: bool
    history_preserved: Literal[True]
    replayed: bool


__all__ = [
    "CandidateReason",
    "StudioCharacterCandidate",
    "StudioWorldCharacterBusyError",
    "StudioWorldCharacterConflictError",
    "StudioWorldCharacterForbiddenError",
    "StudioWorldCharacterLifecycleError",
    "StudioWorldCharacterNotFoundError",
    "StudioWorldCharacterValidationError",
    "WorldCharacterLeaveResult",
]
