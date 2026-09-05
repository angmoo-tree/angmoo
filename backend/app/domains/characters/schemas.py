"""Character identity/state and owner-facing profile/creation inputs."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.domains.media.schemas import validate_profile_media_reference
from app.providers.registry import AGENT_GOOGLE_MODELS

AgentGoogleModel = Literal[*AGENT_GOOGLE_MODELS]
AgentExecutionMode = Literal["llm", "local"]

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
