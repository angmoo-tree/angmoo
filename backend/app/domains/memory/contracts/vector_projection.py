"""Versioned projection identities; a vector hit is never canonical evidence."""
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from app.domains.memory.contracts.scope import MemoryScope


@dataclass(frozen=True, slots=True)
class MemoryVectorDocument:
    document_id: str
    memory_item_id: str
    scope: MemoryScope
    version: int
    content_hash: str
    profile: str
    vector: Sequence[float]
    occurred_at: datetime
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryVectorHit:
    document_id: str
    memory_item_id: str
    version: int
    content_hash: str
    distance: float


@dataclass(frozen=True, slots=True)
class MemoryVectorQuery:
    scope: MemoryScope
    profile: str
    vector: Sequence[float]
    limit: int = 50
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None

    def __post_init__(self):
        if not 1 <= self.limit <= 50 or not self.profile:
            raise ValueError("memory_vector_query_invalid")


@dataclass(frozen=True, slots=True)
class MemoryVectorSearchResult:
    hits: tuple[MemoryVectorHit, ...]
    allowed_count: int
    generation: str
    duration_ms: float
    search_mode: str = "nn"
    index_kind: str = "flat"
