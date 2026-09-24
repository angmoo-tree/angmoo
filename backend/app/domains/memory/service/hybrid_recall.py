"""Equal-weight document-level RRF, before canonical authorization/hydration."""
from collections.abc import Sequence
import asyncio
from time import monotonic
from app.contracts.search_diagnostics import collector, lineage, record_identity

from app.domains.memory.contracts.hybrid_recall import RankedMemoryCandidate
from app.domains.memory.contracts.hybrid_recall import (
    HybridCanonicalReader, HybridRecallRequest, HybridRecallResult,
    HybridSearchAxis, RecallAxisStatus,
)


def reciprocal_rank_fusion(*axes: Sequence[RankedMemoryCandidate], limit: int = 50):
    if not 1 <= limit <= 100:
        raise ValueError("hybrid_fusion_limit_invalid")
    scores: dict[tuple, float] = {}
    documents: dict[tuple, RankedMemoryCandidate] = {}
    order: dict[tuple, int] = {}
    for axis_index, axis in enumerate(axes):
        seen: set[tuple] = set()
        for rank, item in enumerate(axis, 1):
            key = item.identity
            lineage("axis", "returned", axis="fts" if axis_index == 0 else "vector", rank=rank,
                identities={"document_ref": ("d", item.candidate.document_id), "identity_ref": ("i", key),
                    "memory_ref": ("m", item.candidate.memory_item_id)})
            if key in seen:
                continue
            seen.add(key)
            scores[key] = scores.get(key, 0.0) + 1.0 / (60 + rank)
            if key not in documents:
                documents[key] = item
                order[key] = len(order)
    result = tuple(documents[key] for key in sorted(scores, key=lambda k: (-scores[k], order[k]))[:limit])
    if collector() is not None:
        for rank, item in enumerate(result, 1):
            lineage("rrf", "selected", rank=rank, identities={"identity_ref": ("i", item.identity),
                "document_ref": ("d", item.candidate.document_id), "memory_ref": ("m", item.candidate.memory_item_id)})
    return result


class HybridRecallService:
    """Axes own interruption/join; no request Session is shared across tasks."""
    def __init__(self, *, fts: HybridSearchAxis, vector: HybridSearchAxis,
                 canonical: HybridCanonicalReader):
        self._fts = fts
        self._vector = vector
        self._canonical = canonical

    async def execute(self, request: HybridRecallRequest, *, deadline: float) -> HybridRecallResult:
        started = monotonic()
        if deadline <= started:
            raise TimeoutError("hybrid_recall_deadline")
        # Leave time for native worker termination and canonical validation, so
        # an axis timeout can return its unavailable receipt beside a ready axis.
        axis_deadline = deadline - min(0.5, (deadline - started) * 0.1)
        axis_request = getattr(self._canonical, "axis_request", lambda value: value)(request)
        tasks = [asyncio.create_task(axis.search(axis_request, deadline=axis_deadline))
                 for axis in (self._fts, self._vector)]
        try:
            async with asyncio.timeout(max(0.0, deadline - monotonic())):
                fts, vector = await asyncio.gather(*tasks)
        finally:
            # Returning/cancelling the caller must not leave a native read running.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if (fts.receipt.axis, vector.receipt.axis) != ("fts", "vector"):
            raise ValueError("hybrid_axis_identity_mismatch")
        if monotonic() >= deadline:
            raise TimeoutError("hybrid_recall_deadline")
        if any(r.receipt.status is RecallAxisStatus.CANCELLED for r in (fts, vector)):
            raise asyncio.CancelledError()
        available = {RecallAxisStatus.READY, RecallAxisStatus.PARTIAL}
        if not any(r.receipt.status in available for r in (fts, vector)):
            raise RuntimeError("hybrid_all_axes_unavailable")
        fused = reciprocal_rank_fusion(fts.candidates, vector.candidates)
        records = self._canonical.revalidate(request, fused)
        if monotonic() >= deadline:
            raise TimeoutError("hybrid_recall_deadline")
        # Canonical validation preserves fusion order; memory IDs deduplicate only
        # after document/version identity has received its own RRF contribution.
        selected = []
        seen = set()
        for record in records:
            key = record.memory_item_id or record.reference
            if key not in seen:
                selected.append(record)
                seen.add(key)
                lineage("select", "selected", identities=record_identity(record))
            else:
                lineage("select", "merged", reason="memory_identity", identities=record_identity(record))
            if len(selected) >= request.result_limit:
                break
        hydration = self._canonical.hydrate(request, tuple(selected))
        hydrated, sources = hydration.records, hydration.sources
        if monotonic() >= deadline:
            raise TimeoutError("hybrid_recall_deadline")
        partial = (len(records) < len(fused)
                   or any(r.receipt.status is not RecallAxisStatus.READY for r in (fts, vector))
                   or any(source.status is not RecallAxisStatus.READY for source in sources))
        return HybridRecallResult(
            request.request_id, request.call_id, request.envelope_hash, request.scope,
            RecallAxisStatus.PARTIAL if partial else RecallAxisStatus.READY,
            hydrated, (fts.receipt, vector.receipt), sources, vector.embedding_usage,
            len(fused), len(fused)-len(records), (monotonic()-started)*1000,
            hydration.validation_snapshot,
        )
