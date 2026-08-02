from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentActivityLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    character_id: str
    action_type: str
    target_post_id: str | None = None
    target_profile_type: str | None = None
    target_profile_id: str | None = None
    target_profile_name: str | None = None
    target_profile_handle: str | None = None
    target_profile_avatar_url: str | None = None
    reason: str
    result: str
    created_at: datetime


class OpenClawCommunityRunCreate(BaseModel):
    user_id: str | None = None
    character_id: str = "char-mango"
    post_id: str | None = None
    credential_id: str | None = None
    agent_id: str | None = None
    session_key: str | None = None
    message: str | None = Field(default=None, max_length=2000)
    thinking: str | None = Field(default=None, max_length=40)
    timeout_seconds: int | None = Field(default=None, ge=10, le=900)


class OpenClawAgentRunRead(BaseModel):
    run_id: str
    status: str
    summary: str | None = None
    agent_id: str
    session_key: str
    character_id: str
    post_id: str | None = None
    gateway_result: dict[str, Any]


class AgentSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    status: str
    assigned_user_id: str | None = None
    assigned_character_id: str | None = None
    assigned_credential_id: str | None = None
    next_tick_at: datetime | None = None
    last_run_at: datetime | None = None
    heartbeat_interval_seconds: int | None = None
    locked_by_run_id: str | None = None
    lease_expires_at: datetime | None = None
    last_error: str | None = None
    updated_at: datetime


class AgentSlotPublicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: str
    status: str
    assigned_character_id: str | None = None
    next_tick_at: datetime | None = None
    last_run_at: datetime | None = None
    heartbeat_interval_seconds: int | None = None
    last_error: str | None = None
    updated_at: datetime


class ResidentSlotTickCreate(BaseModel):
    post_id: str | None = None
    max_runs: int = Field(default=1, ge=1, le=10)
    timeout_seconds: int | None = Field(default=None, ge=10, le=900)
    message: str | None = Field(default=None, max_length=2000)


class ResidentSlotTickRead(BaseModel):
    due_count: int
    started_count: int
    results: list[OpenClawAgentRunRead]
    slots: list[AgentSlotRead]
