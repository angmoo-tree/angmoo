"""Compose independent native reads with a measured, cancellable query embedding."""
import asyncio
from time import monotonic
from dataclasses import replace
from app.contracts.retrieval_observation import observe
from app.domains.memory.contracts.hybrid_recall import (
    HybridAxisResult, HybridEmbeddingUsage, RankedMemoryCandidate, RecallAxisReceipt, RecallAxisStatus,
)
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.contracts.vector_projection import MemoryVectorQuery


class FtsHybridAxis:
    def __init__(self, workers): self._workers = workers

    async def search(self, request, *, deadline):
        started = monotonic()
        try:
            result, observation = await self._workers.search(MemoryRecallSearchQuery(request.scope, request.search_text,
                request.kinds, request.axis_limit, request.counterpart_world_character_id, request.thread_id,
                korean_spacing_fallback=True, occurred_from=request.occurred_from,
                occurred_to=request.occurred_to), deadline=deadline)
            for event in observation.get("events", ()):
                observe(event["event"], **{key: value for key, value in event.items() if key != "event"})
            return replace(result, receipt=replace(result.receipt, duration_ms=(monotonic()-started)*1000))
        except asyncio.CancelledError:
            raise
        except Exception:
            return HybridAxisResult((), RecallAxisReceipt("fts", RecallAxisStatus.UNAVAILABLE, True, 0,
                (monotonic()-started)*1000, "memory_fts_unavailable"))


class VectorHybridAxis:
    def __init__(self, workers, embedder):
        self._workers, self._embedder = workers, embedder

    async def search(self, request, *, deadline):
        started = monotonic()
        usage = HybridEmbeddingUsage()
        executed = False
        try:
            response = await self._embedder.query(request, deadline=deadline)
            if response is None:
                return HybridAxisResult((), RecallAxisReceipt("vector", RecallAxisStatus.DISABLED, False, 0,
                    (monotonic()-started)*1000, "memory_embedding_disabled"))
            usage = HybridEmbeddingUsage(1, response.physical_attempts, response.usage.input_tokens, response.usage.duration_ms)
            executed = True
            result = await self._workers.search(MemoryVectorQuery(request.scope, request.profile, response.vector,
                request.axis_limit, request.occurred_from, request.occurred_to,
                request.counterpart_world_character_id, request.thread_id), deadline=deadline)
            rows = tuple(RankedMemoryCandidate(MemoryRecallCandidate(hit.document_id, hit.memory_item_id,
                RecallDocumentKind.MEMORY_ITEM, hit.memory_item_id, -hit.distance, ""), hit.version, hit.content_hash)
                for hit in result.hits)
            return HybridAxisResult(rows, RecallAxisReceipt("vector", RecallAxisStatus.READY, True, len(rows),
                (monotonic()-started)*1000, generation=result.generation), usage)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if usage.logical_calls == 0 and getattr(exc, "physical_attempts", None) is not None:
                usage = HybridEmbeddingUsage(1, exc.physical_attempts, getattr(exc, "input_tokens", None), getattr(exc, "duration_ms", None))
            return HybridAxisResult((), RecallAxisReceipt("vector", RecallAxisStatus.UNAVAILABLE, executed, 0,
                (monotonic()-started)*1000, "memory_vector_unavailable"), usage)
