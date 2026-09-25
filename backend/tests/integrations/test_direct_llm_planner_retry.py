import asyncio
import hashlib

import pytest

from app.integrations import direct_llm
from app.providers.contracts import ProviderCapabilities, ProviderResponse, ProviderUsage
from app.runtime.autonomous_activity.output_recovery import planner_json_retry
from app.runtime.autonomous_activity.planner_contract import parse_action


def _context():
    return direct_llm.DirectLlmCallContext(
        "credential", "character", "run", "InboxActionPlanner",
        "inbox_action_planner", "google", "gemini-3.1-flash-lite")


def _candidate():
    return {"target_id": "post-1", "source_ids": ["post-1"],
            "allowed_actions": ["like"]}


def _payload(brief=None):
    decision = {"target_id": "post-1", "action": "like"}
    if brief is not None:
        decision["brief"] = brief
    return {"decisions": [decision], "state_update": None}


def _run(monkeypatch, responses, *, user="input", guard=None, max_calls=2):
    sent, events = [], []
    tracker = direct_llm.RunLlmTracker(max_calls=max_calls, observer=lambda kind, payload:
                                       events.append((kind, payload.copy())))
    async def fake_generate_text(**kwargs):
        sent.append(kwargs)
        order = tracker.next_call_order()
        kwargs["on_request_start"](order)
        tracker.record_call(context=kwargs["context"], call_order=order,
                            provider_call_order=tracker.next_provider_call_order(),
                            status="ok", duration_ms=1, usage={},
                            max_output_tokens=kwargs["max_output_tokens"])
        return responses.pop(0)
    monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)
    async def execute():
        return await direct_llm.generate_json(
            api_key="key", context=_context(), tracker=tracker,
            system_prompt="system", user_prompt=user, response_schema={},
            validator=lambda value: parse_action(value, [_candidate()]),
            max_output_tokens=4096, json_retry_policy=planner_json_retry,
            retry_input_char_limit=64000, before_json_retry=guard,
            sdk_attempts=1)
    return execute, sent, events, tracker


def test_stop_missing_brief_regenerates_once_with_safe_feedback_and_distinct_receipts(monkeypatch):
    responses = [direct_llm.DirectLlmResponse("", _payload(), {}, "STOP"),
                 direct_llm.DirectLlmResponse("", _payload("Notice care"), {}, "STOP")]
    guard_calls = []
    async def guard(attempt):
        guard_calls.append(attempt)
    execute, sent, events, tracker = _run(monkeypatch, responses, guard=guard)
    result = asyncio.run(execute())
    assert result["decisions"][0]["brief"] == "Notice care"
    assert [call["max_output_tokens"] for call in sent] == [4096, 4096]
    assert [call["sdk_attempts"] for call in sent] == [1, 1]
    assert guard_calls == [2]
    assert "action_brief_missing at decisions.0.brief" in sent[1]["user_prompt"]
    assert "Notice care" not in sent[1]["user_prompt"]
    inputs = [row for kind, row in events if kind == "json_attempt_input"]
    assert [row["json_attempt"] for row in inputs] == [1, 2]
    assert inputs[0]["input_sha256"] != inputs[1]["input_sha256"]
    assert inputs[1]["input_sha256"] == hashlib.sha256(
        ("system\n" + sent[1]["user_prompt"]).encode()).hexdigest()
    assert tracker.summary()["call_count"] == 2
    assert tracker.calls[0]["json_postprocess_error"]["validation_code"] == "action_brief_missing"


def test_truncated_unterminated_string_retries_at_larger_limit(monkeypatch):
    responses = [
        direct_llm.DirectLlmResponse('{"decisions":[{"brief":"unfinished', None, {}, "MAX_TOKENS"),
        direct_llm.DirectLlmResponse("", _payload("Recognize detail"), {}, "STOP"),
    ]
    execute, sent, events, _ = _run(monkeypatch, responses)
    assert asyncio.run(execute())["decisions"][0]["brief"] == "Recognize detail"
    assert [call["max_output_tokens"] for call in sent] == [4096, 8192]
    first = [row for kind, row in events if kind == "json_postprocess_error"][0]
    assert first["json_postprocess_error"]["shape_hint"] == "truncated_or_unclosed"
    assert [row["status"] for kind, row in events if kind == "json_attempt"] == [
        "retry_scheduled", "valid"]


def test_second_failure_stops_even_when_type_changes(monkeypatch):
    responses = [direct_llm.DirectLlmResponse("", _payload(), {}, "STOP"),
                 direct_llm.DirectLlmResponse('{"decisions":[', None, {}, "MAX_TOKENS")]
    execute, sent, _, _ = _run(monkeypatch, responses)
    with pytest.raises(direct_llm.DirectLlmJsonError) as caught:
        asyncio.run(execute())
    assert caught.value.attempt_count == 2
    assert caught.value.json_error_diagnostics[0]["validation_code"] == "action_brief_missing"
    assert len(sent) == 2


def test_retry_guard_or_input_limit_stops_before_second_request(monkeypatch):
    async def guard(_attempt):
        raise ValueError("activity_source_changed")
    responses = [direct_llm.DirectLlmResponse("", _payload(), {}, "STOP")]
    execute, sent, _, _ = _run(monkeypatch, responses, guard=guard)
    with pytest.raises(ValueError, match="activity_source_changed"):
        asyncio.run(execute())
    assert len(sent) == 1
    responses = [direct_llm.DirectLlmResponse("", _payload(), {}, "STOP")]
    execute, sent, _, _ = _run(monkeypatch, responses, user="x" * 63990)
    with pytest.raises(ValueError, match="activity_input_budget_exceeded"):
        asyncio.run(execute())
    assert len(sent) == 1


def test_unrelated_stop_errors_are_not_regenerated(monkeypatch):
    responses = [direct_llm.DirectLlmResponse('{"decisions":', None, {}, "STOP")]
    execute, sent, _, _ = _run(monkeypatch, responses)
    with pytest.raises(direct_llm.DirectLlmJsonError):
        asyncio.run(execute())
    assert len(sent) == 1


def test_valid_max_tokens_result_does_not_retry_and_two_brief_failures_keep_code(monkeypatch):
    execute, sent, _, _ = _run(monkeypatch, [
        direct_llm.DirectLlmResponse("", _payload("Useful observation"), {}, "MAX_TOKENS")])
    assert asyncio.run(execute())["decisions"][0]["brief"] == "Useful observation"
    assert len(sent) == 1
    execute, sent, _, _ = _run(monkeypatch, [
        direct_llm.DirectLlmResponse("", _payload(), {}, "STOP"),
        direct_llm.DirectLlmResponse("", _payload(" "), {}, "STOP")])
    with pytest.raises(direct_llm.DirectLlmJsonError) as caught:
        asyncio.run(execute())
    assert caught.value.attempt_count == 2
    assert (caught.value.validation_code, caught.value.field_path) == (
        "action_brief_missing", "decisions.0.brief")
    assert len(sent) == 2


def test_retry_options_conflict_is_rejected_before_provider_request(monkeypatch):
    execute, sent, _, _ = _run(monkeypatch, [])
    with pytest.raises(ValueError, match="json_retry_options_conflict"):
        asyncio.run(direct_llm.generate_json(
            api_key="key", context=_context(), tracker=direct_llm.RunLlmTracker(),
            system_prompt="system", user_prompt="input", response_schema={},
            json_retry_policy=planner_json_retry,
            should_retry_json_error=lambda *_: True))
    assert sent == []


def test_delivery_failure_is_not_reclassified_as_bad_json(monkeypatch):
    _, sent, _, tracker = _run(monkeypatch, [
        direct_llm.DirectLlmResponse("", _payload("Useful observation"), {}, "STOP")])
    async def fail_delivery():
        def callback():
            raise ValueError("feed_delivery_failed")
        return await direct_llm.generate_json(
            api_key="key", context=_context(), tracker=tracker,
            system_prompt="system", user_prompt="input", response_schema={},
            validator=lambda value: parse_action(value, [_candidate()]),
            on_response=callback, json_retry_policy=planner_json_retry)
    with pytest.raises(ValueError, match="feed_delivery_failed"):
        asyncio.run(fail_delivery())
    assert len(sent) == 1


def test_sdk_attempt_option_reaches_provider_request_and_budget_blocks_send(monkeypatch):
    direct_llm._RATE_LIMITER._buckets.clear()
    class Adapter:
        capabilities = ProviderCapabilities(text=True, structured_json=True)
        def __init__(self):
            self.requests = []
            self.parsed = {"ok": True}
        async def generate_json(self, request):
            self.requests.append(request)
            return ProviderResponse("", self.parsed, ProviderUsage(), "STOP")
        async def generate_text(self, request):
            self.requests.append(request)
            return ProviderResponse("ok", None, ProviderUsage(), "STOP")
    adapter = Adapter()
    monkeypatch.setattr(direct_llm, "get_provider_adapter", lambda *_: adapter)
    async def no_wait(**_kwargs):
        return None
    monkeypatch.setattr(direct_llm._RATE_LIMITER, "wait_if_needed", no_wait)
    tracker = direct_llm.RunLlmTracker(max_calls=1)
    result = asyncio.run(direct_llm.generate_json(
        api_key="key", context=_context(), tracker=tracker,
        system_prompt="system", user_prompt="input", response_schema={},
        sdk_attempts=1, should_retry_json_error=lambda *_: False))
    assert result == {"ok": True}
    assert adapter.requests[0].sdk_attempts == 1
    with pytest.raises(direct_llm.DirectLlmMaxCallsExceeded):
        asyncio.run(direct_llm.generate_json(
            api_key="key", context=_context(), tracker=tracker,
            system_prompt="system", user_prompt="input", response_schema={},
            sdk_attempts=1))
    assert len(adapter.requests) == 1
    assert tracker.provider_call_order_in_run == 1
    asyncio.run(direct_llm.generate_json(
        api_key="key", context=_context(), tracker=direct_llm.RunLlmTracker(max_calls=1),
        system_prompt="system", user_prompt="input", response_schema={}))
    assert adapter.requests[-1].sdk_attempts is None
    adapter.parsed = _payload()
    events = []
    limited = direct_llm.RunLlmTracker(
        max_calls=1, observer=lambda kind, payload: events.append((kind, payload.copy())))
    with pytest.raises(direct_llm.DirectLlmMaxCallsExceeded):
        asyncio.run(direct_llm.generate_json(
            api_key="key", context=_context(), tracker=limited,
            system_prompt="system", user_prompt="input", response_schema={},
            validator=lambda value: parse_action(value, [_candidate()]),
            json_retry_policy=planner_json_retry, sdk_attempts=1))
    assert len(adapter.requests) == 3
    assert limited.provider_call_order_in_run == 1
    assert len([kind for kind, _ in events if kind == "json_attempt_input"]) == 1
