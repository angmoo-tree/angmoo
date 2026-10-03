"""Independent source/wire oracle and strict missing-comment recovery regressions."""
import asyncio
from copy import deepcopy
import json
from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel
import pytest

from app.domains.world_characters.contracts.social_io import LANE_IO
from app.integrations import direct_llm
from app.providers.contracts import StructuredOutputValidationError
from app.providers.gemini import build_gemini_developer_response_schema
from app.runtime.autonomous_activity.output_recovery import planner_json_retry
from app.runtime.autonomous_activity.planner_contract import parse_action
from app.runtime.autonomous_activity.social_wire import judgement_model

pytestmark = pytest.mark.usefixtures("deny_external_network")


def candidate(key="post"):
    return {"target_id": key, "allowed_actions": ["comment", "like"], "source_ids": [key]}


@pytest.mark.parametrize("lane,capable", [("feed", False), ("feed", True), ("inbox", False), ("inbox", True)])
def test_source_and_wire_intent_values_are_equivalent(lane, capable):
    item = candidate()
    if capable:
        item["proposal_eligible" if lane == "feed" else "activity_proposal"] = True
    model = judgement_model(lane, [item])
    source = model.model_json_schema()
    wire = build_gemini_developer_response_schema(model)
    for intent in [None, "ordinary_comment", "joint_activity_proposal", "proposal_response", "bad", ""]:
        data = {"state_update": None, "decisions": [{"target_id": "post", "action": "no_action", "interaction_intent": intent}]}
        assert Draft202012Validator(source).is_valid(data) == Draft202012Validator(wire).is_valid(data)


@pytest.mark.parametrize("constant", ["", "ordinary_comment", 0, 3.25, None])
def test_const_lowering_and_required_are_not_lost(constant):
    source = {"type": "object", "properties": {"const": {"const": constant}}, "required": ["const"]}
    class Model:
        @staticmethod
        def model_json_schema():
            return source
    saved = deepcopy(source)
    wire = build_gemini_developer_response_schema(Model)
    for value in [None, "", "ordinary_comment", "wrong", 0, 1, 3.25, True]:
        assert Draft202012Validator(source).is_valid({"const": value}) == Draft202012Validator(wire).is_valid({"const": value})
    assert not Draft202012Validator(wire).is_valid({})
    wire["properties"]["const"]["description"] = "changed"
    assert source == saved


@pytest.mark.parametrize("value", [True, {}, [], float("inf")])
def test_unsupported_const_fails_before_transport(value):
    class Model:
        @staticmethod
        def model_json_schema():
            return {"const": value}
    with pytest.raises(ValueError):
        build_gemini_developer_response_schema(Model)


@pytest.mark.parametrize("missing,path", [("intent", "interaction_intent"), ("purpose", "comment_purpose"), ("both", "interaction_intent")])
def test_verified_missing_path_is_recoverable_once(missing, path):
    row = {"target_id": "post", "action": "comment", "brief": "Ask about the book", "interaction_intent": "ordinary_comment", "comment_purpose": "question"}
    if missing in {"intent", "both"}:
        row.pop("interaction_intent")
    if missing in {"purpose", "both"}:
        row.pop("comment_purpose")
    payload = {"decisions": [row], "state_update": None}
    with pytest.raises(StructuredOutputValidationError) as error:
        parse_action(payload, [candidate()], lane="inbox", policy=LANE_IO)
    assert error.value.field_path == f"decisions.0.{path}"
    retry = planner_json_retry(error.value, payload, {"finish_reason": "STOP"}, 1)
    assert retry is not None and retry.max_output_tokens == 4096
    assert planner_json_retry(error.value, payload, {"finish_reason": "STOP"}, 2) is None
    assert planner_json_retry(error.value, payload, {"finish_reason": "MAX_TOKENS"}, 1) is None


def test_fatal_other_target_takes_precedence_over_missing_intent():
    payload = {"state_update": None, "decisions": [
        {"target_id": "post", "action": "comment", "brief": "Ask"},
        {"target_id": "not-a-candidate", "action": "like", "brief": "Recognize"},
    ]}
    with pytest.raises(StructuredOutputValidationError) as error:
        parse_action(payload, [candidate()], lane="feed", policy=LANE_IO)
    assert error.value.validation_code == "decision_target_invalid"
    assert planner_json_retry(error.value, payload, {"finish_reason": "STOP"}, 1) is None


def test_missing_then_valid_preserves_input_and_has_no_third_request(monkeypatch):
    payloads = [
        {"state_update": None, "decisions": [{"target_id": "post", "action": "comment", "brief": "Ask"}]},
        {"state_update": None, "decisions": [{"target_id": "post", "action": "comment", "brief": "Ask", "interaction_intent": "ordinary_comment", "comment_purpose": "question"}]},
    ]
    calls, guards = [], []
    async def generate(**kwargs):
        calls.append(kwargs)
        return direct_llm.DirectLlmResponse(json.dumps(payloads[len(calls)-1]), None, {}, "STOP")
    async def guard(attempt):
        guards.append(attempt)
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    context = direct_llm.DirectLlmCallContext("fixture", "actor", "run", "InboxActionPlanner", "inbox", "google", "gemini-3.1-flash-lite")
    result = asyncio.run(direct_llm.generate_json(api_key="synthetic-key", context=context,
        tracker=direct_llm.RunLlmTracker(max_calls=2), system_prompt="Original instructions",
        user_prompt="Original context", response_schema={}, max_output_tokens=4096,
        validator=lambda value: parse_action(value, [candidate()], lane="inbox", policy=LANE_IO),
        json_retry_policy=planner_json_retry, before_json_retry=guard, sdk_attempts=1,
        retry_input_char_limit=64000))
    assert result["decisions"][0]["interaction_intent"] == "ordinary_comment"
    assert len(calls) == 2 and guards == [2]
    assert calls[0]["system_prompt"] == calls[1]["system_prompt"]
    assert calls[1]["user_prompt"].startswith(calls[0]["user_prompt"])
    assert [call["max_output_tokens"] for call in calls] == [4096, 4096]


@pytest.mark.parametrize("order", [False, True])
def test_nullable_ref_nested_properties_and_source_isolation(order):
    variants = [{"$ref": "#/$defs/Leaf"}, {"type": "null"}]
    if order:
        variants.reverse()
    source = {"type": "object", "$defs": {"Leaf": {"type": "string", "enum": ["same"], "description": "Leaf"}},
        "properties": {"enum": {"anyOf": variants, "description": "Optional"}, "items": {"type": "array", "items": {"const": 0}}}, "required": ["enum", "items"]}
    class Model:
        @staticmethod
        def model_json_schema():
            return source
    saved = deepcopy(source)
    wire = build_gemini_developer_response_schema(Model)
    for value in [None, "same", "other"]:
        data = {"enum": value, "items": [0]}
        assert Draft202012Validator(source).is_valid(data) == Draft202012Validator(wire).is_valid(data)
    assert source == saved and build_gemini_developer_response_schema(Model) == wire


def test_real_sdk_http_preserves_nullable_enum_for_all_lanes(monkeypatch):
    import httpx
    from google import genai
    from google.genai import types
    from app.providers import gemini
    from app.providers.contracts import ProviderRequest
    original = genai.Client
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}]})
    def client(**kwargs):
        supplied = kwargs["http_options"]
        kwargs["http_options"] = types.HttpOptions(timeout=supplied.timeout,
            retry_options=supplied.retry_options, client_args={"transport": httpx.MockTransport(respond)})
        return original(**kwargs)
    monkeypatch.setattr(genai, "Client", client)
    for lane, capable in [("feed", False), ("feed", True), ("inbox", False), ("inbox", True)]:
        item = candidate()
        if capable:
            item["proposal_eligible" if lane == "feed" else "activity_proposal"] = True
        schema = build_gemini_developer_response_schema(judgement_model(lane, [item]))
        gemini._generate_content_sync(ProviderRequest(api_key="synthetic-key", model="gemini-3.1-flash-lite",
            system_prompt="Fixed instructions", user_prompt="Synthetic context", max_output_tokens=4096,
            timeout_seconds=5, response_schema=schema, response_mime_type="application/json", thinking_level="high"))
        wire = requests[-1]["generationConfig"]["responseJsonSchema"]
        assert wire == schema
        nullable = wire["properties"]["decisions"]["items"]["properties"]["interaction_intent"]
        assert nullable["anyOf"][-1] == {"type": "null"}
        native = gemini._native_parameters(nullable).model_dump(exclude_none=True)
        assert native["nullable"] is True and "ordinary_comment" in native["enum"]
    assert len(requests) == 4


@pytest.mark.parametrize("second", ["bad_target", "missing", "bad_json"])
def test_second_error_is_final_with_shared_retry_chance(monkeypatch, second):
    bad = {"state_update": None, "decisions": [{"target_id": "post", "action": "comment", "brief": "Ask"}]}
    later = deepcopy(bad)
    if second == "bad_target":
        later["decisions"][0]["target_id"] = "unknown"
    calls = []
    async def generate(**kwargs):
        calls.append(kwargs)
        text = json.dumps(bad if len(calls) == 1 else later)
        if len(calls) == 2 and second == "bad_json":
            text = "{"
        return direct_llm.DirectLlmResponse(text, None, {}, "STOP")
    monkeypatch.setattr(direct_llm, "generate_text", generate)
    context = direct_llm.DirectLlmCallContext("fixture", "actor", "run", "FeedActionPlanner", "feed", "google", "gemini-3.1-flash-lite")
    with pytest.raises(direct_llm.DirectLlmJsonError) as error:
        asyncio.run(direct_llm.generate_json(api_key="synthetic-key", context=context,
            tracker=direct_llm.RunLlmTracker(max_calls=2), system_prompt="system", user_prompt="user",
            response_schema={}, max_output_tokens=4096, validator=lambda value: parse_action(value, [candidate()], lane="feed", policy=LANE_IO),
            json_retry_policy=planner_json_retry, retry_input_char_limit=64000, sdk_attempts=1))
    assert len(calls) == 2 and error.value.attempt_count == 2
