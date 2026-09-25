import asyncio
import json

import pytest
from pydantic import BaseModel

from app.integrations import direct_llm
from app.providers.contracts import StructuredOutputValidationError
from app.runtime.autonomous_activity.output_recovery import (
    MAX_CALL_BUDGET, NORMAL_CALL_BUDGET, RECOVERY_CALL_BUDGET,
    planner_json_retry, retry_truncated_json,
)


class _Required(BaseModel):
    selected: str
    reason: str


def test_retry_policy_is_limited_to_unusable_truncated_output():
    assert (NORMAL_CALL_BUDGET, RECOVERY_CALL_BUDGET, MAX_CALL_BUDGET) == (10, 5, 15)
    truncated = {"finish_reason": "MAX_TOKENS", "shape_hint": "truncated_or_unclosed"}
    assert retry_truncated_json(ValueError(), None, truncated, 1)
    assert not retry_truncated_json(ValueError(), None, {**truncated, "finish_reason": "STOP"}, 1)
    assert not retry_truncated_json(ValueError(), {"selected": "wrong"}, truncated, 1)
    assert not retry_truncated_json(ValueError(), None, truncated, 2)
    with pytest.raises(Exception) as missing:
        _Required.model_validate({"selected": "p"})
    assert retry_truncated_json(missing.value, {"selected": "p"}, truncated, 1)


def test_planner_policy_recovers_only_observed_failures():
    unfinished = '{"decisions":[{"brief":"unfinished'
    exc = None
    try:
        json.loads(unfinished)
    except json.JSONDecodeError as caught:
        exc = caught
    assert exc is not None
    truncated = {"finish_reason": "MAX_TOKENS", "shape_hint": "bad_escape"}
    assert retry_truncated_json(exc, None, truncated, 1)
    decision = planner_json_retry(exc, None, truncated, 1)
    assert (decision.reason_code, decision.max_output_tokens) == (
        "planner_output_truncated", 8192)
    brief = StructuredOutputValidationError("action_brief_missing", "decisions.0.brief")
    stopped = planner_json_retry(brief, {"decisions": []},
                                 {"finish_reason": "STOP"}, 1)
    assert (stopped.reason_code, stopped.max_output_tokens) == (
        "action_brief_missing", 4096)
    assert "decisions.0.brief" in stopped.feedback
    assert planner_json_retry(exc, None, {"finish_reason": "STOP"}, 1) is None
    assert planner_json_retry(ValueError("private message"), None, truncated, 1) is None
    assert planner_json_retry(StructuredOutputValidationError(
        "decision_target_invalid", "decisions.0.target_id"),
        {}, {"finish_reason": "STOP"}, 1) is None
    assert planner_json_retry(brief, {}, {"finish_reason": "STOP"}, 2) is None


def _context():
    return direct_llm.DirectLlmCallContext("cred", "actor", "run", "RoutineWriter",
        "routine_writer", "google", "gemini-3.1-flash-lite")


def test_retry_uses_larger_cap_and_guard_before_second_provider_request(monkeypatch):
    tracker = direct_llm.RunLlmTracker(max_calls=2)
    seen = []
    responses = [
        direct_llm.DirectLlmResponse('{"selected":', None, {}, "MAX_TOKENS"),
        direct_llm.DirectLlmResponse('{"selected":"p","reason":"ok"}', None, {}, "STOP"),
    ]
    async def generate_text(**kwargs):
        seen.append(("provider", kwargs["max_output_tokens"]))
        return responses.pop(0)
    async def guard(attempt):
        seen.append(("guard", attempt))
    monkeypatch.setattr(direct_llm, "generate_text", generate_text)
    result = asyncio.run(direct_llm.generate_json(api_key="key", context=_context(), tracker=tracker,
        system_prompt="system", user_prompt="user", response_schema={},
        validator=lambda p: _Required.model_validate(p),
        max_output_tokens=4096, retry_max_output_tokens=8192,
        should_retry_json_error=retry_truncated_json, before_json_retry=guard))
    assert result.selected == "p"
    assert seen == [("provider", 4096), ("guard", 2), ("provider", 8192)]


def test_retry_guard_failure_preserves_original_error_and_does_not_send_again(monkeypatch):
    seen = []
    async def generate_text(**kwargs):
        seen.append("provider")
        return direct_llm.DirectLlmResponse('{"selected":', None, {}, "MAX_TOKENS")
    async def guard(_attempt):
        raise ValueError("activity_source_changed")
    monkeypatch.setattr(direct_llm, "generate_text", generate_text)
    with pytest.raises(ValueError, match="activity_source_changed"):
        asyncio.run(direct_llm.generate_json(api_key="key", context=_context(),
            tracker=direct_llm.RunLlmTracker(max_calls=2), system_prompt="system", user_prompt="user",
            response_schema={}, max_output_tokens=4096, retry_max_output_tokens=8192,
            should_retry_json_error=retry_truncated_json, before_json_retry=guard))
    assert seen == ["provider"]


@pytest.mark.parametrize("finish,text,expected", [
    ("STOP", '{"selected":', 1),
    ("MAX_TOKENS", '{"selected":"p","reason":"ok"}', 1),
])
def test_stop_error_or_complete_max_tokens_do_not_retry(monkeypatch, finish, text, expected):
    seen = []
    async def generate_text(**kwargs):
        seen.append(kwargs["max_output_tokens"])
        return direct_llm.DirectLlmResponse(text, None, {}, finish)
    monkeypatch.setattr(direct_llm, "generate_text", generate_text)
    async def run():
        return await direct_llm.generate_json(api_key="key", context=_context(),
            tracker=direct_llm.RunLlmTracker(max_calls=2), system_prompt="system", user_prompt="user",
            response_schema={}, validator=lambda p: _Required.model_validate(p),
            max_output_tokens=4096, retry_max_output_tokens=8192,
            should_retry_json_error=retry_truncated_json)
    if finish == "STOP":
        with pytest.raises(direct_llm.DirectLlmJsonError):
            asyncio.run(run())
    else:
        assert asyncio.run(run()).selected == "p"
    assert len(seen) == expected
