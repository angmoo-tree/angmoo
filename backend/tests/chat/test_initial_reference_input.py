"""Durable first-input round trips and bounded, scope-bound replay."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from chat.today_like_fixture import prepare, execute, f
from chat.test_social_context_workflow import SnapshotProvider
from app.domains.chat.contracts.initial_input import capture, restore, read, INPUT_KEY
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.relationships.contracts.graph_recall import GraphRecallScope

response_session = f.response_session


@pytest.mark.parametrize("change", ["missing_routing", "corrupt_input", "missing_input", "legacy_missing_input"])
def test_unrecoverable_input_finishes_without_retry_or_provider_call(response_session, change):
    import asyncio
    from app.domains.chat.contracts.input_receipt import ROUTING_STARTED
    record = f._request(response_session, f.RetrievalRoute.CURRENT_CONTEXT)
    metadata = {INPUT_KEY: capture(f._command(record))}
    if change == "missing_input":
        metadata = {ROUTING_STARTED: True}
    elif change == "legacy_missing_input":
        metadata = {'intent_hash': 'a' * 64}
    elif change == "missing_routing":
        metadata[ROUTING_STARTED] = True
    else:
        metadata[INPUT_KEY]["digest"] = "0" * 64
    response_session.get(f.models.ChatResponseRequest, record.request_id).node_state_json = json.dumps(metadata)
    response_session.commit()
    record = f.SqlAlchemyResponseLifecycleRepository(response_session).get_request(record.request_id)
    generator, router = f._Generator(), f._Router(f.RetrievalRoute.CURRENT_CONTEXT)
    workflow = f._workflow(response_session, f.RetrievalRoute.CURRENT_CONTEXT, generator, router=router)
    events = asyncio.run(f._collect(workflow.run(f._command(record))))
    final = workflow._lifecycle.get_request(record.request_id)
    assert final.node_state["failure_class"] == "initial_input_unavailable" and final.retryable is False
    assert not generator.requests and router.calls == 0
    assert events[-1].payload == {"failure_class": "initial_input_unavailable", "retryable": False}


def test_full_initial_input_roundtrip_keeps_today_and_social_after_live_edit(response_session):
    case = prepare(response_session)
    social = SnapshotProvider().prepare(GraphRecallScope("p-owner", "p-world", "p-responding"))
    original = replace(case.command, social_snapshot=social)
    raw = json.loads(json.dumps(capture(original)))
    case.root.body = "Only the next judgment may see this edit."
    case.db.commit()
    changed = replace(original, profile=replace(original.profile, name="New profile"),
                      today_sns_snapshot=None, social_snapshot=None, character_labels={})
    restored = restore(changed, raw)
    assert restored.profile == original.profile
    assert restored.character_labels == original.character_labels
    assert restored.today_sns_snapshot == original.today_sns_snapshot
    assert restored.social_snapshot == original.social_snapshot
    assert capture(restored) == raw


@pytest.mark.parametrize("change", ["text", "scope", "slot", "size", "policy"])
def test_invalid_initial_input_is_not_rebuilt_from_live_data(response_session, change):
    case = prepare(response_session)
    raw = deepcopy(capture(case.command))
    command = case.command
    if change == "text": raw["payload"]["user_message"] += " changed"
    elif change == "scope": command = replace(command, today_sns_snapshot=None,
        preflight=replace(command.preflight, owner_id="foreign"))
    elif change == "slot": command = replace(command, request=replace(command.request, response_slot_id="foreign"))
    elif change == "size": raw["payload"]["user_message"] = "x" * (512 * 1024)
    else: raw["payload"]["policy"] = "unknown"
    with pytest.raises(RetrievalContractError):
        restore(command, raw)


def test_today_content_edit_before_generator_keeps_first_delivery(response_session, monkeypatch):
    case = prepare(response_session)
    original = case.root.body
    # The acquired Today packet is deliberately older than the canonical row.
    case.root.body = "A later canonical edit"
    case.db.commit()
    result = execute(case, monkeypatch)
    assert not result.errors and len(result.assistants) == 1
    assert original in result.calls[0]["user_prompt"]
    assert "A later canonical edit" not in result.calls[0]["user_prompt"]
    assert result.final.node_state[INPUT_KEY]


def test_compound_source_clipping_never_attributes_another_post():
    from app.runtime.memory.captured_delivery import bind_candidate_sources, candidate_fragment
    references = {"a": {"body": "First body"}, "b": {"body": "Second body"}}
    candidate = {"target_id": "thread", "source_ids": ["a", "b"],
                 "text": "A: First body\nB: Second body"}
    bind_candidate_sources([candidate], references)
    assert candidate_fragment(references["a"], candidate, candidate["text"]) == "First body"
    assert candidate_fragment(references["b"], candidate, candidate["text"]) == "Second body"
    assert candidate_fragment(references["a"], candidate, "A: First…") == "First"
    assert candidate_fragment(references["b"], candidate, "A: First…") == ""


def test_sns_first_reference_packet_is_bounded_and_mutable_permissions_do_not_change_it():
    from app.contracts.relationship_currentness import CURRENTNESS_POLICY_KEY, CURRENTNESS_REVISION
    from app.runtime.autonomous_activity.initial_input import seal, assert_integrity
    state = {"identity": {CURRENTNESS_POLICY_KEY: CURRENTNESS_REVISION}, "shared_context": {},
        "candidates": [{"target_id": "post", "text": "Read first", "allowed_actions": ["reply"]}]}
    state.update(seal(state, {}))
    state["candidates"][0]["allowed_actions"] = []
    assert_integrity(state)
    state["candidates"][0]["text"] = "edited"
    with pytest.raises(ValueError, match="activity_initial_input_invalid"):
        assert_integrity(state)
    state["candidates"][0]["text"] = "x" * (512 * 1024)
    with pytest.raises(ValueError, match="activity_initial_input_limit"):
        seal(state, {})


def test_recall_component_roundtrip_preserves_typed_current_rights_snapshot():
    from datetime import UTC, datetime
    from types import MappingProxyType, SimpleNamespace
    from app.domains.chat.contracts.input_receipt import pack, unpack
    from app.domains.memory.contracts.hybrid_recall import (
        HybridRecallResult, EpisodeValidationSnapshot, RecallAxisStatus, RecallAxisReceipt, HybridEmbeddingUsage)
    from app.domains.memory.contracts.scope import MemoryScope
    from app.domains.memory.contracts.recall import CanonicalRecallRecord, RecallDocumentKind
    scope = MemoryScope("owner", "world", "actor")
    now = datetime.now(UTC)
    proof = EpisodeValidationSnapshot(scope, ("memory",), ("memory",), (("memory", 1, "a" * 64),), (), False,
        now, memory_snapshot_digests=(("memory", "b" * 64),))
    row = CanonicalRecallRecord("memory-item:memory", RecallDocumentKind.MEMORY_ITEM, "memory", "First summary", now,
        memory_item_id="memory", metadata=MappingProxyType({"item_version": "1", "episode_packet": "{\"units\":[]}"}))
    result = HybridRecallResult("request", "call", "c" * 64, scope, RecallAxisStatus.READY, (row,), tuple(
        RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 1, 0) for axis in ("fts", "vector")),
        (), HybridEmbeddingUsage(), 1, 0, 1, proof)
    record = SimpleNamespace(response_slot_id="slot", request_scope_hash="d" * 64)
    wire = json.loads(json.dumps(pack(result, HybridRecallResult, record)))
    restored = unpack(wire, HybridRecallResult, slot="slot", scope_hash="d" * 64)
    assert restored == result
    assert isinstance(restored.validation_snapshot, EpisodeValidationSnapshot)
    assert restored.records[0].metadata["item_version"] == "1"
    with pytest.raises(RetrievalContractError):
        unpack(wire, HybridRecallResult, slot="foreign", scope_hash="d" * 64)
