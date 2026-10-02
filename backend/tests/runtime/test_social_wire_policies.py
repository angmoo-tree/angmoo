"""Exercise new lane wire at the schema, validator and real transport boundaries."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from app.domains.world_characters.contracts.social_io import (
    BOUNDED_ROUTINE_OUTPUT, COMMON_IO, LANE_IO, LEGACY_ROUTINE_OUTPUT, new_policies, read_policies,
)
from app.domains.world_characters.contracts.checkpoint_retention import business_result
from app.integrations import direct_llm
from app.runtime.autonomous_activity import provider as transport
from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider
from app.runtime.autonomous_activity.generation_contracts import draft_schema, parse_social_draft
from app.runtime.autonomous_activity.planner_contract import parse_action, planner_response_schema
from app.runtime.autonomous_activity.provider import candidate_previews
from app.runtime.autonomous_activity.social_wire import assignment_view, target_view

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.mark.parametrize("combined", [False, True])
def test_mixed_inbox_writer_rejects_even_null_response_fields_on_ordinary_target(combined):
    from app.runtime.autonomous_activity.provider import parse_writer_output
    assignments = [{"task_id": "ordinary", "source": {"target_id": "a"}, "proposal_response": None},
                   {"task_id": "response", "source": {"target_id": "b"},
                    "proposal_response": {"proposal_decision": "accept"}}]
    key = "target_id" if combined else "task_id"
    value = {"replies": [{key: "a" if combined else "ordinary", "body": "hello", "proposal_decision": None},
                         {key: "b" if combined else "response", "body": "yes", "proposal_decision": "accept"}]}
    with pytest.raises(ValueError, match="social_draft_field_forbidden"):
        if combined:
            parse_social_draft(value, lane="inbox", assignments=assignments, policy=LANE_IO)
        else:
            parse_writer_output(value, lane="inbox", assignments=assignments, policy=LANE_IO)


def candidate(**updates):
    return {"target_id": "post", "counterpart_id": "other", "source_ids": ["post"],
        "source_revisions": {"post": "v1"}, "text": "full source", "parent_text": "parent",
        "waiting_since": "2026-10-01", "activity_proposal": None, "proposal_eligible": False,
        "topic_signature": "topic", "allowed_actions": ["comment", "like"],
        "images": [{"asset_id": "image", "analysis": "observed"}], **updates}


@pytest.mark.parametrize("lane,capable,forbidden", [
    ("feed", False, {"proposal", "proposal_response"}),
    ("feed", True, {"proposal_response"}),
    ("inbox", False, {"proposal", "proposal_response"}),
    ("inbox", True, {"proposal"}),
])
def test_lane_and_capability_schema_excludes_impossible_actions(lane, capable, forbidden):
    source = candidate(proposal_eligible=capable, activity_proposal={"id": "invitation"} if capable else None)
    schema = planner_response_schema([source], lane=lane, policy=LANE_IO)
    fields = schema["properties"]["decisions"]["items"]["properties"]
    assert not forbidden & set(fields)
    assert fields["target_id"]["enum"] == ["post"]
    if "proposal" in fields:
        assert "text" not in fields["proposal"]["properties"]
        assert fields["proposal"]["properties"]["activity_seed"]["maxLength"] == 500
    if "proposal_response" in fields:
        assert not {"task_id", "body"} & set(fields["proposal_response"]["properties"])
        assert "counter_target_date" in fields["proposal_response"]["properties"]
    for key in forbidden:
        with pytest.raises(ValidationError):
            parse_action({"decisions": [{"target_id": "post", "action": "no_action", key: None}],
                "state_update": None}, [source], lane=lane, policy=LANE_IO)


def test_meaning_counter_validation_and_target_checks_survive_wire_reduction():
    source = candidate(activity_proposal={"id": "proposal"})
    response = {"proposal_decision": "counter", "counter_activity_seed": "walk",
        "counter_target_daypart": "morning", "counter_date_policy": "exact"}
    row = {"target_id": "post", "action": "comment", "interaction_intent": "proposal_response",
        "brief": "Suggest a different morning", "proposal_response": response}
    with pytest.raises(ValidationError):
        parse_action({"decisions": [row], "state_update": None}, [source], lane="inbox", policy=LANE_IO)
    response["counter_target_date"] = "2026-10-04"
    result = parse_action({"decisions": [row], "state_update": None}, [source], lane="inbox", policy=LANE_IO)
    assert not {"task_id", "body"} & set(result["decisions"][0]["proposal_response"])
    response["task_id"] = "model-invented"
    with pytest.raises(ValidationError):
        parse_action({"decisions": [row], "state_update": None}, [source], lane="inbox", policy=LANE_IO)


@pytest.mark.parametrize("lane,excluded", [
    ("feed", {"parent_text", "parent_text_partial", "waiting_since", "activity_proposal"}),
    ("inbox", {"topic_signature", "proposal_eligible"}),
])
def test_projection_only_changes_model_view_and_keeps_images_sources_and_writer_tasks(lane, excluded):
    source = candidate()
    original = deepcopy(source)
    preview = candidate_previews([source], lane=lane, policy=LANE_IO)[0]
    assert not excluded & set(preview)
    assert preview["images"] == source["images"]
    assert preview["source_revisions"] == source["source_revisions"]
    task = {"task_id": "server-id", "source": source, "brief": "Reply", "proposal_response": None}
    view = assignment_view([task], lane)[0]
    assert not excluded & set(view["source"])
    assert view["task_id"] == "server-id"
    assert source == original
    view["source"]["images"].clear()
    assert source == original
    assert target_view(source, "inbox" if lane == "feed" else "feed") != target_view(source, lane)


def test_new_feed_draft_uses_server_task_and_rejects_even_null_response_fields():
    task = {"task_id": "server-id", "target_post_id": "post", "scope": "feed", "action_index": 0,
        "source": candidate(), "brief": "Respond", "interaction_intent": "ordinary_comment",
        "comment_purpose": "question", "proposal_response": None}
    fields = draft_schema("feed", policy=LANE_IO)["properties"]["replies"]["items"]["properties"]
    assert not {"task_id", "proposal_decision", "counter_target_date"} & set(fields)
    value = {"replies": [{"target_id": "post", "body": "어떤 책이 도움이 됐나요?", "thought": "궁금하다."}]}
    result = parse_social_draft(value, lane="feed", assignments=[task], policy=LANE_IO)
    assert result["reply_task_results"][0]["task_id"] == "server-id"
    value["replies"][0]["proposal_decision"] = None
    with pytest.raises(ValueError, match="field_forbidden"):
        parse_social_draft(value, lane="feed", assignments=[task], policy=LANE_IO)


@pytest.mark.parametrize("io", [COMMON_IO, LANE_IO])
@pytest.mark.parametrize("routine", [LEGACY_ROUTINE_OUTPUT, BOUNDED_ROUTINE_OUTPUT])
def test_policies_are_independent_and_not_part_of_public_completion(io, routine):
    metadata = {"social_io_policy": io, "routine_output_policy": routine,
        "paths": {"routine": {"status": "completed"}}, "recovery_reservations": ["used"],
        "checkpoint_retention": {"state": "pruned"}}
    assert read_policies(metadata).model_dump() == {"social_io_policy": io, "routine_output_policy": routine}
    assert business_result(metadata) == {"paths": metadata["paths"], "recovery_reservations": ["used"]}
    assert read_policies(None).routine_output_policy == LEGACY_ROUTINE_OUTPUT


class RequiredDecision(BaseModel):
    chosen: str


@pytest.mark.parametrize("responses,expected_caps,valid", [
    ([('{"chosen":"same"}', "STOP")], [8192], True),
    ([('{"chosen":', "MAX_TOKENS"), ('{"chosen":"same"}', "STOP")], [8192, 16384], True),
    ([('{"chosen":', "MAX_TOKENS"), ('{"chosen":', "MAX_TOKENS")], [8192, 16384], False),
    ([('{"chosen":"same"}', "MAX_TOKENS")], [8192], True),
    ([('{"chosen":', "STOP")], [8192], False),
])
def test_split_routine_uses_real_json_transport_and_only_one_bounded_retry(monkeypatch, responses, expected_caps, valid):
    calls, reservations, normal, guards = [], [], [], []
    replies = list(responses)
    async def generate_text(**kwargs):
        calls.append(kwargs)
        text, finish = replies.pop(0)
        return direct_llm.DirectLlmResponse(text, None, {}, finish)
    async def guard(attempt):
        guards.append(attempt)
    monkeypatch.setattr(direct_llm, "generate_text", generate_text)
    monkeypatch.setattr(transport, "_api_key", lambda _: "synthetic")
    monkeypatch.setattr(transport, "_llm_context", lambda *a, **k: direct_llm.DirectLlmCallContext(
        "credential", "actor", "activity", k["node"], k["lane"], "google", "gemini-3.1-flash-lite"))
    provider = CombinedActivityProvider(SimpleNamespace(generation_thinking_level="high", on_rate_limit_wait=None),
        direct_llm.RunLlmTracker(max_calls=15), ledger=SimpleNamespace(reserve=reservations.append,
            reserve_normal=normal.append), policies=new_policies())
    provider.mode = "split"
    provider.request_guard = provider.retry_guard = guard
    request = provider.call(node="RoutineActionPlanner", lane="routine_action_planner", system="Same scene",
        payload={"activity": "frozen", "source": "verified"}, schema={"type": "object"},
        validator=RequiredDecision.model_validate, max_tokens=4096)
    if valid:
        assert asyncio.run(request).chosen == "same"
    else:
        with pytest.raises(direct_llm.DirectLlmError):
            asyncio.run(request)
    assert [call["max_output_tokens"] for call in calls] == expected_caps
    assert all(call["thinking_level"] == "high" for call in calls)
    assert reservations == (["RoutineActionPlanner:json"] if len(calls) == 2 else [])
    assert len(guards) == len(calls)
    assert len(normal) == 1 and normal[0].startswith("RoutineActionPlanner:")
