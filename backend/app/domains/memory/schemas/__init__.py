from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MemoryMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemorySettingUpdate(MemoryMutationRequest):
    schema_version: Literal["memory-setting-update.v1"] = "memory-setting-update.v1"
    expected_version: int = Field(ge=0)
    enabled: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


class MemoryPinUpdate(MemoryMutationRequest):
    schema_version: Literal["memory-pin-update.v1"] = "memory-pin-update.v1"
    expected_version: int = Field(ge=1)
    pinned: bool
    idempotency_key: str = Field(min_length=8, max_length=128)


class MemoryCorrectionCreate(MemoryMutationRequest):
    schema_version: Literal["memory-correction-create.v1"] = (
        "memory-correction-create.v1"
    )
    expected_item_version: int = Field(ge=1)
    expected_scope_version: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=2_000)
    idempotency_key: str = Field(min_length=8, max_length=128)


class MemoryDeleteCreate(MemoryMutationRequest):
    schema_version: Literal["memory-delete.v1"] = "memory-delete.v1"
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class MemoryScopeRead(BaseModel):
    world_id: str
    subject_world_character_id: str


class MemoryCapabilitiesRead(BaseModel):
    read: Literal["available"] = "available"
    mutate: Literal["available"] = "available"


class MemorySettingRead(BaseModel):
    schema_version: Literal["memory-setting-read.v1"] = "memory-setting-read.v1"
    scope: MemoryScopeRead
    configured: bool
    enabled: bool
    retention_days: int
    provider_mode: Literal["none", "optional-configured"]
    version: int
    capabilities: MemoryCapabilitiesRead = Field(
        default_factory=MemoryCapabilitiesRead
    )


class MemoryRelatedCharacterRead(BaseModel):
    display_name: str
    direction: Literal["incoming", "outgoing", "contextual"]


class MemoryItemSummaryRead(BaseModel):
    id: str
    memory_kind: str
    summary: str
    lifecycle: Literal["active", "expired", "superseded", "deleted"]
    formed_at: datetime
    valid_from: datetime
    valid_until: datetime | None
    pinned: bool
    superseded_by_memory_id: str | None = None
    retention_days: int
    related_character: MemoryRelatedCharacterRead | None = None
    version: int


class MemoryItemListRead(BaseModel):
    schema_version: Literal["memory-item-list.v1"] = "memory-item-list.v1"
    scope: MemoryScopeRead
    memory_enabled: bool
    items: list[MemoryItemSummaryRead]
    next_cursor: str | None = None
    capabilities: MemoryCapabilitiesRead = Field(
        default_factory=MemoryCapabilitiesRead
    )


class MemoryEvidenceRead(BaseModel):
    source_kind: str
    source_label: str
    source_created_at: datetime
    availability: Literal["available", "deleted", "unavailable"]
    excerpt: str | None
    related_character: MemoryRelatedCharacterRead | None = None
    canonical_href: str | None = None


class MemoryItemDetailRead(MemoryItemSummaryRead):
    schema_version: Literal["memory-item-detail.v1"] = "memory-item-detail.v1"
    scope: MemoryScopeRead
    evidence: list[MemoryEvidenceRead]
    provenance_summary: str
    capabilities: MemoryCapabilitiesRead = Field(
        default_factory=MemoryCapabilitiesRead
    )


class MemorySettingMutationRead(BaseModel):
    schema_version: Literal["memory-setting-mutation.v1"] = (
        "memory-setting-mutation.v1"
    )
    outcome: Literal["updated", "reused"]
    setting: MemorySettingRead
    projection_cleanup: Literal["automatic_after_commit"] = "automatic_after_commit"


class MemoryItemMutationRead(BaseModel):
    schema_version: Literal["memory-item-mutation.v1"] = "memory-item-mutation.v1"
    operation: Literal["pin", "unpin", "correct", "delete"]
    outcome: Literal["updated", "reused", "deleted"]
    scope: MemoryScopeRead
    item: MemoryItemSummaryRead
    replaced_memory_id: str | None = None
    projection_cleanup: Literal["automatic_after_commit"] = "automatic_after_commit"


__all__ = [
    "MemoryCorrectionCreate",
    "MemoryDeleteCreate",
    "MemoryEvidenceRead",
    "MemoryItemDetailRead",
    "MemoryItemListRead",
    "MemoryItemMutationRead",
    "MemoryItemSummaryRead",
    "MemoryPinUpdate",
    "MemorySettingMutationRead",
    "MemorySettingRead",
    "MemorySettingUpdate",
]
