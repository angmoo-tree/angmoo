"""Optional provider boundary for background Memory consolidation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.memory.domain.consolidation import MemoryMaintenanceLane
from app.domains.memory.domain.consolidation_provider import MemorySummaryProposal


@dataclass(frozen=True, slots=True)
class MemoryConsolidationSource:
    candidate_ref: str
    memory_kind: str
    deterministic_summary: str


@dataclass(frozen=True, slots=True)
class MemoryConsolidationProviderRequest:
    batch_ref: str
    lane: MemoryMaintenanceLane
    sources: tuple[MemoryConsolidationSource, ...]


@dataclass(frozen=True, slots=True)
class MemoryConsolidationProviderResult:
    proposals: tuple[MemorySummaryProposal, ...]
    provider: str
    model: str
    physical_call_count: int
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None


class MemoryConsolidationProviderError(RuntimeError):
    def __init__(self, code: str, *, physical_call_count: int) -> None:
        super().__init__(code)
        self.code = code
        self.physical_call_count = physical_call_count


class MemoryConsolidationProviderPort(Protocol):
    async def consolidate(
        self,
        request: MemoryConsolidationProviderRequest,
    ) -> MemoryConsolidationProviderResult: ...


__all__ = [
    "MemoryConsolidationProviderError",
    "MemoryConsolidationProviderPort",
    "MemoryConsolidationProviderRequest",
    "MemoryConsolidationProviderResult",
    "MemoryConsolidationSource",
]
