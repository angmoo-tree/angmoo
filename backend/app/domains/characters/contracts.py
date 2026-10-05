"""Character seed inputs and caller-composed management workflows."""

from __future__ import annotations

from app.domains.characters.policies.persona import PERSONA_LIMITS, PERSONA_SUMMARY_LIMIT, normalize_persona_text
from dataclasses import dataclass
from datetime import date, tzinfo
from typing import Awaitable, Callable, Protocol, TYPE_CHECKING
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field, field_validator
from urllib.parse import urlsplit
import re

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
    character_background: str = ""
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
    "CharacterImageSettingsWorkflows",
    "ImportProfile",
    "ImportSettings",
    "ImportConfiguration",
    "safe_configuration_media",
    "import_digest",
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
        model: str, api_key: str, message: str, extra_system_prompt: str, thinking_level: str = "high",
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
    resolve_target: Callable[[Session, CharacterOwner, str | None], str] | None = None
    register_draft: Callable[..., schemas.AgentDetailRead] | None = None
    validate_copy_target: Callable[[Session, str, str], None] | None = None


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
    translate_prompt: Callable[[Session, CharacterOwner, str], str]


class ServiceImageQuotaRead(Protocol):
    def __call__(self, db: Session, *, user_id: str, quota_date: date) -> int: ...


@dataclass(frozen=True)
class CharacterImageSettingsWorkflows:
    """Shared key availability and Social quota reads in the caller Session."""

    service_image_available: Callable[[], bool]
    service_image_available_for_model: Callable[[str], bool]
    count_service_image_quota_used: ServiceImageQuotaRead
    app_timezone: tzinfo


def safe_configuration_media(value: str | None) -> str | None:
    """Public reference only; query credentials and executable URLs never persist."""
    if value is None:
        return None
    if not isinstance(value, str) or any(ord(char) < 32 for char in value) or "\\" in value:
        raise ValueError("configuration_media_invalid")
    parts = urlsplit(value)
    if parts.username or parts.password or parts.query or parts.fragment or ".." in parts.path.split("/"):
        raise ValueError("configuration_media_invalid")
    relative = not parts.scheme and not parts.netloc and (parts.path.startswith("/media/") or
        re.fullmatch(r"/api/v1/media/assets/[A-Za-z0-9-]+/content", parts.path))
    if not relative and not (parts.scheme == "https" and parts.hostname):
        raise ValueError("configuration_media_invalid")
    return value


class ImportProfile(BaseModel):
    """Immutable, secret-free profile stored at a permanent import origin."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    display_name: str = Field(min_length=1, max_length=80)
    handle: str = Field(min_length=1, max_length=80)
    avatar_url: str | None = None
    banner_url: str | None = None
    intro: str = ""

    @field_validator("avatar_url", "banner_url")
    @classmethod
    def _media(cls, value):
        return safe_configuration_media(value)


class ImportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personality: str = ""
    speech_style: str = ""
    worldview: str = ""
    character_background: str = ""
    topic_preferences: str = ""
    safety_rules: str = ""
    active_hours_start: str = "09:00"
    active_hours_end: str = "02:00"
    activity_interval_minutes: int = Field(default=60, ge=1, le=1440)
    max_posts_per_day: int = Field(default=30, ge=0, le=1000)
    max_comments_per_day: int = Field(default=30, ge=0, le=1000)
    allow_post: bool = True
    allow_reply: bool = True
    allow_like: bool = True
    allow_repost: bool = True
    allow_follow: bool = True
    allow_unfollow: bool = True
    generation_model: str | None = None
    image_model: str | None = None
    image_style: str = ""
    appearance_prompt: str = ""


class ImportConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: ImportProfile
    settings: ImportSettings


def import_digest(payload: dict) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
