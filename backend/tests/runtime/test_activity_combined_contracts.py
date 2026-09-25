import asyncio
from types import SimpleNamespace

import pytest

from app.runtime.autonomous_activity.generation_contracts import parse_envelope, parse_social_draft
from app.runtime.autonomous_activity.planner_contract import parse_action
from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider, RecoveryLedger
from app.runtime.autonomous_activity import provider as transport


def test_valid_decision_survives_invalid_draft_but_invalid_decision_does_not():
    candidates = [{"target_id": "p", "allowed_actions": ["like"], "source_ids": ["p"]}]
    value = {"decision": {"decisions": [{"target_id": "p", "action": "like", "brief": "응원"}],
                          "state_update": None}, "draft": None}
    assert parse_envelope(value, lambda v: parse_action(v, candidates))["decisions"][0]["action"] == "like"
    value["decision"]["decisions"][0]["target_id"] = "other"
    with pytest.raises(ValueError, match="decision_target_invalid"):
        parse_envelope(value, lambda v: parse_action(v, candidates))


def assignment(target="p"):
    return {"task_id": "canonical-" + target, "target_post_id": target, "scope": "feed",
            "action_index": 0, "source": {"target_id": target}, "brief": "응원",
            "interaction_intent": "ordinary_comment", "comment_purpose": "empathize",
            "proposal_response": None}


@pytest.mark.parametrize("replies", [[], [{"target_id": "other", "body": "hello"}],
    [{"target_id": "p", "body": "hello"}] * 2, [{"target_id": "p", "body": "x" * 501}],
    [{"target_id": "p", "body": "hello", "task_id": "invented"}],
    [{"target_id": "p", "body": "hello", "proposal_decision": "accept"}]])
def test_combined_writer_rejects_changed_identity_count_length_or_proposal(replies):
    with pytest.raises(ValueError):
        parse_social_draft({"replies": replies}, lane="feed", assignments=[assignment()])


def test_combined_writer_uses_code_owned_task_and_keeps_thought():
    result = parse_social_draft({"replies": [{"target_id": "p", "body": "힘내세요!", "thought": "응원하고 싶다."}]},
                               lane="feed", assignments=[assignment()])
    assert result["reply_task_results"][0]["task_id"] == "canonical-p"
    assert result["reply_task_results"][0]["body"] == "힘내세요!"
    assert result["reply_task_results"][0]["_activity_thought"]


def test_recovery_reservation_survives_new_ledger_and_preserves_metadata():
    row = SimpleNamespace(contract_version=2, result={"paths": {"inbox": {"status": "completed"}}})
    db = SimpleNamespace(get=lambda *a, **k: row, commit=lambda: None)
    RecoveryLedger(db, "run").reserve("Inbox:writer")
    with pytest.raises(ValueError, match="recovery_exhausted"):
        RecoveryLedger(db, "run").reserve("Inbox:writer")
    for i in range(4):
        RecoveryLedger(db, "run").reserve(str(i))
    with pytest.raises(ValueError, match="recovery_exhausted"):
        RecoveryLedger(db, "run").reserve("sixth")
    assert row.result["paths"]["inbox"]["status"] == "completed"


def test_combined_social_calls_transport_once_and_retains_all_decision_fields(monkeypatch):
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        assert set(kwargs["response_schema"]["properties"]) == {"decision", "draft"}
        item = kwargs["response_schema"]["properties"]["draft"]["properties"]["replies"]["items"]
        assert "body" in item["required"]
        assert item["properties"]["body"]["type"] == "string"
        assert item["properties"]["target_id"]["enum"] == ["p"]
        return kwargs["validator"]({"decision": {"decisions": [{"target_id": "p", "action": "like", "brief": "응원"}],
            "state_update": None, "relationship_metrics": []}, "draft": {"replies": []}})
    monkeypatch.setattr(transport, "generate_json", generate)
    monkeypatch.setattr(transport, "_api_key", lambda _: "fake")
    monkeypatch.setattr(transport, "_llm_context", lambda *a, **k: None)
    p = CombinedActivityProvider(SimpleNamespace(generation_thinking_level=None, on_rate_limit_wait=None), None,
                                 ledger=SimpleNamespace(reserve=lambda key: None))
    result = asyncio.run(p.plan(lane="feed", context={}, candidates=[{
        "target_id": "p", "source_ids": ["p"], "allowed_actions": ["like"]}]))
    assert len(calls) == 1
    assert calls[0]["max_output_tokens"] == 8192
    assert result["state_status"] == "valid"
    assert "relationship_metrics" in result and "judged_at" in result
    assert result["provisional_draft"] == {"replies": []}
