import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic
from types import SimpleNamespace

import pytest

from app.domains.chat.contracts.retrieval_intent import (
    RetrievalAggregationKind, RetrievalAggregationMeaning, RetrievalDecision,
    RetrievalIntentEnvelope, RetrievalRoute, RetrievalContractError,
)
from app.domains.chat.contracts.resolved_envelope import RetrievalHardCaps
from app.domains.chat.service.hybrid_canonical import HybridCanonicalService
from app.domains.memory.contracts.hybrid_recall import HybridRecallResult, HybridEmbeddingUsage, RecallAxisReceipt, RecallAxisStatus
from app.domains.memory.contracts.recall import RecallDocumentKind


def command(*, operations=("search_memory_items",), aggregation=None, enabled=True, timeout_ms=4000):
    intent = RetrievalIntentEnvelope(decision=RetrievalDecision.RETRIEVAL,
        route=RetrievalRoute.CANONICAL, intent="search_memory", search_text="훈련 약속",
        aggregation=RetrievalAggregationMeaning(RetrievalAggregationKind(aggregation), "memory")
        if aggregation is not None else None)
    resolved = SimpleNamespace(intent_hash=intent.envelope_hash, envelope_hash="b"*64,
        owner_id="owner", world_id="world", responding_world_character_id="subject",
        request_id="request", canonical_operation_allowlist=operations,
        memory_enabled=enabled, absolute_time_from=None, absolute_time_to=None,
        caps=RetrievalHardCaps(timeout_ms=timeout_ms))
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


@pytest.mark.parametrize("timeout_ms,remaining_seconds,expected_seconds", [
    (10000, 60, 10), (2000, 60, 2), (4000, 60, 4), (10000, 18, 3), (30000, 60, 20),
])
def test_search_honors_caller_cap_request_reserve_and_absolute_ceiling(
    monkeypatch, timeout_ms, remaining_seconds, expected_seconds,
):
    monkeypatch.setattr("app.domains.chat.service.hybrid_canonical.monotonic", lambda: 1000.0)
    received = []
    class Hybrid:
        async def execute(self, request, *, deadline):
            received.append((request, deadline))
            return empty_result(request)
    now = datetime.now(UTC)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr("app.domains.chat.service.hybrid_canonical.datetime", Clock)
    asyncio.run(HybridCanonicalService(Hybrid()).plan_and_execute(
        command(timeout_ms=timeout_ms), now=now, deadline_at=now+timedelta(seconds=remaining_seconds)))
    assert len(received) == 1
    request, deadline = received[0]
    assert deadline == 1000.0 + expected_seconds
    assert request.result_limit == 20 and request.search_text == "훈련 약속"


@pytest.mark.parametrize("remaining_seconds", [15, 14, 0])
def test_exhausted_response_reserve_never_starts_search_or_embedding(remaining_seconds):
    class NoSearch:
        async def execute(self, *_args, **_kwargs):
            pytest.fail("request reserve must be checked before search or embedding")
    now = datetime.now(UTC)
    with pytest.raises(RetrievalContractError, match="hybrid_crg_reserve_exhausted"):
        asyncio.run(HybridCanonicalService(NoSearch()).plan_and_execute(
            command(timeout_ms=10000), now=now, deadline_at=now+timedelta(seconds=remaining_seconds)))


@pytest.mark.parametrize("timeout_ms,work_seconds,succeeds", [
    (4000, 5.5, False), (10000, 5.5, True), (10000, 0.025, True), (10000, 10.5, False),
])
def test_completed_work_returns_without_waiting_out_budget_or_restarting_search(
    monkeypatch, timeout_ms, work_seconds, succeeds,
):
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr("app.domains.chat.service.hybrid_canonical.monotonic", lambda: clock.now)
    calls = []
    class Hybrid:
        async def execute(self, request, *, deadline):
            calls.append(request)
            clock.now += work_seconds
            if clock.now >= deadline:
                raise TimeoutError("canonical_read_deadline")
            return empty_result(request)
    now = datetime.now(UTC)
    async def run():
        return await asyncio.wait_for(HybridCanonicalService(Hybrid()).plan_and_execute(
            command(timeout_ms=timeout_ms), now=now, deadline_at=now+timedelta(seconds=60)), timeout=1)
    if succeeds:
        result = asyncio.run(run())
        assert result.recall.status is RecallAxisStatus.READY
        assert result.metrics.planner_logical_calls == 0
    else:
        with pytest.raises(RetrievalContractError, match="hybrid_retrieval_timeout"):
            asyncio.run(run())
    assert len(calls) == 1 and clock.now == 1000.0 + work_seconds


@pytest.mark.parametrize("remaining_seconds,expected_seconds", [(60, 4), (2, 2)])
def test_delivery_currentness_keeps_its_separate_four_second_budget(
    monkeypatch, remaining_seconds, expected_seconds,
):
    from app.domains.chat.service.hybrid_canonical import _CurrentMemoryEvidence
    from app.domains.chat.contracts.evidence_bundle import EvidenceLocatorKind
    now = datetime.now(UTC)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr("app.domains.chat.service.hybrid_canonical.datetime", Clock)
    monkeypatch.setattr("app.domains.chat.service.hybrid_canonical.monotonic", lambda: 1000.0)
    calls, result = [], object()
    class Currentness:
        async def assert_current(self, prior, ids, *, deadline):
            calls.append((prior, ids, deadline))
    item = SimpleNamespace(locator=SimpleNamespace(kind=EvidenceLocatorKind.MEMORY_ITEM, source_id="memory-1"))
    guard = _CurrentMemoryEvidence(Currentness(), result)
    asyncio.run(guard.assert_current(SimpleNamespace(items=(item, item)),
        deadline_at=now+timedelta(seconds=remaining_seconds)))
    assert calls == [(result, ("memory-1",), 1000.0+expected_seconds)]


def empty_result(request):
    return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash,
        request.scope, RecallAxisStatus.READY, (), tuple(
            RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 0, 0) for axis in ("fts", "vector")),
        (), HybridEmbeddingUsage(), 0, 0, 0)
