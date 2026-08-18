"""HTTP request and response schemas owned by the worlds domain."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


WorldDaypart = Literal["dawn", "morning", "afternoon", "evening"]
WorldVisibility = Literal["private", "unlisted", "public"]
WorldJoinPolicy = Literal["open", "approval_required", "invite_only", "private"]
WorldStatus = Literal["draft", "published", "archived"]
WorldQualityTier = Literal["CORE", "ENRICHED", "DETAILED"]
WorldValidationReason = Literal[
    "world_not_found",
    "world_archived",
    "membership_required",
    "creator_role_required",
    "world_definition_incomplete",
    "invalid_world_name",
    "invalid_tagline",
    "invalid_setting_description",
    "invalid_daily_life_description",
    "invalid_genre_tags",
    "invalid_tone_tags",
    "invalid_timezone",
    "invalid_language",
    "unsafe_banner_reference",
    "world_slug_conflict",
    "world_definition_stale",
    "row_version_conflict",
]

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
_MANAGED_MEDIA_PATTERN = re.compile(r"^/media/worlds/[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+$")


class WorldSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _normalize_key(value: str) -> str:
    normalized = "-".join(_normalize_text(value).lower().split())
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ValueError("key contains unsupported characters")
    return normalized


def _normalize_tags(value: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = " ".join(_normalize_text(item).split()).casefold()
        if not tag or len(tag) > 32:
            raise ValueError("tag entries must be 1..32 characters")
        if tag not in seen:
            seen.add(tag)
            normalized.append(tag)
    if len(normalized) > 5:
        raise ValueError("at most 5 unique tags are allowed")
    return normalized


def _normalize_bounded_items(
    value: list[str], *, max_items: int, max_length: int
) -> list[str]:
    if len(value) > max_items:
        raise ValueError(f"at most {max_items} entries are allowed")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        clean = " ".join(_normalize_text(item).split())
        if not clean or len(clean) > max_length:
            raise ValueError(f"entries must be 1..{max_length} characters")
        folded = clean.casefold()
        if folded not in seen:
            seen.add(folded)
            normalized.append(clean)
    return normalized


class WorldPlaceInput(WorldSchema):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    available_dayparts: list[WorldDaypart] = Field(default_factory=list, max_length=4)
    access_role_keys: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        return _normalize_key(value)

    @field_validator("name", "description")
    @classmethod
    def _text(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("available_dayparts")
    @classmethod
    def _unique_dayparts(cls, value: list[WorldDaypart]) -> list[WorldDaypart]:
        return list(dict.fromkeys(value))

    @field_validator("access_role_keys")
    @classmethod
    def _role_keys(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(_normalize_key(item) for item in value))


class WorldRoleInput(WorldSchema):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    responsibilities: list[str] = Field(default_factory=list, max_length=12)
    allowed_activity_scope: list[str] = Field(default_factory=list, max_length=12)
    autonomous_allowed: bool = True

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        return _normalize_key(value)

    @field_validator("name", "description")
    @classmethod
    def _text(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("responsibilities", "allowed_activity_scope")
    @classmethod
    def _items(cls, value: list[str]) -> list[str]:
        return _normalize_bounded_items(value, max_items=12, max_length=120)


class WorldDaypartProfileInput(WorldSchema):
    daypart: WorldDaypart
    description: str = Field(default="", max_length=500)
    available_features: list[str] = Field(default_factory=list, max_length=12)
    restricted_features: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("available_features", "restricted_features")
    @classmethod
    def _features(cls, value: list[str]) -> list[str]:
        return _normalize_bounded_items(value, max_items=12, max_length=120)


class WorldRuleInput(WorldSchema):
    key: str = Field(min_length=1, max_length=64)
    rule_kind: Literal["allow", "forbid"]
    description: str = Field(min_length=1, max_length=500)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        return _normalize_key(value)

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return _normalize_text(value)


class WorldGlossaryTermInput(WorldSchema):
    key: str = Field(min_length=1, max_length=64)
    term: str = Field(min_length=1, max_length=120)
    meaning: str = Field(min_length=1, max_length=500)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        return _normalize_key(value)

    @field_validator("term", "meaning")
    @classmethod
    def _text(cls, value: str) -> str:
        return _normalize_text(value)


class WorldDefinitionFields(WorldSchema):
    tagline: str = Field(default="", max_length=160)
    setting_description: str = Field(default="", max_length=4000)
    daily_life_description: str = Field(default="", max_length=3000)
    genre_tags: list[str] = Field(default_factory=list, max_length=5)
    tone_tags: list[str] = Field(default_factory=list, max_length=5)
    timezone: str = Field(default="Asia/Seoul", min_length=1, max_length=64)
    language: str = Field(default="ko", min_length=2, max_length=16)
    visibility: WorldVisibility = "private"
    join_policy: WorldJoinPolicy = "approval_required"
    additional_generation_guidance: str = Field(default="", max_length=1000)
    places: list[WorldPlaceInput] = Field(default_factory=list, max_length=40)
    roles: list[WorldRoleInput] = Field(default_factory=list, max_length=30)
    daypart_profiles: list[WorldDaypartProfileInput] = Field(
        default_factory=list, max_length=4
    )
    rules: list[WorldRuleInput] = Field(default_factory=list, max_length=50)
    glossary: list[WorldGlossaryTermInput] = Field(default_factory=list, max_length=100)

    @field_validator(
        "tagline",
        "setting_description",
        "daily_life_description",
        "additional_generation_guidance",
    )
    @classmethod
    def _definition_text(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("genre_tags", "tone_tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        normalized = _normalize_text(value)
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return normalized

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        normalized = _normalize_text(value)
        if not _LANGUAGE_PATTERN.fullmatch(normalized):
            raise ValueError("language must be a BCP 47 language tag")
        return normalized


class WorldDraftCreate(WorldDefinitionFields):
    name: str = Field(min_length=2, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("name", "idempotency_key")
    @classmethod
    def _create_text(cls, value: str) -> str:
        return _normalize_text(value)


class WorldUpdate(WorldSchema):
    row_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    tagline: str | None = Field(default=None, max_length=160)
    setting_description: str | None = Field(default=None, max_length=4000)
    daily_life_description: str | None = Field(default=None, max_length=3000)
    genre_tags: list[str] | None = Field(default=None, max_length=5)
    tone_tags: list[str] | None = Field(default=None, max_length=5)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    visibility: WorldVisibility | None = None
    join_policy: WorldJoinPolicy | None = None
    additional_generation_guidance: str | None = Field(default=None, max_length=1000)
    places: list[WorldPlaceInput] | None = Field(default=None, max_length=40)
    roles: list[WorldRoleInput] | None = Field(default=None, max_length=30)
    daypart_profiles: list[WorldDaypartProfileInput] | None = Field(
        default=None, max_length=4
    )
    rules: list[WorldRuleInput] | None = Field(default=None, max_length=50)
    glossary: list[WorldGlossaryTermInput] | None = Field(default=None, max_length=100)

    @field_validator(
        "name",
        "tagline",
        "setting_description",
        "daily_life_description",
        "additional_generation_guidance",
    )
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_text(value)

    @field_validator("genre_tags", "tone_tags")
    @classmethod
    def _optional_tags(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _normalize_tags(value)

    @field_validator("timezone")
    @classmethod
    def _optional_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return normalized

    @field_validator("language")
    @classmethod
    def _optional_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        if not _LANGUAGE_PATTERN.fullmatch(normalized):
            raise ValueError("language must be a BCP 47 language tag")
        return normalized


class WorldMutationRequest(WorldSchema):
    row_version: int = Field(ge=1)


class WorldBannerUpload(WorldMutationRequest):
    content_type: str = Field(min_length=1, max_length=80)
    data_base64: str = Field(min_length=1, max_length=16_000_000)
    alt_text: str = Field(default="", max_length=160)

    @field_validator("content_type", "alt_text")
    @classmethod
    def _upload_text(cls, value: str) -> str:
        return _normalize_text(value)


class WorldValidationIssue(WorldSchema):
    reason_code: WorldValidationReason
    field: str | None = None
    message: str


class WorldReadinessRead(WorldSchema):
    world_id: str
    definition_version: int
    row_version: int
    contract_version: str
    contract_hash: str
    required_fields: dict[str, bool]
    optional_setting_count: int
    quality_tier: WorldQualityTier
    issues: list[WorldValidationIssue] = Field(default_factory=list)
    ready_for_publish: bool
    evaluated_at: datetime


class WorldPlaceRead(WorldPlaceInput):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    version: int


class WorldRoleRead(WorldRoleInput):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    version: int


class WorldDaypartProfileRead(WorldDaypartProfileInput):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    version: int


class WorldRuleRead(WorldRuleInput):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    version: int


class WorldGlossaryTermRead(WorldGlossaryTermInput):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    version: int


class WorldRead(WorldSchema):
    id: str
    slug: str
    name: str
    tagline: str
    setting_description: str
    daily_life_description: str
    genre_tags: list[str]
    tone_tags: list[str]
    banner_media_id: str | None
    banner_alt_text: str
    timezone: str
    language: str
    visibility: WorldVisibility
    join_policy: WorldJoinPolicy
    status: WorldStatus
    definition_version: int
    row_version: int
    contract_version: str
    contract_hash: str
    readiness_status: str
    additional_generation_guidance: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    places: list[WorldPlaceRead]
    roles: list[WorldRoleRead]
    daypart_profiles: list[WorldDaypartProfileRead]
    rules: list[WorldRuleRead]
    glossary: list[WorldGlossaryTermRead]


class WorldCreatorContextRead(WorldSchema):
    world: WorldRead
    membership_role: Literal["owner", "editor"]
    readiness: WorldReadinessRead


class WorldGenerationContextRead(WorldSchema):
    world_id: str
    name: str
    tagline: str
    setting_description: str
    daily_life_description: str
    genre_tags: list[str]
    tone_tags: list[str]
    timezone: str
    language: str
    definition_version: int
    contract_version: str
    contract_hash: str
    additional_generation_guidance: str
    places: list[WorldPlaceInput]
    roles: list[WorldRoleInput]
    daypart_profiles: list[WorldDaypartProfileInput]
    rules: list[WorldRuleInput]
    glossary: list[WorldGlossaryTermInput]


def validate_managed_world_banner(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_text(value)
    if not _MANAGED_MEDIA_PATTERN.fullmatch(normalized):
        raise ValueError("unsafe_banner_reference")
    return normalized
