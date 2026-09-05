from app.domains.characters.schemas import (
    AgentImageGenerationSettingRead,
    AgentDetailRead,
)

from app.domains.runtime.schemas import (
    AgentActionRangeRead,
    AgentActivitySettingRead,
    AgentActivitySummaryRead,
)

from app.domains.identity.schemas import (
    CredentialRead,
)

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





class CredentialUpsert(BaseModel):
    provider: str = Field(default="google", max_length=40)
    model: AgentGoogleModel = "gemini-3.1-flash-lite"
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    auth_profile_id: str | None = Field(default=None, max_length=120)
    label: str | None = Field(default=None, max_length=80)
    world_id: str | None = Field(default=None, min_length=1, max_length=64)
