"""Bounded lexical search values, including incomplete-search receipts."""
from dataclasses import dataclass, field
from app.domains.memory.contracts.recall import MemoryRecallCandidate, MemoryRecallSearchQuery
from app.domains.memory.contracts.hybrid_recall import RecallAxisStatus


@dataclass(frozen=True, slots=True)
class FtsQueryGroup:
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GroupedFtsQuery:
    groups: tuple[FtsQueryGroup, ...]
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class FtsSearchBatch:
    candidates: tuple[MemoryRecallCandidate, ...]
    status: RecallAxisStatus
    executed: bool
    reason_code: str | None
    stats: dict[str, int | bool] = field(default_factory=dict)

    def __post_init__(self):
        if len(self.candidates) > 50 or (self.candidates and self.status not in (RecallAxisStatus.READY, RecallAxisStatus.PARTIAL)):
            raise ValueError("fts_batch_invalid")


@dataclass(frozen=True, slots=True)
class FtsWorkerRequest:
    query: MemoryRecallSearchQuery
    capture_details: bool = False
