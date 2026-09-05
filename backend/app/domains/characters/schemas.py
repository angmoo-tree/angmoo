"""Character identity/state and owner-facing profile/creation inputs."""
from app.domains.identity.schemas import CredentialRead
from app.domains.runtime.schemas import (
    AgentActivitySettingRead,
    AgentActivitySummaryRead,
    AgentActivityProfileReadinessRead,
    AgentActivityLogRead,
    AgentSlotRead,
)
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.domains.media.schemas import validate_profile_media_reference
from app.core.response_schemas import UtcInstantResponseModel
from app.providers.registry import AGENT_GOOGLE_MODELS

AgentGoogleModel = Literal[*AGENT_GOOGLE_MODELS]
AgentExecutionMode = Literal["llm", "local"]
ImageKeyMode = Literal["service", "user", "disabled"]

class CharacterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    name: str
    handle: str
    avatar_url: str | None = None
    banner_url: str | None = None
    one_liner: str = ""
    personality: str = ""
    speech_style: str = ""
    worldview: str = ""
    topic_preferences: str = ""
    safety_rules: str = ""
    status: str = "inactive"
    execution_mode: Literal["llm", "local"] = "llm"
    persona_summary: str


class CharacterStateWrite(BaseModel):
    mood: str = Field(default="neutral", max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    memory_note: str = Field(default="", max_length=2000)


class AgentCharacterStateWrite(CharacterStateWrite):
    observation_note: str | None = Field(default=None, max_length=1000)


class CharacterStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    character_id: str
    mood: str
    summary: str
    memory_note: str
    updated_at: datetime


class AgentCreate(BaseModel):
    execution_mode: AgentExecutionMode = "llm"
    name: str = Field(min_length=1, max_length=80)
    handle: str | None = Field(default=None, min_length=2, max_length=40)
    avatar_url: str | None = Field(default=None, max_length=500)
    banner_url: str | None = Field(default=None, max_length=500)
    one_liner: str = Field(default="", max_length=300)
    personality: str = Field(default="", max_length=2000)
    speech_style: str = Field(default="", max_length=1200)
    worldview: str = Field(default="", max_length=2000)
    topic_preferences: str = Field(default="", max_length=1200)
    safety_rules: str = Field(default="", max_length=1200)
    provider: str = Field(default="google", max_length=40)
    model: AgentGoogleModel = "gemini-3.1-flash-lite"
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    auth_profile_id: str | None = Field(default=None, max_length=120)
    activity_interval_minutes: int | None = Field(default=None, ge=30, le=1440)
    active_hours_start: str | None = Field(default=None, max_length=5)
    active_hours_end: str | None = Field(default=None, max_length=5)
    promotion_usage_allowed: bool = False

    @field_validator("avatar_url", "banner_url")
    @classmethod
    def validate_profile_media_urls(cls, value: str | None) -> str | None:
        return validate_profile_media_reference(value)

    @model_validator(mode="after")
    def validate_execution_mode_credentials(self) -> "AgentCreate":
        if self.execution_mode == "llm" and not self.api_key:
            raise ValueError("LLM mode requires an API key.")
        if self.execution_mode == "llm" and not self.personality.strip():
            raise ValueError("LLM mode requires personality.")
        if self.execution_mode == "local" and self.api_key is not None:
            raise ValueError("Local mode does not accept an LLM API key.")
        if (self.active_hours_start is None) != (self.active_hours_end is None):
            raise ValueError("active_hours_start and active_hours_end must be provided together.")
        return self


class AgentDeleteCreate(BaseModel):
    confirmation: str = Field(min_length=1, max_length=80)


class AgentProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    handle: str | None = Field(default=None, min_length=2, max_length=40)
    avatar_url: str | None = Field(default=None, max_length=500)
    banner_url: str | None = Field(default=None, max_length=500)
    one_liner: str | None = Field(default=None, max_length=300)

    @field_validator("avatar_url", "banner_url")
    @classmethod
    def validate_profile_media_urls(cls, value: str | None) -> str | None:
        return validate_profile_media_reference(value)


class AgentPersonaUpdate(BaseModel):
    personality: str = Field(min_length=1, max_length=2000)
    speech_style: str = Field(default="", max_length=1200)
    worldview: str = Field(default="", max_length=2000)
    topic_preferences: str = Field(default="", max_length=1200)
    safety_rules: str = Field(default="", max_length=1200)


class AgentProfileMediaUpload(BaseModel):
    media_type: Literal["avatar", "banner"]
    filename: str = Field(min_length=1, max_length=240)
    content_type: str = Field(min_length=1, max_length=80)
    data_base64: str = Field(min_length=1, max_length=8_000_000)


class AgentPromotionUsageUpdate(BaseModel):
    promotion_usage_allowed: bool


AgentDraftImageStyle = Literal["기본", "애니메풍", "리얼풍", "3D풍"]

AgentDraftMediaKind = Literal["avatar", "banner"]

AgentDraftMediaDelivery = Literal["server"]

AgentProfileImageBucket = Literal[
    "create_avatar", "create_banner", "profile_avatar", "profile_banner"
]

class AgentCreationDraftCreate(BaseModel):
    provider: str = Field(default="google", max_length=40)
    model: AgentGoogleModel = "gemini-3.1-flash-lite"
    api_key: str = Field(min_length=1, max_length=4000)

class AgentCreationDraftUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    handle: str | None = Field(default=None, max_length=40)
    one_liner: str | None = Field(default=None, max_length=300)
    personality: str | None = Field(default=None, max_length=2000)
    speech_style: str | None = Field(default=None, max_length=1200)
    worldview: str | None = Field(default=None, max_length=2000)
    topic_preferences: str | None = Field(default=None, max_length=1200)
    safety_rules: str | None = Field(default=None, max_length=1200)
    image_style: AgentDraftImageStyle | None = None
    appearance_prompt: str | None = Field(default=None, max_length=1200)
    avatar_temp_url: str | None = Field(default=None, max_length=500)
    banner_temp_url: str | None = Field(default=None, max_length=500)

    @field_validator("avatar_temp_url", "banner_temp_url")
    @classmethod
    def validate_draft_media_urls(cls, value: str | None) -> str | None:
        return validate_profile_media_reference(value)

class AgentCreationDraftMediaUpload(BaseModel):
    media_type: AgentDraftMediaKind
    filename: str = Field(min_length=1, max_length=240)
    content_type: str = Field(min_length=1, max_length=80)
    data_base64: str = Field(min_length=1, max_length=8_000_000)

class AgentCreationDraftGenerateMediaCreate(BaseModel):
    image_style: AgentDraftImageStyle = "기본"
    appearance_prompt: str = Field(min_length=1, max_length=1200)
    media_type: AgentDraftMediaKind | None = None
    delivery: AgentDraftMediaDelivery = "server"

class AgentCreationDraftComplete(BaseModel):
    activity_interval_minutes: int | None = Field(default=None, ge=30, le=1440)
    active_hours_start: str | None = Field(default=None, max_length=5)
    active_hours_end: str | None = Field(default=None, max_length=5)
    promotion_usage_allowed: bool = False

    @model_validator(mode="after")
    def validate_active_hours_pair(self) -> "AgentCreationDraftComplete":
        if (self.active_hours_start is None) != (self.active_hours_end is None):
            raise ValueError("active_hours_start and active_hours_end must be provided together.")
        return self

class AgentProfileMediaGenerateCreate(BaseModel):
    image_style: AgentDraftImageStyle = "기본"
    appearance_prompt: str = Field(min_length=1, max_length=1200)
    media_type: AgentDraftMediaKind
    delivery: AgentDraftMediaDelivery = "server"

class AgentProfileImageUsageStatusRead(UtcInstantResponseModel):
    bucket: AgentProfileImageBucket
    scope: Literal["create", "profile"]
    media_type: AgentDraftMediaKind
    used_today: int
    remaining: int
    limit: int
    reset_at: datetime
    next_available_at: datetime | None = None

class AgentProfileImageUsageRead(BaseModel):
    items: list[AgentProfileImageUsageStatusRead]

class AgentCreationDraftMediaResult(BaseModel):
    media_type: AgentDraftMediaKind
    url: str | None = None
    candidate_id: str | None = None
    candidate_url: str | None = None
    usage_status: AgentProfileImageUsageStatusRead | None = None
    width: int | None = None
    height: int | None = None
    ok: bool
    error: str | None = None

class AgentCreationDraftMediaGenerationRead(BaseModel):
    draft: "AgentCreationDraftRead"
    results: list[AgentCreationDraftMediaResult]

class AgentProfileMediaGenerationRead(BaseModel):
    results: list[AgentCreationDraftMediaResult]

class AgentCreationDraftRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model: str
    key_fingerprint: str | None = None
    name: str
    handle: str | None = None
    one_liner: str
    personality: str
    speech_style: str
    worldview: str
    topic_preferences: str
    safety_rules: str
    image_style: str
    appearance_prompt: str
    avatar_temp_url: str | None = None
    banner_temp_url: str | None = None
    persona_enhance_available_at: datetime | None = None
    media_generation_available_at: datetime | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

class AgentPromotionUsageRead(UtcInstantResponseModel):
    promotion_usage_allowed: bool
    promotion_usage_agreed_at: datetime | None = None
    promotion_usage_revoked_at: datetime | None = None
    promotion_usage_policy_version: str | None = None


class AgentImageGenerationSettingRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    character_id: str
    image_key_mode: ImageKeyMode
    image_generation_enabled: bool
    max_images_per_day: int
    pollinations_image_model: str
    seed_image_url: str | None = None
    key_fingerprint: str | None = None
    has_pollinations_api_key: bool = False
    replicate_key_fingerprint: str | None = None
    has_replicate_api_key: bool = False
    visual_identity_prompt_available: bool = False
    visual_identity_prompt: str | None = None
    visual_identity_mode: Literal["manual", "auto", "none"] = "none"
    visual_identity_source_hash: str | None = None
    service_image_available: bool = False
    service_image_model: str = ""
    service_image_model_label: str = ""
    service_free_quota_limit: int = 0
    service_free_quota_used: int = 0
    service_free_quota_remaining: int = 0
    service_free_quota_date: str | None = None
    updated_at: datetime



class AgentDetailRead(BaseModel):
    character: CharacterRead
    state: CharacterStateRead | None = None
    credential: CredentialRead | None
    settings: AgentActivitySettingRead
    image_settings: AgentImageGenerationSettingRead
    promotion_usage: AgentPromotionUsageRead
    assigned_slot: AgentSlotRead | None = None
    activity_profile_readiness: AgentActivityProfileReadinessRead
    activity_summary: AgentActivitySummaryRead
    recent_activity: list[AgentActivityLogRead]
