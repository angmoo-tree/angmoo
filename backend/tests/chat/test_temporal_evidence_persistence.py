"""Nonempty temporal evidence must survive the real response commit and read path."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_advisory_person_hints import core
from chat.test_named_selection_lifecycle import admission, EmptyHybrid
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat.test_temporal_recall_fallback import BAD_TIME
from app.config import Settings
from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
from app.domains.memory.contracts.recall import CanonicalRecallRecord, RecallDocumentKind
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.integrations import direct_llm
from app.providers.contracts import ProviderToolCall
from app.runtime.chat.message_composition import evidence_service, generation_service

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("fallback", [False, True], ids=["resolved-date", "date-repair-fallback"])
def test_nonempty_temporal_response_commits_reads_and_replays_once(
    response_session, monkeypatch, fallback,
):
    db = response_session
    now = datetime.now(UTC)
    # Actual isolated source rows feed Today SNS and the inspector's live reads.
    for index in range(4):
        db.add(f.models.Post(
            id=f"temporal-post-{index}", author_character_id="p-responding-character",
            world_id="p-world", author_world_character_id="p-responding",
            author_name="Bram", title=f"연습 기록 {index}", body=f"오늘 연습한 내용 {index}.",
            search_document=f"오늘 연습한 내용 {index}.", visibility="public",
            created_at=now, updated_at=now,
        ))
    db.commit()
    owner, accepted, _ = admission(
        db, monkeypatch, memory=True, question="오늘 무슨 일이 있었어?", protocol=None,
    )
    request_id = accepted.response_request.request_id

    class SourceHybrid(EmptyHybrid):
        async def execute(self, request, *, deadline):
            result = await super().execute(request, deadline=deadline)
            record = CanonicalRecallRecord(
                "retrieved-post", RecallDocumentKind.POST, "temporal-post-0",
                "오늘 연습한 내용 0.", now,
            )
            return replace(result, records=(record,))

    hybrid, calls, generated_items = SourceHybrid(), [], []

    async def provider(**kwargs):
        assert not db.in_transaction(), "Provider waits must stay outside the writer"
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        kwargs["tracker"].next_provider_call_order()
        if kwargs.get("tools"):
            args = {**core("CANONICAL"), "time_scope": BAD_TIME if fallback else {
                "kind": "current_day", "expression": "오늘",
            }}
            return SimpleNamespace(text="", usage={}, finish_reason="STOP", tool_calls=(
                ProviderToolCall("CANONICAL", args, f"call-{len(calls)}"),
            ))
        payload = json.loads(kwargs["user_prompt"].split("\n", 1)[-1])
        generated_items.extend(payload["frozen_evidence"]["items"])
        answer = {
            "text": "오늘 연습한 기록이 있어요.", "thought": "확인한 기록으로 답한다.",
            "situation_description": "사용자가 오늘 일을 물었고 캐릭터가 연습 기록을 확인해 답했다.",
        }
        return direct_llm.DirectLlmResponse(
            text=json.dumps(answer), parsed=answer, usage={}, finish_reason="STOP",
        )

    monkeypatch.setattr(direct_llm, "generate_text", provider)

    def run():
        return asyncio.run(f._collect(generation_service.stream_world_response(
            db, owner, "p-world", "p-thread", request_id,
            memory_recall_service=SimpleNamespace(hybrid_service=hybrid),
            runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid"),
        )))

    events = run()
    saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(request_id)
    assert len(generated_items) == 5  # The final generator really received nonempty evidence.
    assert saved.state.value == "committed", saved.node_state
    assert events[-1].event_type is GenerationEventType.COMPLETED
    assert len(calls) == (3 if fallback else 2)
    assert len(hybrid.requests) == 1
    assert (hybrid.requests[0].occurred_from is None) is fallback
    # One canonical source plus four Today SNS entries.
    assert {item["kind"] for item in generated_items} == {"canonical_source", "today_sns_activity"}
    stored = saved.response_metadata["_evidence_inspector_v1"]["items"]
    assert {item["ref"]: item["time_provenance"] for item in stored} == {
        item["ref"]: item["time_provenance"] for item in generated_items
    }
    assert all(item["time_provenance"]["kind"] == "event" for item in stored)
    db.expire_all()
    assistant = db.get(f.models.MessageMessage, saved.committed_assistant_message_id)
    assert assistant.content == "오늘 연습한 기록이 있어요."
    view = evidence_service.get_world_response_evidence(db, owner, "p-world", "p-thread", request_id)
    assert view.capability == "available" and len(view.items) == 5
    assert all(item.availability == "available" and item.time_provenance.event_from == now for item in view.items)
    assert all(item.canonical_href.startswith("/worlds/p-world/posts/temporal-post-") for item in view.items)

    replay = run()
    assert replay[-1].event_type is GenerationEventType.COMPLETED
    assert len(calls) == (3 if fallback else 2) and len(hybrid.requests) == 1
    assert db.scalar(select(func.count()).select_from(f.models.MessageMessage).where(
        f.models.MessageMessage.role == "assistant")) == 1
    assert db.scalar(select(func.count()).select_from(MemorySituationReceipt)) == 1

    # Persisted time metadata does not bypass current source-revision checks.
    db.get(f.models.Post, "temporal-post-1").body = "수정된 기록"
    db.commit()
    changed = evidence_service.get_world_response_evidence(db, owner, "p-world", "p-thread", request_id)
    unavailable = [item for item in changed.items if item.availability != "available"]
    assert changed.capability == "degraded" and len(unavailable) == 1
    assert unavailable[0].excerpt is None and unavailable[0].time_provenance is None
