"""Character seed inputs and caller-composed management workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, TYPE_CHECKING
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


__all__ = [
    "AutonomousCharacterSeedData",
    "CharacterOwner",
    "CharacterManagementWorkflows",
    "CreatorWorkflows",
    "CharacterMediaWorkflows",
    "CharacterImageGenerationWorkflows",
]


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


class DraftLlmCall(Protocol):
    def __call__(
        self, *, db: Session, user: CharacterOwner, draft_id: str, provider: str,
        model: str, api_key: str, message: str, extra_system_prompt: str,
    ) -> Awaitable[str]: ...


class DraftMediaPromotion(Protocol):
    def __call__(
        self, *, character_id: str, media_type: str, draft_media_url: str,
    ) -> str: ...


@dataclass(frozen=True)
class CreatorWorkflows:
    """External work used by the draft lifecycle in its caller-owned Session."""

    run_llm: DraftLlmCall
    decrypt_api_key: Callable[[models.AgentCreationDraft], str]
    delete_candidate_media: Callable[[str, str], None]
    delete_draft_media: Callable[[str], None]
    promote_media: DraftMediaPromotion
    create_character: Callable[
        [Session, CharacterOwner, schemas.AgentCreate], schemas.AgentDetailRead
    ]
    read_character: Callable[[Session, CharacterOwner, str], schemas.AgentDetailRead]


class MediaActivityLog(Protocol):
    def __call__(
        self, db: Session, *, user_id: str, character_id: str, action_type: str,
        target_post_id: str | None, reason: str, result: str,
    ) -> object: ...


@dataclass(frozen=True)
class CharacterMediaWorkflows:
    """Activity/image-setting collaboration in the caller's existing Session."""

    invalidate_visual_identity: Callable[[Session, str], None]
    log_activity: MediaActivityLog
    build_detail: Callable[[Session, models.Character], schemas.AgentDetailRead]


@dataclass(frozen=True)
class CharacterImageGenerationWorkflows:
    """External settings/key/translation used at the original admission points."""

    get_model: Callable[[Session], str]
    get_route_mode: Callable[[Session], str]
    image_key_available: Callable[[str], bool]
    resolve_api_key: Callable[[str], str | None]
    translate_prompt: Callable[[str], str]
