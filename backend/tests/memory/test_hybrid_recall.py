import asyncio
import pytest
from dataclasses import replace
from datetime import UTC, datetime
from time import monotonic

from app.domains.memory.contracts.hybrid_recall import (
    HybridAxisResult, HybridRecallRequest, RankedMemoryCandidate, RecallAxisReceipt, RecallAxisStatus,
)
from app.domains.memory.contracts.recall import CanonicalRecallRecord, MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.service.hybrid_recall import HybridRecallService, reciprocal_rank_fusion


def candidate(name, *, memory="same-memory", version=1):
    return RankedMemoryCandidate(MemoryRecallCandidate(name, memory, RecallDocumentKind.MEMORY_ITEM, memory, 0, ""), version, "a"*64)


def test_fusion_combines_same_document_version_but_not_evidence_or_stale_version():
    summary, evidence, stale = candidate("summary"), candidate("evidence"), candidate("summary", version=2)
    combined = reciprocal_rank_fusion((evidence, summary, summary), (summary, stale))
    assert combined == (summary, evidence, stale)


def test_axes_overlap_and_preserve_partial_status_without_any_planner():
    entered = set()
    class Axis:
        def __init__(self, name): self.name = name
        async def search(self, request, *, deadline):
            entered.add(self.name)
            while len(entered) != 2:
                await asyncio.sleep(0)
            rows = (candidate("summary"),) if self.name == "fts" else ()
            status = RecallAxisStatus.READY if rows else RecallAxisStatus.DISABLED
            return HybridAxisResult(rows, RecallAxisReceipt(self.name, status, bool(rows), len(rows), 0))
    class Canonical:
        def revalidate(self, request, candidates):
            assert [c.candidate.document_id for c in candidates] == ["summary"]
            return (CanonicalRecallRecord("memory-item:one", RecallDocumentKind.MEMORY_ITEM, "one", "verified", datetime.now(UTC), memory_item_id="one"),)
        def hydrate(self, request, records): return records, ()
    request = HybridRecallRequest("request", "call", "b"*64, MemoryScope("owner", "world", "self"), "기억", "profile", (RecallDocumentKind.MEMORY_ITEM,))
    service = HybridRecallService(fts=Axis("fts"), vector=Axis("vector"), canonical=Canonical())
    result = asyncio.run(service.execute(request, deadline=monotonic()+2))
    assert result.status is RecallAxisStatus.PARTIAL
    assert result.embedding_usage.logical_calls == 0
    assert result.embedding_usage.physical_attempts is None
    assert len(result.records) == 1


def test_deadline_cancels_and_joins_both_axes():
    finished = set()
    class Axis:
        def __init__(self, name): self.name = name
        async def search(self, request, *, deadline):
            try:
                await asyncio.Event().wait()
            finally:
                finished.add(self.name)
    request = HybridRecallRequest("request", "call", "b"*64, MemoryScope("owner", "world", "self"), "query", "profile", (RecallDocumentKind.MEMORY_ITEM,))
    service = HybridRecallService(fts=Axis("fts"), vector=Axis("vector"), canonical=None)
    async def run():
        with pytest.raises(TimeoutError):
            await service.execute(request, deadline=monotonic()+0.05)
        assert finished == {"fts", "vector"}
    asyncio.run(run())
