import pytest
from pydantic import ValidationError

from app.domains.relationships.policies.interpretation_prompt import with_metric_schema
from app.providers.contracts import StructuredOutputValidationError
from app.providers.gemini import build_generate_content_config
from app.runtime.autonomous_activity.planner_contract import (
    ACTIVE_ACTIONS, parse_action, planner_response_schema,
)


def _candidate(actions=None):
    return {"target_id": "post-1", "source_ids": ["post-1"],
            "allowed_actions": actions or list(ACTIVE_ACTIONS)}


def _decision(action, brief_marker=None):
    decision = {"target_id": "post-1", "action": action}
    if brief_marker is not None:
        decision["brief"] = brief_marker
    if action == "comment":
        decision.update(interaction_intent="ordinary_comment", comment_purpose="question")
    return decision


@pytest.mark.parametrize("action", ACTIVE_ACTIONS)
@pytest.mark.parametrize("brief", [None, "", "   "])
def test_actual_actions_require_nonblank_brief_with_safe_path(action, brief):
    with pytest.raises(StructuredOutputValidationError) as caught:
        parse_action({"decisions": [_decision(action, brief)]}, [_candidate()])
    assert caught.value.validation_code == "action_brief_missing"
    assert caught.value.field_path == "decisions.0.brief"
    assert str(caught.value) == "action_brief_missing"


def test_no_action_and_subset_decisions_remain_valid():
    assert parse_action({"decisions": [_decision("no_action")]}, [_candidate()])["decisions"][0]["brief"] == ""
    assert parse_action({"decisions": [_decision("no_action", "")]}, [_candidate()])["decisions"][0]["action"] == "no_action"
    assert parse_action({"decisions": []}, [_candidate()])["decisions"] == []


def test_brief_length_and_optional_state_contract():
    text = "가" * 280
    result = parse_action({"decisions": [_decision("like", text)],
                           "state_update": {"mood": "invalid", "mood_intensity": 101}}, [_candidate()])
    assert result["decisions"][0]["brief"] == text
    assert result["state_status"] == "invalid"
    assert result["state_update"] is None
    with pytest.raises(ValidationError):
        parse_action({"decisions": [_decision("like", text + "가")]}, [_candidate()])


def test_other_invalid_decisions_are_rejected_with_distinct_codes():
    with pytest.raises(StructuredOutputValidationError) as target:
        parse_action({"decisions": [{"target_id": "other", "action": "no_action"}]}, [_candidate()])
    assert (target.value.validation_code, target.value.field_path) == (
        "decision_target_invalid", "decisions.0.target_id")
    with pytest.raises(StructuredOutputValidationError) as duplicate:
        parse_action({"decisions": [_decision("no_action"), _decision("no_action")]}, [_candidate()])
    assert duplicate.value.validation_code == "decision_target_invalid"
    with pytest.raises(StructuredOutputValidationError) as forbidden:
        parse_action({"decisions": [_decision("follow", "Say hello")]}, [_candidate(["like"])])
    assert forbidden.value.validation_code == "decision_action_not_allowed"


def test_transport_schema_keeps_target_bound_and_conditional_brief_in_sdk():
    schema = with_metric_schema(planner_response_schema([_candidate()]))
    decisions = schema["properties"]["decisions"]
    assert decisions["maxItems"] == 1
    item = decisions["items"]
    assert item["properties"]["target_id"]["enum"] == ["post-1"]
    assert item["properties"]["brief"]["maxLength"] == 280
    assert item["anyOf"] == [
        {"properties": {"action": {"type": "string", "enum": ["no_action"]}},
         "required": ["action"]},
        {"properties": {"action": {"type": "string", "enum": list(ACTIVE_ACTIONS)}},
         "required": ["action", "brief"]},
    ]
    assert "interaction_intent" in item["properties"]
    assert "relationship_metrics" in schema["properties"]
    config = build_generate_content_config(
        model="gemini-3.1-flash-lite", system_prompt="test", max_output_tokens=4096,
        response_mime_type="application/json", response_schema=schema, thinking_level="low",
    )
    sent = config.model_dump(mode="json", by_alias=True, exclude_none=True)["responseJsonSchema"]
    assert sent["properties"]["decisions"]["items"]["anyOf"] == item["anyOf"]
