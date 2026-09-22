import pytest

from app.runtime.autonomous_activity.provider import parse_action


def test_invalid_optional_state_keeps_valid_like_but_invalid_target_fails():
    candidate = {"target_id": "p", "source_ids": ["p"], "allowed_actions": ["like"]}
    payload = {"decisions": [{"target_id": "p", "action": "like", "brief": "Acknowledge"}],
        "state_update": {"mood": "invented", "mood_intensity": 101}}
    result = parse_action(payload, [candidate])
    assert result["decisions"][0]["action"] == "like"
    assert result["state_status"] == "invalid"
    assert result["state_update"] is None
    with pytest.raises(ValueError, match="decision_target_invalid"):
        parse_action({"decisions": [{"target_id": "other", "action": "no_action"}]}, [candidate])


def test_no_action_can_update_state_only_from_present_source():
    candidate = {"target_id": "p", "source_ids": ["p"], "allowed_actions": []}
    payload = {"decisions": [{"target_id": "p", "action": "no_action"}],
        "state_update": {"mood": "calm", "mood_intensity": 25, "state_note": "마음이 진정되었다."}, "state_source_refs": ["p"]}
    assert parse_action(payload, [candidate])["state_status"] == "valid"
    payload["state_source_refs"] = ["remembered-event"]
    assert parse_action(payload, [candidate])["state_status"] == "invalid"


def test_missing_state_is_invalid_auxiliary_but_explicit_null_is_keep():
    candidate = {"target_id": "p", "source_ids": ["p"], "allowed_actions": []}
    payload = {"decisions": [{"target_id": "p", "action": "no_action"}]}
    assert parse_action(payload, [candidate])["state_status"] == "invalid"
    assert parse_action({**payload, "state_update": None}, [candidate])["state_status"] == "valid"
