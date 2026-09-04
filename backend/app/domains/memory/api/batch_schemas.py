"""Owner-only, saved-state Memory batch controls; never contains secrets."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from app.domains.memory.api.schemas import MemoryScopeRead


class MemoryBatchSettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    expected_profile_version: int = Field(ge=0)
    ai_enabled: bool
    shutdown_enabled: bool
    schedule_enabled: bool
    local_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    consent_version: str | None = Field(default=None, max_length=48)
    model_id: str | None = Field(default=None, max_length=120)
    idempotency_key: str = Field(min_length=8, max_length=128)


class MemoryBatchSettingRead(BaseModel):
    scope: MemoryScopeRead
    version: int
    memory_enabled: bool
    ai_enabled: bool
    shutdown_enabled: bool
    schedule_enabled: bool
    local_time: str
    timezone: str
    next_due_at: datetime | None
    model_id: str | None
    profile_version: int
    pending_count: int
    status: str
    last_code: str | None
    last_completed_at: datetime | None
    available_models: list[str]


class MemoryBatchRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=8, max_length=128)
