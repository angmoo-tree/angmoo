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


def test_budget_removes_whole_optional_records_without_mutating_shared_input(monkeypatch):
    import asyncio, json
    from types import SimpleNamespace
    from app.runtime.autonomous_activity import provider as module
    async def scenario():
        context = SimpleNamespace(credential=None, character=None)
        actor = module.ActivityProvider(context, None)
        monkeypatch.setattr(module, "_api_key", lambda _: "test")
        monkeypatch.setattr(module, "_llm_context", lambda *args, **kwargs: None)
        context.generation_thinking_level = None
        context.on_rate_limit_wait = None
        captured = {}
        async def generate(**kwargs):
            captured.update(json.loads(kwargs["user_prompt"]))
            return {}
        monkeypatch.setattr(module, "generate_json", generate)
        payload = {"context":{"today_activity":{"records":[{"body":"a"*35000},{"body":"b"*35000}]},"memories":{}},"required_source":"Negation must remain intact."}
        await actor.call(node="test",lane="feed",system="rules",payload=payload,schema={},validator=lambda x:x,max_tokens=100)
        assert len(captured["context"]["today_activity"]["records"]) == 1
        assert captured["required_source"] == payload["required_source"]
        assert captured["context"]["input_omissions"]["today_activity"] == 1
        assert len(payload["context"]["today_activity"]["records"]) == 2
        with pytest.raises(ValueError,match="activity_input_budget_exceeded"):
            await actor.call(node="test",lane="feed",system="rules",payload={"source":"x"*65000},schema={},validator=lambda x:x,max_tokens=100)
    asyncio.run(scenario())
