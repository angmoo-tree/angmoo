"""Compose independent native reads with a measured, cancellable query embedding."""
import asyncio
from time import monotonic
from app.contracts.search_diagnostics import collector, SearchTerminal
from app.runtime.memory.worker_diagnostics import WorkerTrace
from dataclasses import replace
from app.contracts.retrieval_observation import observe, detail, current
from app.domains.memory.contracts.fts_recall import FtsWorkerRequest
from app.domains.memory.contracts.recall import MemoryRecallLexicalPolicy
from app.domains.memory.contracts.hybrid_recall import (
    HybridAxisResult, HybridEmbeddingUsage, RankedMemoryCandidate, RecallAxisReceipt, RecallAxisStatus,
)
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.contracts.vector_projection import MemoryVectorQuery


class FtsHybridAxis:
    def __init__(self, workers, *, lexical_policy=MemoryRecallLexicalPolicy.LEGACY_STRICT_V1):
        self._workers = workers
        self._policy = MemoryRecallLexicalPolicy(lexical_policy)

    async def search(self, request, *, deadline):
        started = monotonic()
        axis_status = "unavailable"
        try:
            parent = current.get()
            result, observation = await self._workers.search(FtsWorkerRequest(MemoryRecallSearchQuery(request.scope, request.search_text,
                request.kinds, request.axis_limit, request.counterpart_world_character_id, request.thread_id,
                korean_spacing_fallback=True, occurred_from=request.occurred_from,
                occurred_to=request.occurred_to, lexical_policy=self._policy), capture_details=bool(parent and parent.detailed)), deadline=deadline)
            try:
                for event in observation.get("events", ()):
                    observe(event["event"], **{key: value for key, value in event.items() if key != "event"})
                if parent is not None and parent.detailed:
                    for row in observation.get("details", ())[:24]:
                        if isinstance(row, dict):
                            detail(**row)
                    parent.detail_omitted += min(1000, max(0, int(observation.get("detail_omitted", 0))))
            except (TypeError, ValueError, KeyError):
                if parent is not None:
                    parent.omitted += 1
            axis_status = result.receipt.status.value
            return replace(result, receipt=replace(result.receipt, duration_ms=(monotonic()-started)*1000))
        except asyncio.CancelledError:
            axis_status = "cancelled"
            raise
        except Exception:
            return HybridAxisResult((), RecallAxisReceipt("fts", RecallAxisStatus.UNAVAILABLE, True, 0,
                (monotonic()-started)*1000, "memory_fts_unavailable"))
        finally:
            target = collector()
            if target is not None and "fts" in target.terminals:
                target.terminals["fts"] = target.terminals["fts"].model_copy(update={"axis_status": axis_status})


class VectorHybridAxis:
    def __init__(self, workers, embedder):
        self._workers, self._embedder = workers, embedder

    async def search(self, request, *, deadline):
        started = monotonic()
        usage = HybridEmbeddingUsage()
        executed = False
        axis_status = "unavailable"
        target = collector()
        embedding_trace = WorkerTrace("vector", deadline, domain="parent", detailed=target is not None)
        if current.get() is not None:
            embedding_trace.started = current.get().started
        try:
            with embedding_trace.phase("embedding"):
                response = await self._embedder.query(request, deadline=deadline)
            if response is None:
                axis_status = "disabled"
                if target is not None:
                    target.terminals["vector"] = SearchTerminal(axis="vector", terminal_state="disabled", terminal_observed=True)
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
            axis_status = "ready"
            return HybridAxisResult(rows, RecallAxisReceipt("vector", RecallAxisStatus.READY, True, len(rows),
                (monotonic()-started)*1000, generation=result.generation), usage)
        except asyncio.CancelledError:
            axis_status = "cancelled"
            raise
        except Exception as exc:
            if usage.logical_calls == 0 and getattr(exc, "physical_attempts", None) is not None:
                usage = HybridEmbeddingUsage(1, exc.physical_attempts, getattr(exc, "input_tokens", None), getattr(exc, "duration_ms", None))
            return HybridAxisResult((), RecallAxisReceipt("vector", RecallAxisStatus.UNAVAILABLE, executed, 0,
                (monotonic()-started)*1000, "memory_vector_unavailable"), usage)
        finally:
            if target is not None:
                for stage in embedding_trace.stages.values():
                    target.add_stage(stage)
                if "vector" not in target.terminals and embedding_trace.error is not None:
                    target.terminals["vector"] = SearchTerminal(axis="vector", terminal_state="error",
                        failure=embedding_trace.error, last_observed_stage="embedding", cause_certainty="reported", terminal_observed=True)
                if "vector" in target.terminals:
                    target.terminals["vector"] = target.terminals["vector"].model_copy(update={"axis_status": axis_status})
