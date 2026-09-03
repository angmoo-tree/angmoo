"""Read-only Memory surface contracts.

The public Memory surface deliberately separates a stored memory from the
current availability of the canonical source that formed it.  Source ids stay
inside the application boundary; API presenters may expose only an approved
navigation target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domains.memory.domain.lifecycle import MemoryItemRecord
from app.domains.memory.domain.provenance import MemorySourceTypeV1


MEMORY_READ_CONTRACT_VERSION = "memory-read.v1"
MAX_MEMORY_READ_PAGE_SIZE = 50
MAX_MEMORY_READ_EVIDENCE_ITEMS = 50


class MemoryLifecycle(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class MemoryEvidenceAvailability(StrEnum):
    AVAILABLE = "available"
    DELETED = "deleted"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class MemoryItemEvidenceRecord:
    source_type: MemorySourceTypeV1
    source_id: str
    source_world_id: str
    source_created_at: datetime
    source_digest: str
    actor_world_character_id: str | None
    target_world_character_id: str | None
    counterpart_world_character_id: str | None
    thread_id: str | None


@dataclass(frozen=True, slots=True)
class MemoryEvidenceRead:
    source_type: MemorySourceTypeV1
    source_created_at: datetime
    availability: MemoryEvidenceAvailability
    excerpt: str | None
    actor_world_character_id: str | None = None
    target_world_character_id: str | None = None
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryItemPage:
    items: tuple[MemoryItemRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class MemoryItemDetail:
    item: MemoryItemRecord
    lifecycle: MemoryLifecycle
    evidence: tuple[MemoryEvidenceRead, ...]


__all__ = [
    "MAX_MEMORY_READ_EVIDENCE_ITEMS",
    "MAX_MEMORY_READ_PAGE_SIZE",
    "MEMORY_READ_CONTRACT_VERSION",
    "MemoryEvidenceAvailability",
    "MemoryEvidenceRead",
    "MemoryItemDetail",
    "MemoryItemEvidenceRecord",
    "MemoryItemPage",
    "MemoryLifecycle",
]
