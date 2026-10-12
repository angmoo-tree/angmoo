"""World-owned commands and cross-domain erasure ports."""
from typing import Protocol, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

DeletionState = Literal["accepted", "draining", "purging", "cleaning", "verifying", "retry_wait", "failed", "completed"]


class WorldDeletionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_row_version: int = Field(ge=1, strict=True)
    confirmed_name: str = Field(min_length=1, max_length=120)
    consent: Literal[True]
    idempotency_key: str = Field(min_length=16, max_length=128)

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("permanent_deletion_consent_required")
        return value


class WorldDeletionReceipt(BaseModel):
    request_id: str
    world_id: str
    state: DeletionState
    accepted_at: datetime
    completed_at: datetime | None = None
    can_retry: bool = False


class WorldDeletionPreview(BaseModel):
    world_id: str
    stored_name: str
    row_version: int
    can_delete: bool
    is_default_space: bool
    export_available: bool


class WorldErasurePorts(Protocol):
    def drain(self, db, world_id: str) -> bool: ...
    def collect(self, db, request, limit: int) -> bool: ...
    def purge(self, db, request, limit: int) -> bool: ...
    def clean(self, db, request, limit: int) -> bool: ...
    def verify(self, db, request) -> bool: ...


class WorldDeletionError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)
