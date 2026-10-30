import asyncio
from dataclasses import replace
from hashlib import sha256

import pytest
from chat.today_like_fixture import prepare, execute, f
from app.domains.chat.contracts.generation_lifecycle import ResponseTerminalReason
from app.domains.chat.exceptions import ChatSituationEvidenceError
from app.domains.memory.contracts.activity_situation import DeliveredInputManifest
from app.domains.memory.models.activity_situation import MemorySituationManifest
from app.domains.relationships.models.social import SocialEvent
from app.integrations import direct_llm
from sqlalchemy import event

response_session = f.response_session


CASES = [(transitions, enabled, f.RetrievalRoute.CURRENT_CONTEXT, True, False)
    for transitions in ((), (True,), (True, False), (True, False, True)) for enabled in (False, True)] + [
    ((True,), True, f.RetrievalRoute.CLARIFICATION, True, False),
    ((True,), True, f.RetrievalRoute.CURRENT_CONTEXT, False, False),
    ((True,), True, f.RetrievalRoute.CURRENT_CONTEXT, True, True),
    ((True, False), True, f.RetrievalRoute.CURRENT_CONTEXT, True, True)] + [
    ((True,), True, route, True, False) for route in
    (f.RetrievalRoute.CANONICAL, f.RetrievalRoute.GRAPH, f.RetrievalRoute.BOTH)]


@pytest.mark.parametrize("transitions,enabled,route,include_today,nested", CASES)
def test_real_chat_adapter_commits_manual_today_events(response_session, monkeypatch,
        transitions, enabled, route, include_today, nested):
    case = prepare(response_session, transitions=transitions, enabled=enabled, route=route,
                   include_today=include_today, nested=nested)
    assert len(case.events) == len(transitions)
    result = execute(case, monkeypatch)
    assert not result.errors, result.errors
    assert len(result.calls) == len(result.assistants) == 1
    assert result.events[-1].event_type is f.GenerationEventType.COMPLETED
    assert [r.state for r in result.receipts] == (["pending"] if enabled else [])
    if enabled:
        manifest = DeliveredInputManifest.from_dict(case.db.get(MemorySituationManifest, result.receipts[0].manifest_id).payload)
        expected = len(transitions) if include_today and route is not f.RetrievalRoute.CLARIFICATION else 0
        sources = [s for s in manifest.sources if s.source_type == "SOCIAL_EVENT"]
        assert len(sources) == expected
        assert manifest.version == 3 and manifest.private_thread_id == "p-thread"
        assert manifest.payload_digest == sha256(result.calls[0]["user_prompt"].encode()).hexdigest()
        for source in sources:
            index = int(source.payload_path.split("/")[-2])
            item = result.requests[0].evidence.items[index]
            assert source.role == "background" and source.source_id == item.locator.source_id
            assert source.source_digest == item.locator.source_revision == source.source_version
            assert source.delivered_digest == sha256(item.text.encode()).hexdigest()
            assert source.delivery_payload_digest == manifest.payload_digest
            assert case.db.get(SocialEvent, source.source_id).retrieval_status == "audit_only"
            assert source.source_id not in result.calls[0]["user_prompt"]
    # Reconnect/resume the committed request must reuse the same result.
    before_calls = len(result.calls)
    again = replace(case.command, request=result.final)
    asyncio.run(f._collect(result.workflow.run(again)))
    assert len(result.calls) == before_calls
    assert f.SqlAlchemyResponseLifecycleRepository(case.db).get_request(case.record.request_id).committed_assistant_message_id == result.assistants[0].id


def test_bad_delivery_is_contract_failure_before_transport(response_session, monkeypatch):
    case = prepare(response_session)
    def tamper(payload):
        payload["frozen_evidence"]["items"][0]["text"] += " fabricated"
    result = execute(case, monkeypatch, mutate_payload=tamper)
    assert not result.calls and not result.assistants and not result.receipts
    assert isinstance(result.errors[0], ChatSituationEvidenceError)
    assert result.final.terminal_reason is ResponseTerminalReason.CONTRACT_INVALID
    assert result.final.node_state["failure_class"] == "situation_evidence_contract_invalid"
    assert not result.final.retryable


@pytest.mark.parametrize("kind", ["reply", "post"])
def test_owner_written_today_sources_keep_existing_subject_scope(response_session, monkeypatch, kind):
    case = prepare(response_session, transitions=(), event_kind=kind)
    assert len(case.events) == 1
    # A reply to this character is in its Today. A user's independent root
    # post is not this character's personal activity; no scope broadening.
    selected = [e for e in case.snapshot.entries if e.source_type == "social_event"]
    assert len(selected) == (1 if kind == "reply" else 0)
    result = execute(case, monkeypatch)
    assert not result.errors and len(result.assistants) == len(result.calls) == 1
    assert result.receipts[0].state == "pending"


@pytest.mark.parametrize("status,expected", [(503, "provider_unavailable"), (429, "provider_busy")])
def test_provider_errors_stay_separate_from_binding_failure(response_session, monkeypatch, status, expected):
    case = prepare(response_session)
    error = direct_llm.DirectLlmError("Synthetic provider failure")
    error.provider_error = {"provider_http_status": status}
    result = execute(case, monkeypatch, transport_error=error)
    assert len(result.calls) == 1 and not result.assistants and not result.receipts
    assert result.final.terminal_reason is ResponseTerminalReason.PROVIDER_FAILURE
    assert result.final.node_state["failure_class"] == expected and result.final.retryable


def test_auxiliary_description_failure_keeps_committed_reply(response_session, monkeypatch):
    case = prepare(response_session)
    result = execute(case, monkeypatch, invalid_description=True)
    assert not result.errors and len(result.calls) == len(result.assistants) == 1
    assert result.receipts[0].state == "blocked" and result.receipts[0].description_status == "missing"


def test_receipt_failure_rolls_back_assistant_for_manual_today(response_session, monkeypatch):
    case = prepare(response_session)
    def fail_insert(_conn, _cursor, sql, *_):
        if sql.startswith("INSERT INTO memory_situation_receipts"):
            raise RuntimeError("synthetic_receipt_failure")
    event.listen(case.db.bind, "before_cursor_execute", fail_insert)
    try:
        result = execute(case, monkeypatch)
    finally:
        event.remove(case.db.bind, "before_cursor_execute", fail_insert)
    assert len(result.calls) == 1 and not result.assistants and not result.receipts
    assert result.events[-1].event_type is f.GenerationEventType.FAILED
