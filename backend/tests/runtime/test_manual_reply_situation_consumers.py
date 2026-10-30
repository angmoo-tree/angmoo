"""Owner replies through Inbox, then Routine; canonical Chat/SNS evidence reuse."""
import asyncio
import json
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from model_fixture_support import models
from app.integrations.direct_llm import RunLlmTracker, DirectLlmError
from app.providers.contracts import ProviderError
from app.runtime.autonomous_activity.combined_lanes import CombinedInboxLane
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.autonomous_activity.situation_memory import freeze_social_input
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.models.items import MemoryItem
from app.runtime.memory.situation_sources import SituationSources
from runtime.routine_manual_fixture import manual_routine, install_adapter, run_routine, apply_situations


async def inbox(case, monkeypatch, action):
    from app.runtime.social.planned_actions import _execute_planned_action
    case.ctx = replace(case.ctx, activity_policy=replace(case.ctx.activity_policy, allowed_actions=("post", "reply", "like")))
    async def guard(_state): return {}
    lane = CombinedInboxLane(case.ctx, actor=case.seeded.world_character, lane="inbox",
        tracker=RunLlmTracker(max_calls=8), hybrid_service=None, guard=guard,
        ledger=SimpleNamespace(reserve=lambda _key: pytest.fail("valid output needs no repair")),
        action_executor=_execute_planned_action)
    lane.provider.situation_snapshot = case.provider.situation_snapshot
    def output(request):
        payload = json.loads(request.user_prompt)
        target, = payload["selected_targets"]
        assert case.reply.id in target["source_ids"]
        identifier = target["target_id"]
        return {"decision": {"decisions": [{"target_id": identifier, "action": action, "brief": "Acknowledge the suggestion.",
            "interaction_intent": "ordinary_comment" if action == "comment" else None,
            "comment_purpose": "empathy" if action == "comment" else None}], "state_update": None, "state_source_refs": []},
            "draft": {"replies": [{"target_id": identifier, "body": "Thanks, I will consider that suggestion.",
                "thought": "A useful possibility."}] if action == "comment" else []},
            "situations": [{"target_id": identifier, "description": "I acknowledged the user's suggestion."}]}
    adapter = install_adapter(monkeypatch, output)
    shared = shared_input(case.ctx, case.seeded.world_character, case.seeded.world)
    shared["now"] = case.now.isoformat()
    case.db.commit()
    from app.runtime.autonomous_activity.combined_selection import CombinedSelection
    selection = CombinedSelection({"inbox": lane}, {"inbox": lane.ports()})
    initial = {**case.state, "shared_context": shared}
    selected = await selection.select({"identity": case.state["identity"], "shared_context": shared,
        "selection_mode": "combined", "prepared_lanes": {"inbox": await lane.load(initial)}})
    state = await build_lane("inbox", lane.ports(), combined=True).ainvoke({
        "identity": case.state["identity"], "shared_context": shared, **selected["prepared_lanes"]["inbox"]})
    return lane, state, adapter


@pytest.mark.parametrize("manual_routine", [False], indirect=True)
@pytest.mark.parametrize("action", ["comment", "like"])
@pytest.mark.parametrize("fail_routine_first", [False, True])
def test_completed_inbox_effect_is_not_repeated_by_routine_retry(manual_routine, monkeypatch, action, fail_routine_first):
    case = manual_routine
    inbox_lane, inbox_state, inbox_adapter = asyncio.run(inbox(case, monkeypatch, action))
    assert inbox_state["result"]["public_action_count"] == 1, inbox_state["result"]
    assert len(inbox_adapter.requests) == 1
    if fail_routine_first:
        with pytest.raises(DirectLlmError):
            asyncio.run(run_routine(case, monkeypatch, response=ProviderError("synthetic bad request",
                failure_class="bad_request", provider_code=400)))
        case.lane.release_failed("synthetic_provider_failure")
        case.db.refresh(case.candidate)
        assert case.candidate.status == "released"
    _, state, routine_adapter = asyncio.run(run_routine(case, monkeypatch))
    assert state["result"]["public_action_count"] == 1, state["result"]
    before = (case.db.scalar(select(func.count()).select_from(models.Post)),
        case.db.scalar(select(func.count()).select_from(models.PostLike)),
        case.db.scalar(select(func.count()).select_from(MemorySituationReceipt)))
    replay = asyncio.run(inbox_lane.execute(inbox_state))
    assert replay["executions"][0]["status"] == "reused"
    assert before == (case.db.scalar(select(func.count()).select_from(models.Post)),
        case.db.scalar(select(func.count()).select_from(models.PostLike)),
        case.db.scalar(select(func.count()).select_from(MemorySituationReceipt)))
    assert len(inbox_adapter.requests) == len(routine_adapter.requests) == 1
    apply_situations(case)
    assert all(r.state == "applied" for r in case.db.scalars(select(MemorySituationReceipt)))


def chat_capture(case, *, kind, identifier, text):
    """Real Chat delivery adapter; no response generation or request to a server."""
    from app.domains.chat.contracts.evidence_bundle import EvidenceItem, EvidenceKind, EvidenceLocator, EvidenceLocatorKind
    from app.domains.chat.contracts.response_request import RetrievalAxis, RetrievalOutcome
    from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
    from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
    from app.runtime.chat.situation_memory import ChatSituationMemory
    from app.domains.memory.contracts.activity_situation import SITUATION_POLICY
    thread = case.db.get(models.MessageThread, "routine-consumer-thread")
    if thread is None:
        thread = models.MessageThread(id="routine-consumer-thread", requester_id=case.ctx.user_id,
            character_id=case.seeded.character.id, world_id=case.seeded.world.id,
            requester_world_character_id=case.owner.id, responding_world_character_id=case.seeded.world_character.id,
            world_scope_status="resolved")
        case.db.add(thread); case.db.flush()
    message = models.MessageMessage(thread_id=thread.id, role="user", content="How did the experiment go?", status="ok")
    case.db.add(message); case.db.commit()
    is_memory = kind == "MEMORY_ITEM"
    item = EvidenceItem("source-1", EvidenceKind.EPISODE_MEMORY if is_memory else EvidenceKind.CANONICAL_SOURCE,
        text, None, (RetrievalAxis.CANONICAL,), locator=EvidenceLocator(
            EvidenceLocatorKind.MEMORY_ITEM if is_memory else EvidenceLocatorKind.CANONICAL_SOURCE,
            identifier, source_type=kind))
    bundle = EvidenceBundleAssembler()._bundle(request_id="routine-consumer-request", request_scope_hash="1"*64,
        route=RetrievalRoute.CANONICAL, outcome=RetrievalOutcome.MEMORY_USED, candidates=(item,))
    command = SimpleNamespace(request=SimpleNamespace(node_state={"_situation_policy": {
        "policy": SITUATION_POLICY, "snapshot": asdict(case.provider.situation_snapshot)}},
        request_scope_hash="1"*64, response_slot_id="routine-consumer-slot", thread_id=thread.id, user_message_id=message.id),
        preflight=SimpleNamespace(user_message=message.content, owner_id=case.ctx.user_id,
            world_id=case.seeded.world.id, thread_id=thread.id, requester_world_character_id=case.owner.id,
            responding_world_character_id=case.seeded.world_character.id),
        response_context=(), social_snapshot=None, image_evidence=None)
    payload = {"latest_user_message": message.content, "recent_context": [],
        "frozen_evidence": bundle.provider_payload()}
    return ChatSituationMemory(case.db), command, bundle, payload


@pytest.mark.parametrize("manual_routine", [False], indirect=True)
def test_consumed_comment_memory_can_be_reused_by_chat_and_sns_with_lineage_checks(manual_routine, monkeypatch):
    from app.domains.memory.policies.episode_provider_view import episode_provider_reference
    case = manual_routine
    asyncio.run(run_routine(case, monkeypatch))
    apply_situations(case)
    item = case.db.scalars(select(MemoryItem)).one()
    chat, command, bundle, payload = chat_capture(case, kind="MEMORY_ITEM", identifier=item.id, text=item.summary)
    chat_manifest = chat.freeze(command, bundle, payload)
    entry = next(s for s in chat_manifest.sources if s.source_type == "MEMORY_ITEM")
    reader, now = SituationSources(case.db), datetime.now(UTC)
    from app.domains.memory.repository.experience import validate_captured_sources
    receipt = SimpleNamespace(occurred_at=now, description="A captured delivery")
    def validate(manifest, selected):
        return next(access for source, access in validate_captured_sources(
            case.db, manifest, (), receipt, now=now) if source == selected)
    assert validate(chat_manifest, entry).state == "available"
    ref = episode_provider_reference("episode", f"memory-item:{item.id}")
    sns_payload = {"context": {"memories": {"target": {"packets": [{"ref": ref, "summary": item.summary}]}}}}
    sns_state = {"identity": case.state["identity"],
        "memory_validations": {"target": {"item_revisions": [(item.id, item.version, sha256(item.summary.encode()).hexdigest())]}}}
    sns_manifest = freeze_social_input(case.ctx, case.provider.situation_snapshot, node="FeedDecisionDraft",
        payload=sns_payload, transmitted=json.dumps(sns_payload), state=sns_state)
    prior = next(s for s in sns_manifest.sources if s.source_type == "MEMORY_ITEM")
    assert validate(sns_manifest, prior).state == "available"
    bad = replace(chat_manifest, snapshot=replace(chat_manifest.snapshot,
        scope=replace(chat_manifest.snapshot.scope, subject_world_character_id=case.owner.id)))
    with pytest.raises(ValueError, match="situation_prior_memory_deleted"):
        validate(bad, entry)
    wrong_thread = deepcopy(command)
    wrong_thread.request.thread_id = "not-the-message-thread"
    with pytest.raises(ValueError, match="situation_"):
        chat.freeze(wrong_thread, bundle, payload)
    case.reply.report_hidden_at = now
    case.db.commit(); case.db.expire_all()
    assert validate(chat_manifest, entry).state == "available"
    assert validate(sns_manifest, prior).state == "available"
    item.deleted_at, item.status = now, "deleted"
    case.db.commit()
    for manifest, source in ((chat_manifest, entry), (sns_manifest, prior)):
        with pytest.raises(ValueError, match="situation_prior_memory_deleted"):
            validate(manifest, source)


def test_chat_receives_real_reply_locator_not_inbox_candidate(manual_routine):
    case = manual_routine
    chat, command, bundle, payload = chat_capture(case, kind="REPLY", identifier=case.reply.id, text=case.reply.body)
    manifest = chat.freeze(command, bundle, payload)
    entries = [s for s in manifest.sources if s.source_type == "REPLY"]
    assert len(entries) == 1 and entries[0].source_id == case.reply.id
    assert any(s.source_type == "CHAT_MESSAGE" for s in manifest.sources)
    # A raw capture alone is not a committed delivery proof. The Chat finalize
    # regression exercises admission and the resulting durable proof separately.
    access = SituationSources(case.db).validate(manifest, entries[0], now=datetime.now(UTC))
    assert access.reason == "situation_delivery_proof_missing"
    case.reply.visibility = "private"
    case.db.commit(); case.db.expire_all()
    assert SituationSources(case.db).validate(manifest, entries[0], now=datetime.now(UTC)).state != "available"
