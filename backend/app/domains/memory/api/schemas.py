from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemoryScopeRead(BaseModel):
    world_id: str
    subject_world_character_id: str


class MemoryCapabilitiesRead(BaseModel):
    read: Literal["available"] = "available"
    mutate: Literal["not_available_in_p8_l_q"] = "not_available_in_p8_l_q"


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


__all__ = [
    "MemoryEvidenceRead",
    "MemoryItemDetailRead",
    "MemoryItemListRead",
    "MemoryItemSummaryRead",
    "MemorySettingRead",
]
