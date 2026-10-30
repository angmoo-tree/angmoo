"""Time-only degradation uses the real adapter/workflow and a denied-network DB."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from chat.test_advisory_person_hints import core, options
from chat.test_named_selection_lifecycle import admission, EmptyHybrid, metadata, fail
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat import test_p8_l_p_evidence_response_streaming as f
from app.config import Settings
from app.domains.chat.contracts.supervisor_selection import SelectionToolCall, parse_control_selection, SELECTION_PROTOCOL_KEY
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.temporal_recall import ChatTimeContext, TEMPORAL_SELECTION_PROTOCOL, TIME_CONTEXT_KEY
from app.domains.chat.schemas import WorldChatRetryCreate
from app.integrations import direct_llm
from app.providers.contracts import ProviderToolCall
from app.runtime.chat.message_composition import generation_service

pytestmark = pytest.mark.usefixtures("deny_external_network")
BAD_TIME = {"kind": "current_day", "expression": "오늘", "unit": "day", "offset": 0}


def parse(args, control="CANONICAL"):
    return parse_control_selection("", (SelectionToolCall("time-call", control, json.dumps(args)),),
        options=replace(options(), temporal_recall=True))


@pytest.mark.parametrize("time_value", [BAD_TIME, [], {"kind": []}, {"kind": "relative", "expression": None},
    {"kind": "relative", "expression": "yesterday", "unit": {}, "offset": -1},
    {"kind": "relative", "expression": None, "unit": "day", "offset": True},
    {"kind": "current_day", "expression": "today", "timezone": "Bad/Region"}])
def test_closed_time_errors_do_not_create_valid_time_values(time_value):
    intent = parse({**core("CANONICAL"), "time_scope": time_value})
    assert intent.time_scope is None
    assert intent.temporal.validation == "invalid"
    assert intent.temporal.validation_code == "time_scope_invalid"
    assert intent.temporal.field_path.startswith("time_scope")


@pytest.mark.parametrize("change", [{"search_text": ""}, {"search_text": "SELECT * FROM secret"},
    {"aggregation": {"kind": "oops", "target_role": "events"}}, {"intent": "unknown"},
    {"activity_kinds": ["fake"]}, {"coordination_hint": "INDEPENDENT_PARALLEL"},
    {"time_scope": {**BAD_TIME, "sql": "SELECT * FROM secret"}},
    {"time_scope": {**BAD_TIME, "expression": "x" * 17000}}])
def test_time_failure_never_hides_core_or_security_failure(change):
    with pytest.raises(RetrievalContractError):
        parse({**core("CANONICAL"), "time_scope": BAD_TIME, **change})


@pytest.mark.parametrize("control,repair,expected_calls,query_origin,resolution", [
    ("CANONICAL", BAD_TIME, 3, "model_search_text", "invalid"),
    ("USE_CONTEXT", BAD_TIME, 3, "original_user_message", "invalid"),
    ("REQUEST_CLARIFICATION", BAD_TIME, 3, "original_user_message", "invalid"),
    ("CANONICAL", {"kind": "current_day", "expression": "today"}, 3, "model_search_text", "resolved"),
    ("CANONICAL", {"kind": "relative", "expression": "sometime"}, 2, "model_search_text", "ambiguous"),
])
def test_real_time_repair_fallback_generates_and_commits_once(response_session, monkeypatch,
    control, repair, expected_calls, query_origin, resolution):
    db = response_session
    owner, accepted, _ = admission(db, monkeypatch, memory=True, question="오늘 무슨 일이 있었어?", protocol=None)
    request_id = accepted.response_request.request_id
    admitted = metadata(db, request_id)
    assert admitted[SELECTION_PROTOCOL_KEY] == TEMPORAL_SELECTION_PROTOCOL
    expected_time = ChatTimeContext.read(admitted[TIME_CONTEXT_KEY])
    calls, hybrid = [], EmptyHybrid()
    async def provider(**kwargs):
        assert not db.in_transaction(), "AI wait must not retain the admission transaction"
        calls.append(kwargs)
        kwargs["tracker"].next_call_order(); kwargs["tracker"].next_provider_call_order()
        payload = json.loads(kwargs["user_prompt"].split("\n", 1)[-1])
        if kwargs.get("tools"):
            assert payload["time_context"] == expected_time.payload()
            time_value = repair if expected_calls == 2 or len(calls) > 1 else BAD_TIME
            args = {**core(control), "time_scope": time_value}
            if control == "REQUEST_CLARIFICATION": args["clarification_slot"] = "time_scope"
            return SimpleNamespace(text="", parsed=None, usage={}, finish_reason="STOP",
                tool_calls=(ProviderToolCall(control, args, "call-" + str(len(calls))),))
        interpretation = payload["recall_interpretation"]
        assert interpretation["revision"] == "hybrid-admission.v4"
        assert interpretation["temporal"]["query_origin"] == query_origin
        assert interpretation["time_resolution"] == resolution
        assert interpretation["retrieval_executed"] is True
        assert "recording time" in kwargs["system_prompt"]
        answer = {"text": "확인한 근거 범위에서 답해요.", "thought": "기억을 살핀다.",
            "situation_description": "사용자가 오늘 일을 물었고 캐릭터는 관련 근거를 확인했다."}
        return direct_llm.DirectLlmResponse(text=json.dumps(answer), parsed=answer, usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", provider)
    asyncio.run(f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread", request_id,
        memory_recall_service=SimpleNamespace(hybrid_service=hybrid),
        runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid"))))
    saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(request_id)
    assert saved.state.value == "committed", saved.node_state
    assert len(calls) == expected_calls and len(hybrid.requests) == 1
    assert (hybrid.requests[0].occurred_from is not None) == (resolution == "resolved")
    assert db.scalar(select(func.count()).select_from(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant")) == 1


def test_explicit_retry_reuses_original_time_and_replay_does_not_rewrite(response_session, monkeypatch):
    db = response_session
    owner, accepted, data = admission(db, monkeypatch, protocol=None)
    original = metadata(db, accepted.response_request.request_id)
    fail(db, accepted.response_request.request_id)
    new = generation_service.retry_world_response(db, owner, "p-world", "p-thread", WorldChatRetryCreate(
        failed_request_id=accepted.response_request.request_id, idempotency_key="temporal-retry-key"))
    assert metadata(db, new.response_request.request_id)[TIME_CONTEXT_KEY] == original[TIME_CONTEXT_KEY]
    replay = generation_service.accept_world_message(db, owner, "p-world", "p-thread", data)
    assert replay.outcome == "replayed"
    assert metadata(db, accepted.response_request.request_id)[TIME_CONTEXT_KEY] == original[TIME_CONTEXT_KEY]


def test_reference_digest_rejects_corrupt_timezone_or_date():
    value = ChatTimeContext.create(datetime(2026, 3, 8, 7, tzinfo=UTC), "America/New_York").payload()
    with pytest.raises(ValueError): ChatTimeContext.read({**value, "local_date": "2026-03-09"})
    with pytest.raises(ValueError): ChatTimeContext.read({**value, "timezone": "Asia/Seoul"})


def test_actual_adapter_counts_physical_attempts_and_marks_invalid_time_meaning(monkeypatch):
    from chat.test_decision_diagnostics import material,recording
    from chat.test_named_retrieval_resolution import identity
    from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider
    from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterRequest
    async def provider(**kwargs):
        kwargs["tracker"].next_call_order()
        kwargs["tracker"].next_provider_call_order();kwargs["tracker"].next_provider_call_order()
        return SimpleNamespace(text="",usage={},finish_reason="STOP",tool_calls=(ProviderToolCall("CANONICAL",{**core("CANONICAL"),"time_scope":BAD_TIME},"call"),))
    monkeypatch.setattr(direct_llm,"generate_text",provider)
    selector=DirectLlmSupervisorSelectionProvider(material(),native_controls=True,code_coordination=True,social_context_mode=True,hybrid_recall=True)
    with recording(True) as observation:
        result=asyncio.run(selector.route(RetrievalRouterRequest(user_message="오늘 기록",chat_identity=identity(),
            selection_protocol=TEMPORAL_SELECTION_PROTOCOL,time_context=ChatTimeContext.create(datetime.now(UTC),"Asia/Seoul"))))
    assert result.physical_attempt_count==2
    assert result.selection_validation["stages"]["meaning"]=="fail"
    assert any(row.get("validation_code")=="time_scope_invalid" for row in observation.details)


@pytest.mark.parametrize("fallback", [False, True])
def test_separate_sqlite_writer_can_commit_during_each_provider_wait(response_session, monkeypatch, tmp_path, fallback):
    import sqlite3
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.domains.chat.service.diagnostic_capture import capture

    path = tmp_path / "chat.sqlite"
    response_session.commit()
    with response_session.get_bind().connect() as source, sqlite3.connect(path) as target:
        source.connection.driver_connection.backup(target)
    engine = create_engine("sqlite:///" + str(path))
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE concurrent_probe (n INTEGER)")
        connection.exec_driver_sql("INSERT INTO concurrent_probe VALUES (0)")
    scope = ("p-owner", "p-world", "p-thread")
    capture.configure(scope, True)
    calls = []

    def independent_write():
        # A different physical connection must commit before the fake AI returns.
        with sqlite3.connect(path, timeout=0.5) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE concurrent_probe SET n = n + 1")

    try:
        with Session(engine) as db:
            owner, accepted, _ = admission(db, monkeypatch, memory=True, protocol=None)
            async def provider(**kwargs):
                assert not db.in_transaction()
                await asyncio.to_thread(independent_write)
                calls.append(kwargs)
                kwargs["tracker"].next_call_order()
                kwargs["tracker"].next_provider_call_order()
                if kwargs.get("tools"):
                    control = "CANONICAL" if fallback else "USE_CONTEXT"
                    arguments = core(control)
                    if fallback:
                        arguments["time_scope"] = BAD_TIME
                    return SimpleNamespace(text="", usage={}, finish_reason="STOP",
                        tool_calls=(ProviderToolCall(control, arguments, "call"),))
                answer = {"text": "확인한 내용이에요.", "thought": "질문을 살핀다.", "situation_description": "질문에 답했다."}
                return direct_llm.DirectLlmResponse(text=json.dumps(answer), parsed=answer, usage={}, finish_reason="STOP")
            monkeypatch.setattr(direct_llm, "generate_text", provider)
            request_id = accepted.response_request.request_id
            asyncio.run(f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread", request_id,
                memory_recall_service=SimpleNamespace(hybrid_service=EmptyHybrid()),
                runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid"))))
            assert f.SqlAlchemyResponseLifecycleRepository(db).get_request(request_id).state.value == "committed"
        assert len(calls) == (3 if fallback else 2)
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT n FROM concurrent_probe").fetchone()[0] == len(calls)
    finally:
        capture.configure(scope, False)
        engine.dispose()


@pytest.mark.parametrize("change", ["world_deleting", "membership_revoked", "character_deleted"])
def test_time_fallback_cannot_commit_after_current_scope_changes(response_session, monkeypatch, change):
    from app.domains.worlds.models_deletion import WorldDeletionRequest
    db = response_session
    owner, accepted, _ = admission(db, monkeypatch, memory=True, protocol=None)
    request_id = accepted.response_request.request_id
    calls = []
    async def provider(**kwargs):
        assert not db.in_transaction()
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        kwargs["tracker"].next_provider_call_order()
        if kwargs.get("tools"):
            return SimpleNamespace(text="", usage={}, finish_reason="STOP",
                tool_calls=(ProviderToolCall("CANONICAL", {**core("CANONICAL"), "time_scope": BAD_TIME}, "call"),))
        # The model has received valid input, but authorization changes before it returns.
        if change == "world_deleting":
            db.add(WorldDeletionRequest(id="deletion", world_id="p-world", owner_id="p-owner",
                idempotency_key="deletion", confirmation_digest="a" * 64))
        elif change == "membership_revoked":
            db.get(f.models.WorldMembership, "p-owner-membership").status = "left"
        else:
            db.get(f.models.Character, "p-responding-character").deleted_at = datetime.now(UTC)
        db.commit()
        answer = {"text": "저장되면 안 되는 늦은 응답", "thought": "기록을 확인했다.", "situation_description": "질문에 답했다."}
        return direct_llm.DirectLlmResponse(text=json.dumps(answer), parsed=answer, usage={}, finish_reason="STOP")
    monkeypatch.setattr(direct_llm, "generate_text", provider)
    async def consume():
        return await f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread", request_id,
            memory_recall_service=SimpleNamespace(hybrid_service=EmptyHybrid()),
            runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid")))
    if change == "world_deleting":
        from app.domains.chat.exceptions import MessageCredentialInvalidError
        with pytest.raises(MessageCredentialInvalidError, match="world_chat_credential_changed"):
            asyncio.run(consume())
    else:
        asyncio.run(consume())
    assert len(calls) == 3
    assert f.SqlAlchemyResponseLifecycleRepository(db).get_request(request_id).state.value != "committed"
    assert db.scalar(select(func.count()).select_from(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant")) == 0
