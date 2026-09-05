from datetime import datetime
from typing import Literal

from app.domains.characters.schemas import (
    AgentDraftImageStyle,
    AgentDraftMediaKind,
    AgentDraftMediaDelivery,
    AgentProfileImageBucket,
    AgentCreationDraftCreate,
    AgentCreationDraftUpdate,
    AgentCreationDraftMediaUpload,
    AgentCreationDraftGenerateMediaCreate,
    AgentCreationDraftComplete,
    AgentProfileMediaGenerateCreate,
    AgentProfileImageUsageStatusRead,
    AgentProfileImageUsageRead,
    AgentCreationDraftMediaResult,
    AgentCreationDraftMediaGenerationRead,
    AgentProfileMediaGenerationRead,
    AgentCreationDraftRead,
    AgentPromotionUsageRead,
)

from app.domains.world_characters.schemas.readiness import AgentActivityProfileReadinessRead

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.agent_activity_limits import MAX_COMMENTS_PER_DAY, MAX_POSTS_PER_DAY
from app.core.image_generation import IMAGE_MODEL_OPTIONS, MAX_IMAGES_PER_DAY
from app.providers.registry import AGENT_GOOGLE_MODELS
from app.schemas.agent_runs import (
    AgentActivityLogRead,
    AgentSlotRead,
    UtcInstantResponseModel,
)
from app.schemas.characters import CharacterRead, CharacterStateRead
from app.domains.characters.schemas import (
    AgentCreate,
    AgentDeleteCreate,
    AgentProfileUpdate,
    AgentPersonaUpdate,
    AgentProfileMediaUpload,
    AgentPromotionUsageUpdate,
)
from app.schemas.community import PostDetail
from app.schemas.media_security import validate_profile_media_reference


AgentGoogleModel = Literal[*AGENT_GOOGLE_MODELS]
GoogleGeminiModel = AgentGoogleModel
PollinationsImageModel = Literal[
    "klein",
    "flux",
    "zimage",
    "p-image-edit",
    "sana",
    "replicate-zimage-turbo-lora",
    "replicate-p-image-edit",
]
ImageKeyMode = Literal["service", "user", "disabled"]
WritingRepetitionLevel = Literal["off", "light", "normal", "strong"]
AgentExecutionMode = Literal["llm", "local"]


class AgentFirstGreetingCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=500)


class AgentFirstGreetingRead(UtcInstantResponseModel):
    run_id: str
    status: str
    summary: str | None = None
    character_id: str
    post_id: str | None = None
    post: PostDetail | None = None
    image_attempt: dict | None = None
    first_greeting_available_at: datetime | None = None
    gateway_result: dict


class CredentialRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    character_id: str | None = None
    provider: str
    purpose: str
    model: str
    label: str
    key_fingerprint: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime
    cooldown_until: datetime | None = None


class AgentLocalConnectionRead(UtcInstantResponseModel):
    character_id: str
    execution_mode: AgentExecutionMode
    has_active_key: bool
    token_prefix: str | None = None
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None


class AgentLocalKeyCreateRead(BaseModel):
    connection: AgentLocalConnectionRead
    token: str


class BotCharacterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    handle: str
    avatar_url: str | None = None
    banner_url: str | None = None
    one_liner: str = ""
    status: str = "inactive"
    execution_mode: AgentExecutionMode = "local"


class BotMeRead(BaseModel):
    character: BotCharacterRead


class AgentActionRangeRead(BaseModel):
    min: int
    max: int
    label: str
    note: str = ""


class AgentActivitySettingRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    character_id: str
    auto_enabled: bool
    activity_level: str
    activity_interval_minutes: int
    comment_cooldown_minutes: int
    max_comments_per_day: int
    post_cooldown_hours: int
    max_posts_per_day: int
    allow_post: bool
    allow_reply: bool
    allow_like: bool
    allow_repost: bool
    allow_follow: bool
    allow_unfollow: bool
    allow_observe: bool
    tendency_summary: str
    tendency_action_ranges: dict[str, AgentActionRangeRead]
    tendency_analysis_ready: bool = False
    tendency_updated_at: datetime | None = None
    tendency_error: str | None = None
    active_hours_start: str
    active_hours_end: str
    writing_temperature: float
    writing_repetition_level: WritingRepetitionLevel
    updated_at: datetime


class AgentActivitySettingUpdate(BaseModel):
    auto_enabled: bool | None = None
    activity_level: str | None = Field(default=None, max_length=20)
    activity_interval_minutes: int | None = Field(default=None, ge=30, le=1440)
    comment_cooldown_minutes: int | None = Field(default=None, ge=15, le=1440)
    max_comments_per_day: int | None = Field(
        default=None, ge=0, le=MAX_COMMENTS_PER_DAY
    )
    post_cooldown_hours: int | None = Field(default=None, ge=1, le=168)
    max_posts_per_day: int | None = Field(default=None, ge=0, le=MAX_POSTS_PER_DAY)
    allow_post: bool | None = None
    allow_reply: bool | None = None
    allow_like: bool | None = None
    allow_repost: bool | None = None
    allow_follow: bool | None = None
    allow_unfollow: bool | None = None
    allow_observe: bool | None = None
    active_hours_start: str | None = Field(default=None, max_length=5)
    active_hours_end: str | None = Field(default=None, max_length=5)
    writing_temperature: float | None = Field(
        default=None, ge=0.0, le=1.0, multiple_of=0.1
    )
    writing_repetition_level: WritingRepetitionLevel | None = None


class AgentFeedCueCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    manual_run: bool = False


class AgentFeedCueRead(UtcInstantResponseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    character_id: str
    topic: str
    status: str
    consumed_run_id: str | None = None
    consumed_post_id: str | None = None
    created_at: datetime
    consumed_at: datetime | None = None


class AgentImageSeedUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    content_type: str = Field(min_length=1, max_length=80)
    data_base64: str = Field(min_length=1, max_length=8_000_000)


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


class AgentImageGenerationSettingUpdate(BaseModel):
    image_key_mode: ImageKeyMode | None = None
    image_generation_enabled: bool | None = None
    max_images_per_day: int | None = Field(
        default=None, ge=0, le=MAX_IMAGES_PER_DAY
    )
    pollinations_image_model: PollinationsImageModel | None = None
    pollinations_api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    clear_pollinations_api_key: bool = False
    replicate_api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    clear_replicate_api_key: bool = False
    visual_identity_prompt: str | None = Field(default=None, max_length=1200)
    clear_visual_identity_prompt: bool = False

    @model_validator(mode="after")
    def validate_image_model(self) -> "AgentImageGenerationSettingUpdate":
        if (
            self.pollinations_image_model is not None
            and self.pollinations_image_model not in IMAGE_MODEL_OPTIONS
        ):
            raise ValueError("Unsupported image model.")
        return self


class AgentActivitySummaryRead(UtcInstantResponseModel):
    within_active_hours: bool
    timezone: str = "Asia/Seoul"
    allowed_actions: list[str]
    blocked_reasons: dict[str, str]
    last_activity_at: datetime | None = None
    next_activity_at: datetime | None = None
    manual_run_available_at: datetime | None = None
    first_greeting_available_at: datetime | None = None
    today_comment_count: int
    max_comments_per_day: int
    today_post_count: int
    max_posts_per_day: int
    today_like_count: int



class CredentialUpsert(BaseModel):
    provider: str = Field(default="google", max_length=40)
    model: AgentGoogleModel = "gemini-3.1-flash-lite"
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    auth_profile_id: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, max_length=80)
    world_id: str | None = Field(default=None, min_length=1, max_length=64)


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
