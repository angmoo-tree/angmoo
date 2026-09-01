"""Read-only canonical evidence boundary; P8-L-G supplies implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domains.memory.domain.provenance import MemorySourceTypeV1
from app.domains.memory.domain.scope import MemoryScope


@dataclass(frozen=True, slots=True)
class CanonicalMemoryEvidence:
    source_type: MemorySourceTypeV1
    source_id: str
    source_world_id: str
    source_digest: str
    source_created_at: datetime
    actor_world_character_id: str | None = None
    target_world_character_id: str | None = None
    observation_id: str | None = None


class MemorySourceEvidenceReaderPort(Protocol):
    def read_evidence(
        self,
        *,
        scope: MemoryScope,
        source_type: MemorySourceTypeV1,
        source_id: str,
    ) -> CanonicalMemoryEvidence | None: ...


__all__ = ["CanonicalMemoryEvidence", "MemorySourceEvidenceReaderPort"]
