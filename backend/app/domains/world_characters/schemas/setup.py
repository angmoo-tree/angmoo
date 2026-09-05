from __future__ import annotations

from datetime import datetime
from typing import Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.worlds.schemas import (
    WorldDaypartProfileInput,
    WorldGenerationContextRead,
    WorldPlaceInput,
)


WorldSetupStage = Literal["community_profile", "repertoire", "approval"]
WorldSetupState = Literal[
    "ready",
    "needs_profile",
    "needs_repertoire",
    "stale",
    "failed",
    "running",
]
WorldActivityDaypart = Literal["dawn", "morning", "afternoon", "evening"]
WorldActivitySocialMode = Literal[
    "solo", "open_to_interaction", "cooperative"
]
WorldActivityKind = Literal[
    "duty",
    "rest",
    "self_care",
    "hobby",
    "exploration",
    "social",
    "maintenance",
    "challenge",
]

WORLD_COMMUNITY_ACTION_KEYS = frozenset(
    {"comment", "reply", "like", "repost", "follow", "unfollow", "observe"}
)


def normalize_bounded_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def _normalize_unique_items(
    value: list[str],
    *,
    min_items: int,
    max_items: int,
    max_length: int,
    casefold: bool = False,
) -> list[str]:
    if not min_items <= len(value) <= max_items:
        raise ValueError(f"expected {min_items}..{max_items} entries")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        clean = normalize_bounded_text(item)
        if not clean or len(clean) > max_length:
            raise ValueError(f"entries must be 1..{max_length} characters")
        canonical = clean.casefold()
        if canonical in seen:
            raise ValueError("entries must be unique after normalization")
        seen.add(canonical)
        normalized.append(canonical if casefold else clean)
    return normalized


class WorldCharacterSetupSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class WorldCommunityActionPreference(WorldCharacterSetupSchema):
    weight: int = Field(ge=0, le=100)
    note: str = Field(default="", max_length=160)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str) -> str:
        return normalize_bounded_text(value)


class WorldCommunityActionProfile(WorldCharacterSetupSchema):
    """The seven product-defined social actions for one WorldCharacter."""

    comment: WorldCommunityActionPreference
    reply: WorldCommunityActionPreference
    like: WorldCommunityActionPreference
    repost: WorldCommunityActionPreference
    follow: WorldCommunityActionPreference
    unfollow: WorldCommunityActionPreference
    observe: WorldCommunityActionPreference


class WorldCommunityProfilePayload(WorldCharacterSetupSchema):
    visible_summary: str = Field(min_length=1, max_length=280)
    core_interests: list[str] = Field(min_length=3, max_length=5)
    adjacent_interests: list[str] = Field(min_length=2, max_length=4)
    avoid_topics: list[str] = Field(default_factory=list, max_length=8)
    discovery_openness: int = Field(ge=0, le=100)
    search_keywords: list[str] = Field(min_length=8, max_length=8)
    action_profile: WorldCommunityActionProfile

    @field_validator("visible_summary")
    @classmethod
    def _summary(cls, value: str) -> str:
        return normalize_bounded_text(value)

    @field_validator("core_interests")
    @classmethod
    def _core_interests(cls, value: list[str]) -> list[str]:
        return _normalize_unique_items(
            value, min_items=3, max_items=5, max_length=40
        )

    @field_validator("adjacent_interests")
    @classmethod
    def _adjacent_interests(cls, value: list[str]) -> list[str]:
        return _normalize_unique_items(
            value, min_items=2, max_items=4, max_length=40
        )

    @field_validator("avoid_topics")
    @classmethod
    def _avoid_topics(cls, value: list[str]) -> list[str]:
        return _normalize_unique_items(
            value, min_items=0, max_items=8, max_length=40
        )

    @field_validator("search_keywords")
    @classmethod
    def _search_keywords(cls, value: list[str]) -> list[str]:
        return _normalize_unique_items(
            value,
            min_items=8,
            max_items=8,
            max_length=40,
            casefold=True,
        )


class WorldActivityCandidatePayload(WorldCharacterSetupSchema):
    daypart: WorldActivityDaypart
    activity_kind: WorldActivityKind
    title: str = Field(min_length=1, max_length=120)
    activity_seed: str = Field(min_length=1, max_length=500)
    place_key: str | None = Field(default=None, min_length=1, max_length=64)
    social_mode: WorldActivitySocialMode

    @field_validator("title", "activity_seed")
    @classmethod
    def _required_text(cls, value: str) -> str:
        return normalize_bounded_text(value)

    @field_validator("place_key")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return normalize_bounded_text(value) if value is not None else None


class WorldActivityRepertoirePayload(WorldCharacterSetupSchema):
    candidates: list[WorldActivityCandidatePayload] = Field(
        min_length=40, max_length=40
    )


class WorldCharacterSetupGenerateCreate(WorldCharacterSetupSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)
    consent_policy_version: str = Field(min_length=1, max_length=40)
    consented: Literal[True]


class WorldCharacterSetupRetryCreate(WorldCharacterSetupGenerateCreate):
    stage: Literal["community_profile", "repertoire"]


class WorldCharacterSetupApproveCreate(WorldCharacterSetupSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)
    profile_id: str = Field(min_length=1, max_length=64)
    repertoire_id: str = Field(min_length=1, max_length=64)


class WorldCharacterSetupRejectCreate(WorldCharacterSetupSchema):
    idempotency_key: str = Field(min_length=8, max_length=128)
    reason: str = Field(default="", max_length=280)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return normalize_bounded_text(value)


class WorldCharacterEntryCreate(WorldCharacterSetupSchema):
    character_id: str = Field(min_length=1, max_length=64)
    role_key: str | None = Field(default=None, min_length=1, max_length=64)
    local_background: str = Field(default="", max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("character_id", "role_key", "local_background", "idempotency_key")
    @classmethod
    def _entry_text(cls, value: str | None) -> str | None:
        return normalize_bounded_text(value) if value is not None else None


class WorldCharacterEntryRead(WorldCharacterSetupSchema):
    id: str
    world_id: str
    character_id: str
    membership_id: str
    role_key: str | None = None
    status: str
    autonomous_enabled: bool
    version: int
    reused: bool = False


class WorldCharacterRoleUpdate(WorldCharacterSetupSchema):
    role_key: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1)

    @field_validator("role_key")
    @classmethod
    def _role_key(cls, value: str) -> str:
        return normalize_bounded_text(value)


class WorldCharacterLeaveCreate(WorldCharacterSetupSchema):
    world_character_id: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1)
    confirmation_name: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator(
        "world_character_id",
        "confirmation_name",
        "idempotency_key",
    )
    @classmethod
    def _leave_text(cls, value: str) -> str:
        return normalize_bounded_text(value)


class WorldCharacterLeaveRead(WorldCharacterSetupSchema):
    world_character_id: str
    world_id: str
    character_id: str
    status: Literal["left"]
    autonomous_enabled: Literal[False]
    version: int
    scheduler_assignment_released: bool
    history_preserved: Literal[True]
    replayed: bool = False


class WorldCommunityProfileRead(WorldCommunityProfilePayload):
    id: str
    world_character_id: str
    status: str
    schema_version: int
    generator_version: str
    character_contract_hash: str
    world_contract_hash: str
    provider: str
    model: str
    generated_at: datetime
    approved_at: datetime | None = None


class WorldActivityCandidateRead(WorldActivityCandidatePayload):
    id: str
    repertoire_id: str
    ordinal: int
    canonical_signature: str
    enabled: bool


class WorldActivityRepertoireRead(WorldCharacterSetupSchema):
    id: str
    world_character_id: str
    status: str
    schema_version: int
    generator_version: str
    character_contract_hash: str
    world_contract_hash: str
    community_profile_id: str
    provider: str
    model: str
    validation_summary: dict[str, object]
    generated_at: datetime
    approved_at: datetime | None = None
    candidates: list[WorldActivityCandidateRead]


class WorldCharacterSetupPreflightRead(WorldCharacterSetupSchema):
    world_character_id: str
    world_id: str
    character_id: str
    provider: str | None = None
    model: str | None = None
    credential_ready: bool
    logical_call_count: int = 2
    physical_request_count: int = 3
    profile_max_output_tokens: int
    repertoire_max_output_tokens: int
    regeneration_limit_character_24h: int = 2
    regeneration_limit_owner_24h: int = 5
    reused: bool = False
    safe_reason_code: str | None = None


class WorldCharacterSetupRead(WorldCharacterSetupSchema):
    world_character_id: str
    world_id: str
    character_id: str
    state: WorldSetupState
    autonomy_ready: bool
    autonomous_enabled: bool
    reused: bool = False
    can_retry_stage: WorldSetupStage | None = None
    can_approve: bool = False
    can_regenerate: bool = False
    safe_reason_code: str | None = None
    current_character_contract_hash: str
    current_world_contract_hash: str
    generated_character_contract_hash: str | None = None
    generated_world_contract_hash: str | None = None
    profile: WorldCommunityProfileRead | None = None
    repertoire: WorldActivityRepertoireRead | None = None
