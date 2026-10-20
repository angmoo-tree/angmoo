"""v4 time degradation, evidence meaning and execution budgets with synthetic data."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from chat.test_temporal_recall_fallback import parse, core, BAD_TIME
from chat.test_p8_l_k_retrieval_router import _FakePolicy, _command
from chat.test_chat_identity_delivery import request as response_request
from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext, ChatPerson
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute, RetrievalContractError
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterProviderResult, RetrievalRouterOutputError
from app.domains.chat.contracts.temporal_recall import ChatTimeContext, TEMPORAL_SELECTION_PROTOCOL
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.service.hybrid_canonical import HybridCanonicalService
from app.domains.memory.contracts.hybrid_recall import HybridRecallResult, RecallAxisReceipt, RecallAxisStatus, HybridEmbeddingUsage
from app.domains.memory.contracts.recall import CanonicalRecallRecord, RecallDocumentKind
from app.integrations.llm.character_response_generator import _user_payload, _system_prompt

pytestmark = pytest.mark.usefixtures("deny_external_network")
NOW = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)
IDENTITY = ChatIdentityContext("owner-1", "world-1", "thread-1", ChatPerson("requester-1", "사용자"), ChatPerson("responding-1", "Bram"))


class Router:
    def __init__(self, *items): self.items, self.requests = list(items), []
    async def route(self, request):
        self.requests.append(request)
        item = self.items.pop(0)
        if isinstance(item, Exception): raise item
        return RetrievalRouterProviderResult(item, "fixture", "fixture", 1, argument_protocol=TEMPORAL_SELECTION_PROTOCOL)


def routing(*items, policy=None, reference=NOW, today=None, question="What happened today?"):
    router = Router(*items)
    service = RetrievalRoutingService(router=router, policy=policy or _FakePolicy(), recall_mode=ChatRecallMode.SOCIAL_HYBRID)
    command = replace(_command(), user_message=question)
    result = asyncio.run(service.route(command, now=NOW+timedelta(days=1), deadline_at=NOW+timedelta(days=1, seconds=60),
        chat_identity=IDENTITY, selection_protocol=TEMPORAL_SELECTION_PROTOCOL,
        time_context=ChatTimeContext.create(reference, "Asia/Seoul"), today_sns_context=today))
    return result, router, command


@pytest.mark.parametrize("control,slot", [("USE_CONTEXT", None), ("REQUEST_CLARIFICATION", "counterpart")])
def test_unrequested_time_and_other_clarification_do_not_trigger_recall(control, slot):
    args = {**core(control), "time_scope": BAD_TIME if slot else None}
    if slot: args["clarification_slot"] = slot
    intent = parse(args, control)
    result, router, _ = routing(intent, intent)
    assert result.intent.route is (RetrievalRoute.CLARIFICATION if slot else RetrievalRoute.CURRENT_CONTEXT)
    assert result.intent.search_text is None and result.resolved.canonical_operation_allowlist == ()
    assert len(router.requests) == (2 if slot else 1)


@pytest.mark.parametrize("failure", [RetrievalRouterOutputError("aggregation_invalid", physical_attempt_count=1),
    RuntimeError("transport unavailable"), TimeoutError("provider deadline")])
def test_repair_core_failure_transport_and_deadline_never_reuse_first_candidate(failure):
    invalid = parse({**core("CANONICAL"), "time_scope": BAD_TIME})
    with pytest.raises(Exception): routing(invalid, failure)


@pytest.mark.parametrize("time,reference,start,end", [
    ({"kind":"current_day", "expression":"오늘"}, datetime(2026,10,16,15,tzinfo=UTC), "2026-10-16T15:00:00Z", "2026-10-16T15:00:00Z"),
    ({"kind":"relative", "expression":None, "unit":"month", "offset":-1}, datetime(2026,3,1,tzinfo=UTC), "2026-01-31T15:00:00Z", "2026-02-28T15:00:00Z"),
    ({"kind":"relative", "expression":"yesterday", "unit":"day", "offset":-1,"timezone":"America/New_York"}, datetime(2026,3,9,5,tzinfo=UTC), "2026-03-08T05:00:00Z", "2026-03-09T04:00:00Z"),
])
def test_fixed_time_boundaries_ignore_execution_day(time, reference, start, end):
    result, _, _ = routing(parse({**core("CANONICAL"), "time_scope": time}), reference=reference)
    assert (result.resolved.absolute_time_from, result.resolved.absolute_time_to) == (start, end)
    assert result.interpretation.temporal.context.instant == reference


def test_today_guard_keeps_context_or_uses_code_query_without_false_time_fallback():
    args = {**core("CANONICAL"), "intent":"today_sns_activity", "activity_kinds":["posts_authored"], "time_scope":{"kind":"current_day","expression":"today"}}
    # Use an existing registered intent; activity_kinds expresses the requested surface.
    args["intent"] = core("CANONICAL")["intent"]
    complete = {"entries":[], "counts":{"posts_authored":0}, "coverage":{"posts_authored":"complete"}}
    result, _, _ = routing(parse(args), today=complete, question="today posts")
    assert result.intent.route is RetrievalRoute.CURRENT_CONTEXT and result.intent.search_text is None
    use = {**core("USE_CONTEXT"), "activity_kinds":["posts_authored"], "time_scope":args["time_scope"]}
    result, _, command = routing(parse(use, "USE_CONTEXT"), question="today posts")
    assert result.intent.route is RetrievalRoute.CANONICAL and result.intent.search_text == command.user_message
    assert result.intent.temporal.query_origin == "original_user_message"
    invalid = parse({**args, "time_scope":BAD_TIME})
    result, _, _ = routing(invalid, invalid, today=complete, question="today posts")
    assert result.intent.route is RetrievalRoute.CANONICAL and result.intent.temporal.resolution == "invalid"


class Search:
    def __init__(self, records): self.records, self.requests = records, []
    async def execute(self, request, *, deadline):
        self.requests.append(request)
        rows = tuple(row for row in self.records if (request.occurred_from is None or row.occurred_at >= request.occurred_from)
            and (request.occurred_to is None or row.occurred_at <= request.occurred_to))
        return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash, request.scope,
            RecallAxisStatus.READY, rows, tuple(RecallAxisReceipt(axis, RecallAxisStatus.READY, True, len(rows), 1) for axis in ("fts","vector")),
            (), HybridEmbeddingUsage(), len(rows), 0, 1)


@pytest.mark.parametrize("enabled", [True, False])
def test_fallback_records_keep_event_interval_recording_unknown_and_memory_opt_out(enabled):
    class Policy(_FakePolicy):
        def load_scope(self, command): return replace(super().load_scope(command), memory_enabled=enabled)
    invalid = parse({**core("CANONICAL"), "time_scope":BAD_TIME})
    result, _, command = routing(invalid, invalid, policy=Policy())
    rows = (
        CanonicalRecallRecord("old", RecallDocumentKind.POST, "old", "Yesterday event", NOW-timedelta(days=1)),
        CanonicalRecallRecord("today", RecallDocumentKind.POST, "today", "Today event", NOW),
        CanonicalRecallRecord("recording", RecallDocumentKind.MEMORY_ITEM, "recording", "Later summary", NOW, memory_item_id="recording",
            metadata={"recorded_at": NOW.isoformat()}),
        CanonicalRecallRecord("unknown", RecallDocumentKind.MEMORY_ITEM, "unknown", "Unknown event time", NOW, memory_item_id="unknown",
            metadata={"episode_packet":"v1", "recorded_at":NOW.isoformat()}),
    )
    search = Search(rows)
    # Event-time fixtures remain fixed; the execution deadline uses the live
    # clock so this test also exercises the real response-generation reserve.
    execution_deadline = datetime.now(UTC) + timedelta(seconds=60)
    execution = asyncio.run(HybridCanonicalService(search).plan_and_execute(SimpleNamespace(intent=result.intent,
        resolved=result.resolved, call_id="tool-1", call_tracker=result.call_tracker), now=NOW, deadline_at=execution_deadline))
    bundle = EvidenceBundleAssembler().canonical(request_scope_hash="c"*64, result=execution).with_temporal_evidence()
    interpretation = replace(result.interpretation.freeze(bundle), retrieval_executed=any(axis.executed for axis in execution.recall.axes))
    item = replace(response_request(raw=command.user_message, participants=IDENTITY, bundle=bundle),
        recall_mode=ChatRecallMode.SOCIAL_HYBRID, recall_interpretation=interpretation)
    view = _user_payload(item)
    assert view["recall_interpretation"]["retrieval_executed"] is enabled
    assert len(search.requests) == int(enabled)
    if enabled:
        assert search.requests[0].occurred_from is None and search.requests[0].result_limit <= 20
        assert search.requests[0].scope.owner_id == "owner-1" and search.requests[0].scope.subject_world_character_id == "responding-1"
        times = {entry.text: entry.time_provenance for entry in bundle.items}
        assert times["Yesterday event"][1] == (NOW-timedelta(days=1)).isoformat()
        assert times["Today event"][1] == NOW.isoformat()
        assert times["Later summary"][0] == "recorded"
        assert times["Unknown event time"] == ("unknown", None, None, NOW.isoformat())
    assert "recording time" in _system_prompt(item)
    for damage in (replace(interpretation.temporal, context=ChatTimeContext.create(NOW-timedelta(days=1),"Asia/Seoul")),
                   replace(interpretation.temporal, query_origin="original_user_message")):
        with pytest.raises(RetrievalContractError): replace(interpretation, temporal=damage).assert_routing(result.intent,result.resolved)
    with pytest.raises(RetrievalContractError): interpretation.assert_response("Different question", bundle)


def test_evidence_time_interval_hash_changes_only_for_v4():
    from app.domains.chat.contracts.evidence_bundle import EvidenceBundle, EvidenceItem, EvidenceKind
    from app.domains.chat.contracts.response_request import RetrievalAxis, RetrievalOutcome
    old = EvidenceBundleAssembler()._bundle(request_id="r", request_scope_hash="a"*64,
        route=RetrievalRoute.CANONICAL, outcome=RetrievalOutcome.MEMORY_USED,
        candidates=(EvidenceItem("e", EvidenceKind.EPISODE_MEMORY, "Two-day source", NOW, (RetrievalAxis.CANONICAL,)),))
    item = replace(old.items[0], prepared_times=("interval", (NOW-timedelta(days=1)).isoformat(), NOW.isoformat(), (NOW+timedelta(days=1)).isoformat()))
    prepared = replace(old, items=(item,))
    assert prepared.evidence_hash == old.evidence_hash and "time_provenance" not in old.provider_payload()["items"][0]
    bound = prepared.with_temporal_evidence()
    assert bound.evidence_hash != old.evidence_hash
    assert bound.provider_payload()["items"][0]["time_provenance"]["kind"] == "interval"
    with pytest.raises(ValueError): replace(bound, items=(replace(bound.items[0], time_provenance=("unknown",None,None,None)),))


def test_generic_memory_validity_time_is_not_mislabeled_and_source_time_stays_event():
    from app.domains.chat.service.evidence_assembly import _record_times
    memory = CanonicalRecallRecord("memory", RecallDocumentKind.MEMORY_ITEM, "memory", "fixture", NOW,
        memory_item_id="memory")
    assert _record_times(memory) == ("unknown", None, None, None)
    source = CanonicalRecallRecord("post", RecallDocumentKind.POST, "post", "fixture", NOW,
        memory_item_id="memory")
    assert _record_times(source) == ("event", NOW.isoformat(), None, None)
    interval = replace(memory, metadata={"event_time_from": (NOW-timedelta(days=1)).isoformat(),
        "event_time_to": NOW.isoformat(), "recorded_at": (NOW+timedelta(days=1)).isoformat()})
    assert _record_times(interval) == ("interval", (NOW-timedelta(days=1)).isoformat(), NOW.isoformat(),
        (NOW+timedelta(days=1)).isoformat())


def test_valid_date_empty_result_does_not_expand_or_retry_search():
    intent = parse({**core("CANONICAL"), "time_scope": {"kind": "current_day", "expression": "today"}})
    result, router, _ = routing(intent)
    search = Search((CanonicalRecallRecord("old", RecallDocumentKind.POST, "old", "Yesterday", NOW-timedelta(days=1)),))
    execution_deadline = datetime.now(UTC) + timedelta(seconds=60)
    execution = asyncio.run(HybridCanonicalService(search).plan_and_execute(SimpleNamespace(intent=result.intent,
        resolved=result.resolved, call_id="empty", call_tracker=result.call_tracker), now=NOW, deadline_at=execution_deadline))
    assert execution.recall.records == ()
    assert len(router.requests) == len(search.requests) == 1
    assert search.requests[0].occurred_from is not None and search.requests[0].occurred_to is not None
    assert result.interpretation.temporal.resolution == "resolved"


def test_invalid_admitted_timezone_is_not_a_model_time_fallback():
    from zoneinfo import ZoneInfoNotFoundError
    with pytest.raises(ZoneInfoNotFoundError):
        ChatTimeContext.create(NOW, "Invalid/Region")
