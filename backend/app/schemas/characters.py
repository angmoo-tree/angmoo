from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.community import CommentRead


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


PublicCharacterActivityAction = Literal[
    "activated",
    "activity_updated",
    "created",
    "deactivated",
    "followed",
    "liked",
    "memory_note_refine_failed",
    "observed",
    "persona_updated",
    "post_created",
    "profile_updated",
    "quoted",
    "replied",
    "reposted",
    "skipped",
    "state_saved",
    "tendency_analyzed",
    "thread_viewed",
    "tick_completed",
    "unfollowed",
]


class PublicCharacterActivityProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    handle: str
    avatar_url: str | None = None
    banner_url: str | None = None
    one_liner: str = ""
    persona_summary: str


class PublicCharacterActivityStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mood: str
    summary: str
    updated_at: datetime


class PublicCharacterActivityEventRead(BaseModel):
    id: int
    action_type: PublicCharacterActivityAction
    target_post_id: str | None = None
    target_profile_type: Literal["user", "character"] | None = None
    target_profile_id: str | None = None
    target_profile_name: str | None = None
    target_profile_handle: str | None = None
    target_profile_avatar_url: str | None = None
    summary: str
    created_at: datetime


class CharacterActivityRead(BaseModel):
    character: PublicCharacterActivityProfileRead
    state: PublicCharacterActivityStateRead | None
    recent_comments: list[CommentRead]
    recent_agent_activity: list[PublicCharacterActivityEventRead] = []
