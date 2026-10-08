"""Owner-facing settings and status for provider-free canonical memory saving."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.domains.memory.schemas import MemoryScopeRead


class MemoryProcessingRead(BaseModel):
    scope: MemoryScopeRead
    version: int
    memory_enabled: bool
    daily_enabled: bool
    local_time: str
    timezone: str
    shutdown_apply_enabled: bool
    next_due_at: datetime | None
    last_applied_at: datetime | None
    pending_count: int
    blocked_count: int
    status: Literal["idle", "accepted", "applying", "saved", "partial_error"]
    applied_count: int = 0
    result: str | None = None
    resolved_request_key: str | None = None


class MemoryProcessingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    daily_enabled: bool
    local_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    shutdown_apply_enabled: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


class MemorySaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128)
