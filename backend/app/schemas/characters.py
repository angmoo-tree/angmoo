from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domains.social.schemas.community import CommentRead


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

from app.domains.characters.schemas import (
    CharacterRead,
    CharacterStateWrite,
    AgentCharacterStateWrite,
    CharacterStateRead,
)
