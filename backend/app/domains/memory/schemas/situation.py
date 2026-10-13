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
    operation: Literal["pending_apply", "blocked_recheck"] | None = None
    run_id: str | None = None
    run_state: Literal["pending", "running", "deferred", "completed", "error"] | None = None
    rejected_count: int = 0
    skipped_count: int = 0
    scope_busy: bool = False
    can_recheck: bool = False


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


class MemoryIndividualRecheckRequest(MemorySaveRequest):
    expected_receipt_version: int = Field(ge=1)


class MemorySituationDiscardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_receipt_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class MemoryUnsavedExperienceRead(BaseModel):
    receipt_sequence: int
    state_version: int
    occurred_at: datetime
    description: str | None
    reason: Literal["source_changed", "access_unavailable", "proof_unavailable", "activation_closed", "description_invalid", "result_invalid", "validation_failed"]
    can_recheck: bool
    can_discard: bool


class MemoryUnsavedExperiencesRead(BaseModel):
    scope: MemoryScopeRead
    items: list[MemoryUnsavedExperienceRead]
    next_cursor: str | None
    blocked_count: int
    scope_busy: bool
    can_recheck: bool


class MemorySituationDiscardRead(BaseModel):
    scope: MemoryScopeRead
    receipt_sequence: int
    state: Literal["discarded"]
    state_version: int
    discarded_at: datetime
    operation: Literal["discard"] = "discard"
    result: Literal["discarded", "already_discarded"]
    resolved_request_key: str
    pending_count: int
    blocked_count: int
