"""Hybrid semantic uncertainty must not grant access or suppress authorized recall."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute, RetrievalContractError
from app.domains.chat.contracts.retrieval_router import parse_retrieval_intent_payload
from app.domains.chat.contracts.retrieval_policy import RetrievalEntityResolution
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
from app.domains.chat.service.hybrid_canonical import HybridCanonicalService
from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
from app.domains.memory.contracts.hybrid_recall import (
    HybridRecallResult, HybridEmbeddingUsage, RecallAxisReceipt, RecallAxisStatus,
)
from chat.test_p8_l_k_retrieval_router import _FakeRouter, _FakePolicy, _command, _payload, _candidate


def routing(mode=ChatRecallMode.SOCIAL_HYBRID, candidates=(), expression="열이틀 날", world_ambiguous=False):
    intent = replace(parse_retrieval_intent_payload(_payload("CANONICAL", time_expression=expression)),
        search_text="철수와 열이틀 날 싸운 이유", coordination_source="code")
    policy = _FakePolicy((RetrievalEntityResolution("entity-1", candidates),), world_ambiguous=world_ambiguous)
    service = RetrievalRoutingService(router=_FakeRouter(intent), policy=policy, recall_mode=mode)
    now = datetime.now(UTC)
    return asyncio.run(service.route(_command(), now=now, deadline_at=now+timedelta(seconds=60)))


@pytest.mark.parametrize("candidates,status", [
    ((), "unmatched"),
    ((_candidate("first"), _candidate("second")), "multiple"),
    ((_candidate("private", blocked=True),), "unavailable"),
    ((_candidate("inactive", active=False),), "unavailable"),
    ((_candidate("matched"),), "resolved"),
])
@pytest.mark.parametrize("mode", list(ChatRecallMode))
def test_advisory_resolution_preserves_hybrid_search_and_legacy_behavior(mode, candidates, status):
    result = routing(mode, candidates)
    if mode is ChatRecallMode.SOCIAL_HYBRID:
        assert result.intent.route is RetrievalRoute.CANONICAL
        assert result.clarification is None
        assert result.interpretation.mentions[0][2] == status
        assert result.resolved.absolute_time_from is None
        assert result.interpretation.time_expression == "열이틀 날"
        assert result.interpretation.time_status == "ambiguous"
        assert result.intent.search_text == "철수와 열이틀 날 싸운 이유"
        assert "private" not in str(result.interpretation.provider_payload())
    else:
        assert result.intent.route is RetrievalRoute.CLARIFICATION
        assert result.interpretation is None


def test_unknown_world_still_requires_scope_resolution():
    result = routing(world_ambiguous=True)
    assert result.intent.route is RetrievalRoute.CLARIFICATION
    assert result.clarification.slot == "world"


def test_denied_request_never_calls_the_model():
    class Denied(_FakePolicy):
        def load_scope(self, command):
            return replace(super().load_scope(command), blocked=True)
    provider = _FakeRouter()
    service = RetrievalRoutingService(router=provider, policy=Denied(), recall_mode=ChatRecallMode.SOCIAL_HYBRID)
    now = datetime.now(UTC)
    with pytest.raises(RetrievalContractError, match="preflight_policy_denied"):
        asyncio.run(service.route(_command(), now=now, deadline_at=now+timedelta(seconds=60)))
    assert provider.requests == []


@pytest.mark.parametrize("expression,filtered", [("어제", True), ("열이틀 날", False)])
def test_search_receives_fixed_scope_query_and_only_resolved_time_filters(expression, filtered):
    result = routing(expression=expression)
    captured = []
    class Search:
        async def execute(self, request, *, deadline):
            captured.append(request)
            return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash,
                request.scope, RecallAxisStatus.READY, (), tuple(
                    RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 0, 0) for axis in ("fts", "vector")),
                (), HybridEmbeddingUsage(), 0, 0, 0)
    command = SimpleNamespace(intent=result.intent, resolved=result.resolved, call_id="tool-1", call_tracker=result.call_tracker)
    now = datetime.now(UTC)
    execution = asyncio.run(HybridCanonicalService(Search()).plan_and_execute(command, now=now, deadline_at=now+timedelta(seconds=60)))
    request = captured[0]
    assert request.scope.subject_world_character_id == "responding-1"
    assert request.scope.owner_id == "owner-1" and request.scope.world_id == "world-1"
    assert request.counterpart_world_character_id is None
    assert request.search_text == result.intent.search_text
    assert (request.occurred_from is not None) is filtered
    bundle = EvidenceBundleAssembler().canonical(request_scope_hash="c"*64, result=execution)
    frozen = result.interpretation.freeze(bundle)
    frozen.assert_response(_command().user_message, bundle)
    assert bundle.route is RetrievalRoute.CANONICAL
    assert (frozen.time_bounds is not None) is filtered
    with pytest.raises(RetrievalContractError, match="response_mismatch"):
        frozen.assert_response("different question", bundle)
    other = EvidenceBundleAssembler().current_context(request_id="other", request_scope_hash="d"*64)
    with pytest.raises(RetrievalContractError):
        frozen.freeze(other)
    with pytest.raises(RetrievalContractError, match="routing_mismatch"):
        replace(result, interpretation=replace(result.interpretation, resolved_hash="e"*64))
    with pytest.raises(RetrievalContractError, match="routing_mismatch"):
        replace(result, interpretation=replace(result.interpretation, search_text="다른 질문"))
    with pytest.raises(RetrievalContractError, match="mutable_input"):
        replace(result.interpretation, mentions=list(result.interpretation.mentions))


def test_control_outcomes_are_not_forced_to_search():
    now = datetime.now(UTC)
    for route in ("CURRENT_CONTEXT", "CLARIFICATION"):
        provider = _FakeRouter(parse_retrieval_intent_payload(_payload(route)))
        policy = _FakePolicy((RetrievalEntityResolution("entity-1", ()),))
        result = asyncio.run(RetrievalRoutingService(router=provider, policy=policy,
            recall_mode=ChatRecallMode.SOCIAL_HYBRID).route(_command(), now=now, deadline_at=now+timedelta(seconds=60)))
        assert result.intent.route.value == route
        assert result.interpretation.search_text is None
        assert result.call_tracker["logical_total"] == 1

from chat.test_p8_l_p_evidence_response_streaming import response_session


@pytest.mark.parametrize("mode", [*ChatRecallMode, None])
def test_production_composition_native_selection(response_session, monkeypatch, mode):
    import json
    from app.config import Settings
    from app.domains.identity.contracts import CredentialPurpose
    from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
    from app.domains.memory.service.scope import MemoryScopeService
    from app.domains.memory.contracts.scope import MemoryScope
    from app.runtime.memory.composition import memory_repository
    from app.runtime.chat.generation_workflows import build
    from app.providers.contracts import ProviderToolCall
    from chat.test_p8_l_p_evidence_response_streaming import _request, _command as workflow_command, _collect
    from chat.test_supervisor_control_tools import native
    from chat.test_social_context_workflow import SnapshotProvider
    from chat.test_response_supervisor import RecordingExecutor
    from model_fixture_support import models

    db = response_session
    monkeypatch.delenv("CHAT_RECALL_MODE", raising=False)
    monkeypatch.delenv("SNS_SOCIAL_CONTEXT_ENABLED", raising=False)
    runtime_settings = Settings(_env_file=None, **({} if mode is None else {"CHAT_RECALL_MODE": mode.value}))
    if mode is None:
        assert runtime_settings.CHAT_RECALL_MODE == "social_hybrid"
        assert runtime_settings.SNS_SOCIAL_CONTEXT_ENABLED is True
        mode = ChatRecallMode.SOCIAL_HYBRID
    db.get(models.Character, "p-responding-character").owner_id = "p-owner"
    db.get(models.WorldCharacter, "p-responding").membership_id = "p-owner-membership"
    scope = MemoryScope("p-owner", "p-world", "p-responding")
    scopes = MemoryScopeService(memory_repository(db))
    setting = scopes.get_or_create(scope)
    scopes.update(scope, expected_version=setting.version, enabled=True, retention_days=180)
    record = _request(db, RetrievalRoute.CANONICAL)
    db.commit()
    calls, searches = [], []
    class Hybrid:
        async def execute(self, request, *, deadline):
            searches.append(request)
            return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash,
                request.scope, RecallAxisStatus.READY, (), tuple(
                    RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 0, 0) for axis in ("fts", "vector")),
                (), HybridEmbeddingUsage(), 0, 0, 0)
    material = SimpleNamespace(purpose=CredentialPurpose.MESSAGE_LLM, model="gemini-3.1-flash-lite",
        thinking_level="high", provider="google", credential_id="fixture", fingerprint="fixture", reveal=lambda: "fixture")
    query = "철수와 열이틀 날 만나기로 한 약속이 취소됐어?"
    async def provider(**kwargs):
        calls.append(kwargs)
        if kwargs.get("tools"):
            args = native(RetrievalRoute.CANONICAL).arguments()
            args.pop("coordination_hint")
            args["entities"] = [{"ref": "entity-1", "mention": "철수", "role": "counterpart"}]
            args["time_scope"] = {"kind": "relative", "expression": "열이틀 날"}
            if mode is ChatRecallMode.SOCIAL_HYBRID:
                args["search_text"] = query
            return SimpleNamespace(text="", finish_reason="STOP", tool_calls=(ProviderToolCall("CANONICAL", args, "native-hr"),))
        return SimpleNamespace(text="어느 장소에서 만나기로 했던 약속을 말하는 건가요?", finish_reason="STOP", tool_calls=())
    monkeypatch.setattr("app.integrations.direct_llm.generate_text", provider)
    execution = build(db, material, memory_recall_service=SimpleNamespace(hybrid_service=Hybrid()),
        runtime_settings=runtime_settings, lifecycle=SqlAlchemyResponseLifecycleRepository(db), world_id="p-world")
    workflow = execution.workflow
    workflow._social_context_provider = SnapshotProvider()
    observer = RecordingExecutor()
    workflow._graph_executor = observer
    command = workflow_command(record)
    command = replace(command, preflight=replace(command.preflight, user_message=query), character_labels=execution.character_labels)
    events = asyncio.run(_collect(workflow.run(command)))
    stored = workflow._lifecycle.get_request(record.request_id)
    assert stored.state.value == "committed", (events[-1].payload, observer.observation)
    assert len(calls) == 2
    assert stored.call_tracker["logical_total"] == stored.call_tracker["physical_total"] == 2
    payload = json.loads(calls[-1]["user_prompt"].split("\n", 1)[1])
    if mode is ChatRecallMode.SOCIAL_HYBRID:
        assert stored.route is RetrievalRoute.CANONICAL
        assert len(searches) == 1 and searches[0].search_text == query and searches[0].scope == scope
        assert searches[0].occurred_from is None
        assert payload["recall_interpretation"]["time_expression"] == "열이틀 날"
        assert payload["recall_interpretation"]["mentions"][0]["resolution"] == "unmatched"
        assert stored.node_state["recall_interpretation"]["content_hash"]
        assert stored.node_state["final_response_kind"] is None
        assert any(e["event"] == "tool_return" and e["status"] == "completed" for e in observer.observation["events"])
    else:
        assert stored.route is RetrievalRoute.CLARIFICATION
        assert not searches and "recall_interpretation" not in payload
    assert "어느 장소" in db.get(models.MessageMessage, stored.committed_assistant_message_id).content
