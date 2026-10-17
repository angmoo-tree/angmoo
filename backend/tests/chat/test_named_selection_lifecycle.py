"""Actual admission/composition/serialization with isolated DB and denied network."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from chat import test_p8_l_p_evidence_response_streaming as f
from chat.test_p8_l_p_evidence_response_streaming import response_session
from chat.test_named_retrieval_resolution import setup_names, rename
from chat.test_named_supervisor_selection import arguments, options
from app.config import Settings, settings
from app.contracts.environment import EnvironmentSnapshot
from app.domains.chat.contracts.chat_identity_context import ChatIdentityContext, IDENTITY_KEY
from app.domains.chat.contracts.generation_lifecycle import GenerationEventType
from app.domains.chat.contracts.supervisor_selection import NAME_SELECTION_PROTOCOL, ADVISORY_SELECTION_PROTOCOL, SELECTION_PROTOCOL_KEY, LEGACY_HYBRID_PROTOCOL
from app.domains.chat.contracts.temporal_recall import TEMPORAL_SELECTION_PROTOCOL, TIME_CONTEXT_KEY
from app.domains.chat.schemas import WorldChatMessageCreate, WorldChatRetryCreate
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationManifest
from app.domains.memory.service.scope import MemoryScopeService
from app.runtime.chat.message_composition import generation_service
from app.runtime.memory.composition import memory_repository
from app.providers.contracts import ProviderToolCall


def admission(db, monkeypatch, *, memory=False, question="Bram은 나를 어떻게 생각해?", protocol=NAME_SELECTION_PROTOCOL):
    setup_names(db)
    monkeypatch.setattr(settings, "CHAT_RECALL_MODE", "social_hybrid")
    monkeypatch.setattr(settings, "MEMORY_GENERATION_POLICY", "activity_situation")
    monkeypatch.setattr("app.domains.chat.service.generation.snapshot", lambda *_: EnvironmentSnapshot(
        memory_search_locale="ko-KR", timezone="Asia/Seoul"))
    # This integration exercises the owner's character, including the existing
    # relationship read authority. Memory ON/OFF is independent of ownership.
    db.get(f.models.Character, "p-responding-character").owner_id = "p-owner"
    db.get(f.models.WorldCharacter, "p-responding").membership_id = "p-owner-membership"
    if memory:
        service = MemoryScopeService(memory_repository(db))
        scope = MemoryScope("p-owner", "p-world", "p-responding")
        current = service.get_or_create(scope)
        service.update(scope, expected_version=current.version, enabled=True, retention_days=180)
    db.commit()
    data = WorldChatMessageCreate(content=question, idempotency_key="named-admission-fixture-key")
    owner = db.get(f.models.User, "p-owner")
    accepted = generation_service.accept_world_message(db, owner, "p-world", "p-thread", data)
    # Legacy lifecycle fixtures explicitly replay their admitted v2 protocol.
    if protocol is not None:
        row = db.get(f.models.ChatResponseRequest, accepted.response_request.request_id)
        state = json.loads(row.node_state_json)
        state[SELECTION_PROTOCOL_KEY] = protocol
        row.node_state_json = json.dumps(state)
        db.commit()
    return owner, accepted, data


def metadata(db, request_id):
    return json.loads(db.get(f.models.ChatResponseRequest, request_id).node_state_json)


def fail(db, request_id):
    repository = f.SqlAlchemyResponseLifecycleRepository(db)
    now = datetime.now(UTC)
    row = repository.acquire_lease(request_id=request_id, lease_token="named-failure",
        now=now, lease_expires_at=now + timedelta(seconds=30))
    fence = f.GenerationFence(row.request_id, row.thread_id, row.request_scope_hash,
        row.generation_id, row.attempt_number, row.lease_generation, row.state)
    repository.mark_terminal(fence, target=f.ResponseRequestState.FAILED,
        reason=f.ResponseTerminalReason.CONTRACT_INVALID, retryable=True,
        failure_class="router_schema_rejected", now=now)
    db.commit()


def test_protocol_replay_and_explicit_retry_preserve_the_original_admission(response_session, monkeypatch):
    db = response_session
    owner, accepted, data = admission(db, monkeypatch, memory=True)
    request_id = accepted.response_request.request_id
    old = metadata(db, request_id)
    assert old[SELECTION_PROTOCOL_KEY] == NAME_SELECTION_PROTOCOL
    # Simulate a historically admitted hybrid-v1 request, without changing its names.
    old[SELECTION_PROTOCOL_KEY] = LEGACY_HYBRID_PROTOCOL
    db.get(f.models.ChatResponseRequest, request_id).node_state_json = json.dumps(old)
    db.commit()
    replay = generation_service.accept_world_message(db, owner, "p-world", "p-thread", data)
    assert replay.outcome == "replayed" and metadata(db, request_id) == old
    fail(db, request_id)
    failed_json = db.get(f.models.ChatResponseRequest, request_id).node_state_json
    rename(db, "p-requester", "New user name")
    rename(db, "p-responding", "New assistant name")
    db.commit()
    retry_data = WorldChatRetryCreate(failed_request_id=request_id, idempotency_key="named-explicit-retry-key")
    retry = generation_service.retry_world_response(db, owner, "p-world", "p-thread", retry_data)
    repeated = generation_service.retry_world_response(db, owner, "p-world", "p-thread", retry_data)
    new = metadata(db, retry.response_request.request_id)
    assert new[SELECTION_PROTOCOL_KEY] == TEMPORAL_SELECTION_PROTOCOL
    assert new[TIME_CONTEXT_KEY] == old[TIME_CONTEXT_KEY]
    for key in ("name_binding_policy", "name_binding", "_world_credential", IDENTITY_KEY,
                "_world_configuration", "_environment", "_situation_policy"):
        assert new[key] == old[key]
    assert retry.user_message.id == accepted.user_message.id
    assert retry.response_request.response_slot_id == accepted.response_request.response_slot_id
    assert db.get(f.models.ChatResponseRequest, retry.response_request.request_id).selected_model == db.get(f.models.ChatResponseRequest, request_id).selected_model
    assert repeated.outcome == "replayed" and repeated.response_request.request_id == retry.response_request.request_id
    assert db.get(f.models.ChatResponseRequest, request_id).node_state_json == failed_json
    assert db.get(f.models.ChatResponseRequest, request_id).state == "failed"


@pytest.mark.parametrize("damage", [None, "unknown", "object", "missing_identity", "wrong_mode"])
def test_present_damaged_protocol_fails_before_provider_or_image(response_session, monkeypatch, damage):
    db = response_session
    owner, accepted, _ = admission(db, monkeypatch)
    request_id = accepted.response_request.request_id
    value = metadata(db, request_id)
    if damage == "missing_identity": value.pop(IDENTITY_KEY)
    elif damage not in {"wrong_mode"}: value[SELECTION_PROTOCOL_KEY] = {} if damage == "object" else damage
    db.get(f.models.ChatResponseRequest, request_id).node_state_json = json.dumps(value)
    db.commit()
    def forbidden(*args, **kwargs):
        pytest.fail("Damaged protocol reached provider/image workflow construction")
    monkeypatch.setattr(generation_service.workflows, "build", forbidden)
    mode = "legacy_checkpoint" if damage == "wrong_mode" else "social_hybrid"
    events = asyncio.run(f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread",
        request_id, memory_recall_service=SimpleNamespace(), runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE=mode))))
    assert events[-1].event_type is GenerationEventType.FAILED
    saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(request_id)
    assert saved.node_state["failure_class"] == "selection_protocol_invalid" and not saved.retryable
    public = generation_service.get_world_response_request(db, owner, "p-world", "p-thread", request_id).model_dump_json()
    assert SELECTION_PROTOCOL_KEY not in public and IDENTITY_KEY not in public


def test_historical_retry_without_identity_retains_legacy_contract(response_session, monkeypatch):
    db = response_session
    monkeypatch.setattr(settings, "CHAT_RECALL_MODE", "social_hybrid")
    record = f._request(db, f.RetrievalRoute.CURRENT_CONTEXT)
    db.commit(); fail(db, record.request_id)
    retry = generation_service.retry_world_response(db, db.get(f.models.User, "p-owner"), "p-world", "p-thread",
        WorldChatRetryCreate(failed_request_id=record.request_id, idempotency_key="legacy-explicit-retry-key"))
    assert SELECTION_PROTOCOL_KEY not in metadata(db, retry.response_request.request_id)


class EmptyHybrid:
    def __init__(self): self.requests = []

    async def execute(self, request, *, deadline):
        from app.domains.memory.contracts.hybrid_recall import (
            HybridRecallResult, RecallAxisStatus, RecallAxisReceipt, HybridEmbeddingUsage)
        self.requests.append(request)
        return HybridRecallResult(request.request_id, request.call_id, request.envelope_hash,
            request.scope, RecallAxisStatus.READY, (), tuple(
                RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 0, 0) for axis in ("fts", "vector")),
            (), HybridEmbeddingUsage(), 0, 0, 0)


@pytest.mark.parametrize("memory,control,invalid", [
    (False, "USE_CONTEXT", 0), (True, "USE_CONTEXT", 0),
    (True, "CANONICAL", 0), (False, "CANONICAL", 0),
    (False, "REQUEST_CLARIFICATION", 0),
    (False, "USE_CONTEXT", 1), (False, "USE_CONTEXT", 2),
])
def test_admission_to_real_composition_commit_and_receipt(response_session, monkeypatch, memory, control, invalid):
    from app.domains.chat.contracts.relationship_evidence import DELIVERY_KEY
    from app.domains.memory.contracts.activity_situation import DeliveredInputManifest
    from app.integrations import direct_llm
    from app.domains.chat.contracts.person_roles import person_role_description
    from app.domains.chat.contracts.recall_interpretation import NAMED_ADMISSION_REVISION
    db = response_session
    question = "내가 좋아하는 사람이 누군지 맞춰봐" if control == "USE_CONTEXT" else "Bram과 나의 예전 약속을 기억해?"
    owner, accepted, _ = admission(db, monkeypatch, memory=memory, question=question)
    calls, hybrid, transactions = [], EmptyHybrid(), []

    async def provider(**kwargs):
        transactions.append(db.in_transaction())
        calls.append(kwargs)
        kwargs["tracker"].next_call_order()
        kwargs["tracker"].next_provider_call_order()
        if kwargs.get("tools"):
            args = arguments()
            args["intent"] = "current_context" if control == "USE_CONTEXT" else "historical_recall"
            if control != "CANONICAL": args.pop("search_text")
            if control == "REQUEST_CLARIFICATION":
                args.update(intent="clarification_required", clarification_slot="entity_identity")
            args["entities"] = [{"mention": "진구", "role": "subject"}]
            args["relationship"] = None
            if control == "CANONICAL":
                args["entities"].append({"mention": "Unknown spelling", "role": "counterpart"})
                args["search_text"] = question
            if len(calls) <= invalid:
                args["entities"][0]["ref"] = "synthetic_context_person_1"
            return SimpleNamespace(text="", parsed=None, usage={}, finish_reason="STOP",
                tool_calls=(ProviderToolCall(control, args, "named-native-call"),))
        answer = {"text": "아직 상대가 누구인지는 확실하지 않아. 힌트를 줄래?", "thought": "상대를 단정하지 않기로 한다."}
        if memory:
            answer["situation_description"] = "진구가 좋아하는 상대에 대해 물었고 Bram은 단정하지 않고 힌트를 요청했다."
        return direct_llm.DirectLlmResponse(text=json.dumps(answer, ensure_ascii=False), parsed=answer, usage={}, finish_reason="STOP")

    monkeypatch.setattr(direct_llm, "generate_text", provider)
    events = asyncio.run(f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread",
        accepted.response_request.request_id, memory_recall_service=SimpleNamespace(hybrid_service=hybrid),
        runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid"))))
    saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(accepted.response_request.request_id)
    assert not any(transactions), "Name/config reads must checkpoint before awaiting a provider"
    if invalid == 2:
        assert saved.state.value == "failed" and len(calls) == 2
        assert saved.node_state["failure_class"] == "router_schema_rejected"
        assert saved.node_state["router_diagnostic"]["physical_attempts"] == 2
        assert saved.node_state["router_diagnostic"]["repair_exhausted"] is True
        assert not list(db.scalars(select(MemorySituationReceipt)))
        assert all(call.get("tools") for call in calls)
        return
    assert events[-1].event_type is GenerationEventType.COMPLETED, events[-1].payload
    assert saved.state.value == "committed" and len(calls) == 2 + invalid
    assert saved.call_tracker["physical_total"] == 2 + invalid
    payload = json.loads(calls[-1]["user_prompt"].split("\n", 1)[1])
    assert payload["recall_interpretation"]["revision"] == NAMED_ADMISSION_REVISION
    assert payload["recall_interpretation"]["mentions"][0] == {"mention": "진구", "role": "subject", "resolution": "resolved"}
    assert payload["recall_interpretation"]["requested_direction"] is None
    assert payload["latest_user_message"]["content"] == "진구: " + question
    assert "entity-1" not in json.dumps(payload["recall_interpretation"])
    assert calls[-1]["system_prompt"].count(person_role_description()) == 1
    assert len(hybrid.requests) == int(memory and control == "CANONICAL")
    if hybrid.requests:
        assert hybrid.requests[0].scope == MemoryScope("p-owner", "p-world", "p-responding")
    receipt_rows = list(db.scalars(select(MemorySituationReceipt)))
    assert len(receipt_rows) == int(memory)
    if memory:
        assert "Use ko-KR for this description" in calls[-1]["system_prompt"]
        receipt = receipt_rows[0]
        assert receipt.state == "pending" and receipt.description_status == "valid"
        manifest = DeliveredInputManifest.from_dict(db.get(MemorySituationManifest, receipt.manifest_id).payload)
        prompt_digest = sha256(calls[-1]["user_prompt"].encode()).hexdigest()
        assert manifest.payload_digest == saved.response_metadata[DELIVERY_KEY]["prompt_digest"] == prompt_digest
        assert manifest.snapshot.memory_search_locale == "ko-KR"
        assert saved.response_metadata[DELIVERY_KEY]["payload_digest"] == sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert all(source.delivery_payload_digest in {None, prompt_digest} for source in manifest.sources)
        if control == "CANONICAL" and invalid == 0:
            # Consume a v2-produced receipt through the existing source-checked
            # Memory path, rather than only observing a pending database row.
            from app.domains.memory.models.items import MemoryItem
            from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
            from app.domains.memory.repository.situation_apply import apply_page
            from app.runtime.memory.situation_sources import SituationSources
            now = datetime.now(UTC)
            repository = memory_repository(db)
            setting = MemoryScopeService(repository).get_or_create(MemoryScope("p-owner", "p-world", "p-responding"))
            get_or_create_settings(db, setting.id, timezone="Asia/Seoul", now=now)
            run = request_run(db, setting, trigger="manual", request_key="named-memory-save-fixture", expected_version=1, now=now)
            token = claim_run(db, run.run_id, now=now)
            db.commit()
            apply_page(db, repository, SituationSources(db), run_id=run.run_id, token=token, now=now)
            db.commit()
            assert receipt.state == "applied", receipt.error_code
            assert db.get(MemoryItem, receipt.applied_item_id) is not None
            assert db.get(f.models.MessageMessage, saved.user_message_id).content == question
    dto = generation_service.get_world_response_request(db, owner, "p-world", "p-thread", saved.request_id).model_dump_json()
    assert "person_roles" not in dto and "selection-args" not in dto
    assert db.scalar(select(func.count()).select_from(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant")) == 1


@pytest.mark.parametrize("waiting_at", ["router", "crg"])
def test_named_admission_cancellation_stops_provider_and_never_commits(response_session, monkeypatch, waiting_at):
    from app.integrations import direct_llm
    db = response_session
    owner, accepted, _ = admission(db, monkeypatch, memory=True)
    entered, stopped = asyncio.Event(), asyncio.Event()
    provider_stages = []

    async def provider(**kwargs):
        stage = "router" if kwargs.get("tools") else "crg"
        provider_stages.append(stage)
        assert not db.in_transaction()
        if stage == waiting_at:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        args = arguments()
        args.pop("search_text")
        args.update(intent="current_context", entities=[{"mention": "진구", "role": "subject"}], relationship=None)
        return SimpleNamespace(text="", parsed=None, usage={}, finish_reason="STOP",
            tool_calls=(ProviderToolCall("USE_CONTEXT", args, "cancel-native-call"),))

    monkeypatch.setattr(direct_llm, "generate_text", provider)

    async def cancel_inflight():
        task = asyncio.create_task(f._collect(generation_service.stream_world_response(db, owner, "p-world", "p-thread",
            accepted.response_request.request_id, memory_recall_service=SimpleNamespace(hybrid_service=EmptyHybrid()),
            runtime_settings=Settings(_env_file=None, CHAT_RECALL_MODE="social_hybrid"))))
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()

    asyncio.run(cancel_inflight())
    saved = f.SqlAlchemyResponseLifecycleRepository(db).get_request(accepted.response_request.request_id)
    assert saved.state is f.ResponseRequestState.CANCELLED and saved.committed_assistant_message_id is None
    assert provider_stages == (["router"] if waiting_at == "router" else ["router", "crg"])
    assert not list(db.scalars(select(MemorySituationReceipt)))
    assert db.scalar(select(func.count()).select_from(f.models.MessageMessage).where(f.models.MessageMessage.role == "assistant")) == 0
