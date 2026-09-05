"""Character seed inputs and caller-composed management workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, TYPE_CHECKING
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.domains.characters import models, schemas


class CharacterOwner(Protocol):
    """The owner identifier required by Character creation in the caller session."""

    id: str


@dataclass(frozen=True, slots=True)
class AutonomousCharacterSeedData:
    owner_id: str
    display_name: str
    handle_hint: str
    one_liner: str
    personality: str
    speech_style: str
    worldview: str
    topic_preferences: tuple[str, ...]
    safety_rules: tuple[str, ...]
    persona_summary: str
    planned_handle: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None


__all__ = ["AutonomousCharacterSeedData", "CharacterOwner", "CharacterManagementWorkflows"]


@dataclass(frozen=True)
class CharacterManagementWorkflows:
    """Runtime work composed after/before Character writes in the caller Session.

    Callbacks preserve the existing activity/credential commits. They must not
    create a replacement Session or detach the supplied Character/owner.
    """

    validate_initial_activity: Callable[[schemas.AgentCreate], None]
    after_create: Callable[
        [Session, CharacterOwner, models.Character, schemas.AgentCreate],
        schemas.AgentDetailRead,
    ]
    build_detail: Callable[[Session, models.Character], schemas.AgentDetailRead]
    build_full_detail: Callable[[Session, models.Character], schemas.AgentDetailRead]
    after_profile: Callable[
        [Session, CharacterOwner, models.Character, bool], schemas.AgentDetailRead
    ]
    after_persona: Callable[
        [Session, CharacterOwner, models.Character], schemas.AgentDetailRead
    ]
