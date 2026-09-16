"""Planner-free request, projection ranks and canonical result receipts."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
import math
import re

_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _duration(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

from app.domains.memory.contracts.recall import CanonicalRecallRecord, MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope


class RecallAxisStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class HybridRecallRequest:
    request_id: str
    call_id: str
    envelope_hash: str
    scope: MemoryScope
    search_text: str
    profile: str
    kinds: tuple[RecallDocumentKind, ...]
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    counterpart_world_character_id: str | None = None
    thread_id: str | None = None
    axis_limit: int = 50
    result_limit: int = 10
    episode_source_kinds: tuple[RecallDocumentKind, ...] = ()

    def __post_init__(self):
        if (not self.request_id or not self.call_id or not _HASH.fullmatch(self.envelope_hash)
                or not isinstance(self.search_text, str) or not self.search_text.strip()
                or len(self.search_text) > 4000 or not self.profile or not self.kinds
                or not 1 <= self.result_limit <= 20 or not 1 <= self.axis_limit <= 50):
            raise ValueError("hybrid_recall_request_invalid")
        if any(not isinstance(k, RecallDocumentKind) for k in self.kinds):
            raise ValueError("hybrid_recall_kind_invalid")
        if any(not isinstance(k, RecallDocumentKind) or k is RecallDocumentKind.MEMORY_ITEM for k in self.episode_source_kinds):
            raise ValueError("hybrid_episode_source_kind_invalid")
        if any(t is not None and t.tzinfo is None for t in (self.occurred_from, self.occurred_to)):
            raise ValueError("hybrid_recall_time_invalid")
        if self.occurred_from and self.occurred_to and self.occurred_from >= self.occurred_to:
            raise ValueError("hybrid_recall_time_invalid")


@dataclass(frozen=True, slots=True)
class RankedMemoryCandidate:
    candidate: MemoryRecallCandidate
    version: int
    content_hash: str

    def __post_init__(self):
        if (not _count(self.version) or self.version < 1 or not _HASH.fullmatch(self.content_hash)
                or not isinstance(self.candidate, MemoryRecallCandidate)
                or not math.isfinite(self.candidate.score)):
            raise ValueError("hybrid_candidate_invalid")

    @property
    def identity(self):
        return (self.candidate.document_id, self.version, self.content_hash)


@dataclass(frozen=True, slots=True)
class RecallAxisReceipt:
    axis: str
    status: RecallAxisStatus
    executed: bool
    candidate_count: int
    duration_ms: float
    reason_code: str | None = None
    generation: str | None = None
    physical_scan_count: int | None = None

    def __post_init__(self):
        if (self.axis not in {"fts", "vector"} or not isinstance(self.status, RecallAxisStatus)
                or not isinstance(self.executed, bool) or not _count(self.candidate_count)
                or self.candidate_count > 50 or not _duration(self.duration_ms)
                or (self.physical_scan_count is not None and not _count(self.physical_scan_count))):
            raise ValueError("hybrid_axis_receipt_invalid")


@dataclass(frozen=True, slots=True)
class HybridEmbeddingUsage:
    logical_calls: int = 0
    physical_attempts: int | None = None
    input_tokens: int | None = None
    duration_ms: float | None = None

    def __post_init__(self):
        if (not _count(self.logical_calls) or self.logical_calls > 1
                or any(value is not None and not _count(value) for value in (self.physical_attempts, self.input_tokens))
                or (self.duration_ms is not None and not _duration(self.duration_ms))):
            raise ValueError("hybrid_embedding_usage_invalid")


@dataclass(frozen=True, slots=True)
class HybridSourceReceipt:
    reference: str
    status: RecallAxisStatus
    record_count: int

    def __post_init__(self):
        if not self.reference or not isinstance(self.status, RecallAxisStatus) or not _count(self.record_count):
            raise ValueError("hybrid_source_receipt_invalid")


@dataclass(frozen=True, slots=True)
class HybridRecallResult:
    request_id: str
    call_id: str
    envelope_hash: str
    scope: MemoryScope
    status: RecallAxisStatus
    records: tuple[CanonicalRecallRecord, ...]
    axes: tuple[RecallAxisReceipt, ...]
    sources: tuple[HybridSourceReceipt, ...]
    embedding_usage: HybridEmbeddingUsage
    fused_count: int
    excluded_count: int
    duration_ms: float

    def __post_init__(self):
        if (not self.request_id or not self.call_id or not _HASH.fullmatch(self.envelope_hash)
                or not isinstance(self.status, RecallAxisStatus)
                or not isinstance(self.records, tuple) or len(self.records) > 50
                or any(not isinstance(r, CanonicalRecallRecord) for r in self.records)
                or not isinstance(self.axes, tuple) or len(self.axes) != 2
                or {r.axis for r in self.axes} != {"fts", "vector"}
                or not _count(self.fused_count) or not _count(self.excluded_count)
                or self.excluded_count > self.fused_count or self.fused_count > 50
                or not _duration(self.duration_ms) or len(self.sources) > 400):
            raise ValueError("hybrid_recall_result_invalid")


@dataclass(frozen=True, slots=True)
class HybridAxisResult:
    candidates: tuple[RankedMemoryCandidate, ...]
    receipt: RecallAxisReceipt
    embedding_usage: HybridEmbeddingUsage = HybridEmbeddingUsage()

    def __post_init__(self):
        if (not isinstance(self.candidates, tuple) or len(self.candidates) > 50
                or any(not isinstance(row, RankedMemoryCandidate) for row in self.candidates)
                or len(self.candidates) != self.receipt.candidate_count
                or (self.candidates and self.receipt.status not in {RecallAxisStatus.READY, RecallAxisStatus.PARTIAL})):
            raise ValueError("hybrid_axis_result_invalid")


class HybridSearchAxis(Protocol):
    async def search(self, request: HybridRecallRequest, *, deadline: float) -> HybridAxisResult: ...


class HybridCanonicalReader(Protocol):
    def revalidate(self, request: HybridRecallRequest, candidates: tuple[RankedMemoryCandidate, ...]) -> tuple[CanonicalRecallRecord, ...]: ...
    def hydrate(self, request: HybridRecallRequest, records: tuple[CanonicalRecallRecord, ...]) -> tuple[tuple[CanonicalRecallRecord, ...], tuple[HybridSourceReceipt, ...]]: ...
