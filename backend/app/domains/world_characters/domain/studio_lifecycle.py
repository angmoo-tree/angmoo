from __future__ import annotations

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


class StudioWorldCharacterLifecycleError(Exception):
    reason_code = "studio_world_character_lifecycle_error"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code is not None:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


class StudioWorldCharacterNotFoundError(StudioWorldCharacterLifecycleError):
    reason_code = "world_character_not_found"


class StudioWorldCharacterForbiddenError(StudioWorldCharacterLifecycleError):
    reason_code = "character_not_owned"


class StudioWorldCharacterConflictError(StudioWorldCharacterLifecycleError):
    reason_code = "stale_world_character_version"


class StudioWorldCharacterValidationError(StudioWorldCharacterLifecycleError):
    reason_code = "world_character_ineligible"


class StudioWorldCharacterBusyError(StudioWorldCharacterConflictError):
    reason_code = "world_character_run_in_progress"


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
