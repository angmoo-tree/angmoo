import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic
from types import SimpleNamespace

import pytest

from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.domains.chat.service.hybrid_canonical import HybridCanonicalService
from app.domains.memory.contracts.hybrid_recall import HybridRecallResult, HybridEmbeddingUsage, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.contracts.recall import RecallDocumentKind


def command(*, operations=("search_memory_items",), aggregation=None, enabled=True):
    intent = SimpleNamespace(route=RetrievalRoute.CANONICAL, envelope_hash="a"*64,
        search_text="훈련 약속", aggregation=aggregation)
    resolved = SimpleNamespace(intent_hash=intent.envelope_hash, envelope_hash="b"*64,
        owner_id="owner", world_id="world", responding_world_character_id="subject",
        request_id="request", canonical_operation_allowlist=operations,
        memory_enabled=enabled, absolute_time_from=None, absolute_time_to=None,
        caps=SimpleNamespace(row_limit=20, timeout_ms=4000))
    return SimpleNamespace(intent=intent, resolved=resolved, call_id="call", call_tracker={})


@pytest.mark.parametrize("operations,aggregation,enabled,reason", [
    ((), None, True, "canonical_operations_unavailable"),
    (("read_source",), None, True, "canonical_operations_unavailable"),
    (("search_memory_items",), "count", True, "hybrid_aggregation_unsupported"),
    (("search_memory_items",), None, False, "memory_opt_out"),
])
def test_unsupported_or_opted_out_requests_never_search_or_embed(operations, aggregation, enabled, reason):
    now = datetime.now(UTC)
    result = asyncio.run(HybridCanonicalService(None).plan_and_execute(
        command(operations=operations, aggregation=aggregation, enabled=enabled),
        now=now, deadline_at=now+timedelta(seconds=60)))
    assert all(not axis.executed and axis.reason_code == reason for axis in result.recall.axes)
    assert result.recall.embedding_usage.logical_calls == 0
    assert result.metrics.planner_logical_calls == 0
    from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
    from app.domains.chat.contracts.evidence_bundle import RetrievalOutcome
    bundle = EvidenceBundleAssembler().canonical(request_scope_hash="c"*64, result=result)
    assert bundle.retrieval_outcome is (RetrievalOutcome.MEMORY_OFF if not enabled else RetrievalOutcome.DEGRADED)


def test_allowed_document_kinds_and_resolved_deadline_reach_actual_search_port():
    class Hybrid:
        async def execute(self, request, *, deadline):
            assert request.kinds == (RecallDocumentKind.MEMORY_ITEM,)
            assert 0 < deadline-monotonic() <= 4.0
            return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash,
                request.scope, RecallAxisStatus.READY, (), tuple(
                    RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 0, 0) for axis in ("fts", "vector")),
                (), HybridEmbeddingUsage(), 0, 0, 0)
    now = datetime.now(UTC)
    asyncio.run(HybridCanonicalService(Hybrid()).plan_and_execute(command(), now=now,
        deadline_at=now+timedelta(seconds=60)))
