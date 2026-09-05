from app.domains.routines.schemas.resident import (
    AgentActivityLogRead,
    AgentSlotRead,
)

from datetime import UTC, datetime
from typing import Any

from app.core.response_schemas import (
    normalize_utc_instant,
    UtcInstantResponseModel,
)

from pydantic import BaseModel, ConfigDict, Field, field_validator



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



class AgentSlotPublicRead(UtcInstantResponseModel):
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


class ResidentSlotTickRead(UtcInstantResponseModel):
    due_count: int
    started_count: int
    results: list[OpenClawAgentRunRead]
    slots: list[AgentSlotRead]
