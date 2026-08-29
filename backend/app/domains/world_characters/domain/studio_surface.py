from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ActivitySetupState = Literal[
    "not_started",
    "generated",
    "approved",
    "unavailable_for_owner_controlled",
]


@dataclass(frozen=True, slots=True)
class StudioWorldCharacter:
    world_character_id: str
    character_id: str
    display_name: str
    confirmation_name: str
    avatar_url: str | None
    intro: str
    role_key: str | None
    control_mode: Literal["autonomous", "owner_controlled"]
    status: str
    autonomous_enabled: bool
    selected_active_world: bool
    version: int
    activity_setup_state: ActivitySetupState


__all__ = ["ActivitySetupState", "StudioWorldCharacter"]
