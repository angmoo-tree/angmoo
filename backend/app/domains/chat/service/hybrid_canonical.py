"""Canonical ToolNode execution without a specialist Planner or fabricated plan."""
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from app.contracts.retrieval_observation import observe

from app.domains.chat.contracts.retrieval_intent import RetrievalContractError, RetrievalRoute
from app.domains.chat.service.canonical_retrieval import CanonicalPlanningMetrics
from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest, HybridRecallResult, RecallAxisReceipt, RecallAxisStatus, HybridEmbeddingUsage
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope

_SEARCH_KINDS = {
    "search_thread_messages": (RecallDocumentKind.THREAD_MESSAGE, RecallDocumentKind.OWNER_MEMORY_REQUEST),
    "search_posts": (RecallDocumentKind.POST, RecallDocumentKind.REPLY),
    "search_memory_items": (RecallDocumentKind.MEMORY_ITEM,),
    "list_social_events": (RecallDocumentKind.SOCIAL_EVENT, RecallDocumentKind.REACTION),
    "list_activity_episodes": (RecallDocumentKind.ACTIVITY_EVENT, RecallDocumentKind.JOINT_COMMITMENT),
    "list_relationship_changes": (RecallDocumentKind.RELATIONSHIP_EVENT,),
}


@dataclass(frozen=True, slots=True)
class HybridCanonicalResult:
    request_id: str
    recall: HybridRecallResult
    metrics: CanonicalPlanningMetrics
    call_tracker: dict


class HybridCanonicalService:
    def __init__(self, hybrid): self._hybrid = hybrid

    async def plan_and_execute(self, command, *, now, deadline_at):
        resolved = command.resolved
        if (command.intent.route is not RetrievalRoute.CANONICAL
            or resolved.intent_hash != command.intent.envelope_hash or not command.call_id
            or not command.intent.search_text):
            raise RetrievalContractError("hybrid_canonical_command_invalid")
        scope = MemoryScope(resolved.owner_id, resolved.world_id, resolved.responding_world_character_id)
        kinds = tuple(dict.fromkeys(kind for operation in resolved.canonical_operation_allowlist
                                   for kind in _SEARCH_KINDS.get(operation, ())))
        short_reason = "memory_opt_out" if not resolved.memory_enabled else (
            "canonical_operations_unavailable" if not kinds else (
                "hybrid_aggregation_unsupported" if command.intent.aggregation is not None else None))
        if short_reason:
            result = HybridRecallResult(resolved.request_id, command.call_id, resolved.envelope_hash, scope,
                RecallAxisStatus.DISABLED, (), tuple(RecallAxisReceipt(axis, RecallAxisStatus.DISABLED, False, 0, 0, short_reason)
                for axis in ("fts", "vector")), (), HybridEmbeddingUsage(), 0, 0, 0)
        else:
            remaining = (deadline_at-now).total_seconds()-15.0
            if remaining <= 0:
                raise RetrievalContractError("hybrid_crg_reserve_exhausted")
            request = HybridRecallRequest(resolved.request_id, command.call_id, resolved.envelope_hash, scope,
                command.intent.search_text, EMBEDDING_PROFILE, kinds,
                None if resolved.absolute_time_from is None else datetime.fromisoformat(resolved.absolute_time_from),
                None if resolved.absolute_time_to is None else datetime.fromisoformat(resolved.absolute_time_to),
                result_limit=min(20, resolved.caps.row_limit))
            result = await self._hybrid.execute(request, deadline=monotonic()+min(20.0, remaining, resolved.caps.timeout_ms / 1000))
        for axis in result.axes:
            observe("hybrid_axis", axis=axis.axis, status=axis.status.value, executed=axis.executed,
                returned=axis.candidate_count, elapsed_ms=axis.duration_ms, reason=axis.reason_code,
                physical_count_complete=axis.physical_scan_count is not None, scanned=axis.physical_scan_count)
        observe("hybrid_embedding", logical_calls=result.embedding_usage.logical_calls,
            physical_attempts=result.embedding_usage.physical_attempts, input_tokens=result.embedding_usage.input_tokens,
            physical_count_complete=result.embedding_usage.physical_attempts is not None,
            elapsed_ms=result.embedding_usage.duration_ms)
        observe("hybrid_fusion", method="rrf_k60", candidates=result.fused_count, excluded=result.excluded_count,
                returned=len(result.records), status=result.status.value, elapsed_ms=result.duration_ms)
        return HybridCanonicalResult(resolved.request_id, result,
            CanonicalPlanningMetrics(True, False, bool(short_reason), short_reason, 0, 0, 0, 0,
                len(result.records), None, None, latency_ms=int(result.duration_ms)), dict(command.call_tracker))
