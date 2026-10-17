"""Capture ownership, generation invalidation, and real admission/final commit."""
import asyncio
import pytest
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from app.domains.chat.service.diagnostic_capture import DiagnosticCapture, capture
from app.domains.chat.contracts.db_write_diagnostics import DbWriteCollector
from chat.test_db_write_diagnostics import feed
from chat.test_temporal_recall_fallback import core, BAD_TIME
from chat.test_named_selection_lifecycle import admission, EmptyHybrid
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat import test_p8_l_p_evidence_response_streaming as f
from app.integrations import direct_llm
from app.providers.contracts import ProviderToolCall
from app.runtime.chat.message_composition import generation_service
from app.config import Settings


def test_old_callbacks_cannot_join_reenabled_capture_and_scope_isolation():
    owner = DiagnosticCapture()
    scope, other = ("u", "w", "t"), ("u", "other", "t")
    owner.configure(scope, True); generation = owner.generation(scope)
    collector = DbWriteCollector()
    owner.admit(scope, "r"); owner.bind_db(scope, "r", generation, collector, 2)
    owner.store(scope, "r", [])
    assert owner.read_full(other, "r") is None
    assert owner.read_full(scope, "r")["db_write"]["attempt_number"] == 2
    owner.configure(scope, False); owner.configure(scope, True)
    assert not owner.generation_active(scope, generation)
    assert owner.db_collector(scope, "r") is None
    assert DiagnosticCapture().generation(scope) is None
    current = owner.generation(scope)
    owner._enabled[scope].until = datetime.now(UTC) - timedelta(seconds=1)
    assert not owner.generation_active(scope, current)


def test_quota_last_request_still_captures_and_export_shares_budget():
    owner = DiagnosticCapture(); scope = ("u", "w", "t")
    owner.configure(scope, True); generation = owner.generation(scope)
    for n in range(10): owner.admit(scope, str(n))
    assert owner.active(scope, "9") and not owner.status(scope)["enabled"]
    collector = DbWriteCollector(); owner.bind_db(scope, "9", generation, collector, 1)
    for n in range(70):
        feed(collector, "write_started", 0, span=str(n), event="session_write")
        feed(collector, "committed", 2, span=str(n), event="session_write")
    owner.store(scope, "9", [{"search_text": "x" * 3000} for _ in range(24)])
    exported = owner.read_full(scope, "9")
    assert len(json.dumps(exported, ensure_ascii=True).encode()) <= 64 * 1024
    assert exported["db_write"]["omitted_attempts"] == 6


def test_admission_to_final_commit_is_available_without_followup_write(response_session, monkeypatch):
    db = response_session; scope = ("p-owner", "p-world", "p-thread")
    capture.configure(scope, True)
    try:
        owner, accepted, _ = admission(db, monkeypatch, memory=True, protocol=None)
        request_id = accepted.response_request.request_id
        async def provider(**kwargs):
            assert not db.in_transaction()
            kwargs["tracker"].next_call_order(); kwargs["tracker"].next_provider_call_order()
            if kwargs.get("tools"):
                return SimpleNamespace(text="", parsed=None, usage={}, finish_reason="STOP",
                    tool_calls=(ProviderToolCall("CANONICAL", {**core("CANONICAL"), "time_scope": BAD_TIME}, "bad-time"),))
            answer = {"text": "관련 기록을 확인했어요.", "thought": "기억을 살핀다.", "situation_description": "질문에 답했다."}
            return direct_llm.DirectLlmResponse(text=json.dumps(answer), parsed=answer, usage={}, finish_reason="STOP")
        monkeypatch.setattr(direct_llm, "generate_text", provider)
        asyncio.run(f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread", request_id,
            memory_recall_service=SimpleNamespace(hybrid_service=EmptyHybrid()),
            runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid"))))
        saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(request_id)
        assert saved.state.value == "committed", saved.node_state
        result = capture.read_full(scope, request_id)["db_write"]
        assert result["request_id"] == request_id and result["attempt_number"] == 1
        assert {"admission", "workflow_checkpoint", "response_finalize"} <= {a["stage"] for a in result["attempts"]}
        assert any(a["diagnostic_persist_ms"] is not None for a in result["attempts"])
        assert all(a["hold_ms"] is None for a in result["attempts"] if a["basis"] == "write_span_only")
        assert any(a["stage"] == "response_finalize" and a["outcome"] == "committed" for a in result["attempts"])
    finally:
        capture.configure(scope, False)


def test_completed_capture_retains_snapshot_after_ttl_but_stops_updates():
    owner=DiagnosticCapture();scope=("u","w","t")
    owner.configure(scope,True);generation=owner.generation(scope)
    owner.admit(scope,"r");collector=DbWriteCollector();owner.bind_db(scope,"r",generation,collector,1)
    feed(collector,"write_started",0,event="session_write");feed(collector,"committed",2,event="session_write")
    owner.store(scope,"r",[])
    expected=owner.read_full(scope,"r")["db_write"]
    owner._enabled[scope].until=datetime.now(UTC)-timedelta(seconds=1)
    assert owner.db_collector(scope,"r") is None
    feed(collector,"write_started",3,event="session_write");feed(collector,"committed",4,event="session_write")
    owner.store(scope,"r",[{"event":"late"}])
    assert owner.read_full(scope,"r")["db_write"]==expected


def test_admission_observer_failure_does_not_replay_or_fail_business(monkeypatch):
    from app.domains.chat.service.db_observation import observe_admission
    calls=[]
    @observe_admission
    def business(self,db,user,world,thread,data): calls.append(data);return "accepted"
    def broken(*args): raise RuntimeError("capture unavailable")
    monkeypatch.setattr(capture,"generation",broken)
    assert business(None,None,SimpleNamespace(id="u"),"w","t",1)=="accepted" and calls==[1]


def test_diagnostic_read_serializes_final_timing_and_safe_temporal_status(response_session,monkeypatch):
    from fastapi import Response
    from app.domains.chat.router import retrieval_diagnostics as router
    from app.domains.chat.schemas import DiagnosticRead
    from app.domains.chat.contracts.temporal_recall import ChatTimeContext,TemporalRecall
    record=f._request(response_session,f.RetrievalRoute.CANONICAL)
    row=response_session.get(f.models.ChatResponseRequest,record.request_id)
    state=json.loads(row.node_state_json)
    time=TemporalRecall("invalid",validation_code="time_scope_invalid",expression="private-expression-canary",
        context=ChatTimeContext.create(datetime.now(UTC),"Asia/Seoul"),resolution="invalid",query_origin="original_user_message")
    state["recall_interpretation"]={"temporal":{**time.diagnostic(),"retrieval_executed":False}}
    row.node_state_json=json.dumps(state);response_session.commit()
    owner=DiagnosticCapture();scope=("p-owner","p-world","p-thread")
    owner.configure(scope,True);generation=owner.generation(scope);owner.admit(scope,record.request_id)
    collector=DbWriteCollector();owner.bind_db(scope,record.request_id,generation,collector,record.attempt_number)
    feed(collector,"write_started",0,event="session_write");feed(collector,"committed",2,event="session_write")
    owner.store(scope,record.request_id,[]);monkeypatch.setattr(router,"capture",owner)
    value=DiagnosticRead.model_validate(router.diagnostics(Response(),request_id=record.request_id,scope=scope,db=response_session)).model_dump(mode="json")
    assert value["db_write"]["completed_attempts"]==1 and value["db_write"]["longest_hold_ms"] is None
    assert value["temporal_recall"]["time_resolution"]=="invalid" and not value["temporal_recall"]["retrieval_executed"]
    assert "private-expression-canary" not in json.dumps(value)


@pytest.mark.parametrize("outcome",["cancel","provider_failure"])
def test_v4_terminal_cleanup_keeps_capture_and_does_not_commit_late_answer(response_session,monkeypatch,outcome):
    from sqlalchemy import select,func
    db=response_session;scope=("p-owner","p-world","p-thread")
    capture.configure(scope,True)
    try:
        owner,accepted,_=admission(db,monkeypatch,protocol=None)
        entered,stopped=asyncio.Event(),asyncio.Event();calls=[]
        async def provider(**kwargs):
            calls.append("router" if kwargs.get("tools") else "crg")
            if kwargs.get("tools"):
                return SimpleNamespace(text="",parsed=None,usage={},finish_reason="STOP",
                    tool_calls=(ProviderToolCall("USE_CONTEXT",core("USE_CONTEXT"),"context-call"),))
            assert not db.in_transaction()
            entered.set()
            if outcome=="provider_failure":raise RuntimeError("synthetic provider failure")
            try:await asyncio.Event().wait()
            finally:stopped.set()
        monkeypatch.setattr(direct_llm,"generate_text",provider)
        async def run():
            task=asyncio.create_task(f._collect(generation_service.stream_world_response(db,owner,"p-world","p-thread",
                accepted.response_request.request_id,memory_recall_service=SimpleNamespace(hybrid_service=EmptyHybrid()),
                runtime_settings=Settings(_env_file=None,CHAT_RECALL_MODE="social_hybrid"))))
            if outcome=="cancel":
                await asyncio.wait_for(entered.wait(),5);task.cancel()
                with pytest.raises(asyncio.CancelledError):await task
                assert stopped.is_set()
            else:await task
        asyncio.run(run())
        saved=f.SqlAlchemyResponseLifecycleRepository(db).get_request(accepted.response_request.request_id)
        assert saved.state.value==("cancelled" if outcome=="cancel" else "failed")
        assert saved.committed_assistant_message_id is None and calls==["router","crg"]
        value=capture.read_full(scope,saved.request_id)["db_write"]
        assert any(row["stage"]=="cancel_or_failure" and row["outcome"]=="committed" for row in value["attempts"])
        assert db.scalar(select(func.count()).select_from(f.models.MessageMessage).where(f.models.MessageMessage.role=="assistant"))==0
    finally:capture.configure(scope,False)
