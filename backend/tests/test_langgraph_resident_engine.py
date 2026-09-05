import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from google.genai import errors as google_errors

from app.services import agent_runs, agent_writing, direct_llm




























































def test_generate_content_config_sets_thinking_level() -> None:
    config = direct_llm._generate_content_config(
        model="gemini-3.1-flash-lite",
        system_prompt="system",
        max_output_tokens=128,
        response_mime_type="application/json",
        response_schema=None,
        thinking_level="low",
    )

    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level.value == "LOW"


def test_generate_content_config_sets_medium_thinking_level() -> None:
    config = direct_llm._generate_content_config(
        model="gemini-3.1-flash-lite",
        system_prompt="system",
        max_output_tokens=128,
        response_mime_type="application/json",
        response_schema=None,
        thinking_level="medium",
    )

    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level.value == "MEDIUM"


def test_generate_content_config_omits_thinking_config_by_default() -> None:
    config = direct_llm._generate_content_config(
        model="gemini-3.1-flash-lite",
        system_prompt="system",
        max_output_tokens=128,
        response_mime_type="application/json",
        response_schema=None,
        thinking_level=None,
    )

    assert config.thinking_config is None


def test_generate_content_config_omits_sampling_parameters() -> None:
    config = direct_llm._generate_content_config(
        model="gemini-3.1-flash-lite",
        system_prompt="system",
        max_output_tokens=128,
        response_mime_type="application/json",
        response_schema=None,
        thinking_level="low",
    )
    payload = config.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert "temperature" not in payload
    assert "topP" not in payload
    assert "topK" not in payload


def test_writing_composition_stream_params_omit_sampling_parameters() -> None:
    params = agent_writing._writing_stream_params(SimpleNamespace())

    assert params == {}


def test_llm_tracker_records_thinking_level() -> None:
    tracker = direct_llm.RunLlmTracker(max_calls=1)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="ReplyWriter",
        lane="reply_writer",
        provider="google",
        model="gemini-3.1-flash-lite",
    )

    tracker.record_call(
        context=context,
        call_order=1,
        provider_call_order=1,
        status="ok",
        duration_ms=12,
        usage={},
        thinking_level="medium",
    )

    call = tracker.summary()["calls"][0]
    assert call["node"] == "ReplyWriter"
    assert call["lane"] == "reply_writer"
    assert call["call_type"] == "generate_content"
    assert call["thinking_level"] == "medium"


def test_generate_json_records_postprocess_error_on_repaired_success(monkeypatch) -> None:
    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="PostWriterPlanner",
        lane="post_writer_planner",
        provider="google",
        model="gemini-3.1-flash-lite",
    )
    responses = [
        direct_llm.DirectLlmResponse(
            text="not json AIza12345678901234567890",
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
        direct_llm.DirectLlmResponse(
            text='{"ok": true}',
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
    ]

    async def fake_generate_text(**kwargs):
        call_order = tracker.next_call_order()
        provider_call_order = tracker.next_provider_call_order()
        tracker.record_call(
            context=kwargs["context"],
            call_order=call_order,
            provider_call_order=provider_call_order,
            status="ok",
            duration_ms=1,
            usage={},
            thinking_level=kwargs.get("thinking_level"),
        )
        return responses.pop(0)

    monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)

    result = asyncio.run(
        direct_llm.generate_json(
            api_key="key",
            context=context,
            tracker=tracker,
            system_prompt="system",
            user_prompt="user",
            response_schema={},
        )
    )

    assert result == {"ok": True}
    summary = tracker.summary()
    assert summary["call_count"] == 2
    first_call = summary["calls"][0]
    assert first_call["json_postprocess_error"]["attempt"] == 1
    assert first_call["json_postprocess_error"]["shape_hint"] == "natural_text_only"
    assert "AIza12345678901234567890" not in first_call["json_postprocess_error"][
        "preview_head"
    ]


def test_generate_json_raises_with_diagnostics_after_two_parse_failures(
    monkeypatch,
) -> None:
    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="PostWriter",
        lane="post_writer",
        provider="google",
        model="gemini-3.1-flash-lite",
    )
    responses = [
        direct_llm.DirectLlmResponse(
            text="```json\n{}\n```",
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
        direct_llm.DirectLlmResponse(
            text='{"post_title": "broken"',
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
    ]

    async def fake_generate_text(**kwargs):
        call_order = tracker.next_call_order()
        provider_call_order = tracker.next_provider_call_order()
        tracker.record_call(
            context=kwargs["context"],
            call_order=call_order,
            provider_call_order=provider_call_order,
            status="ok",
            duration_ms=1,
            usage={},
        )
        return responses.pop(0)

    monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)

    with pytest.raises(direct_llm.DirectLlmJsonError) as exc_info:
        asyncio.run(
            direct_llm.generate_json(
                api_key="key",
                context=context,
                tracker=tracker,
                system_prompt="system",
                user_prompt="user",
                response_schema={},
            )
        )

    exc = exc_info.value
    assert exc.attempt_count == 2
    assert exc.parse_error_type == "JSONDecodeError"
    assert [item["attempt"] for item in exc.json_error_diagnostics] == [1, 2]
    assert exc.json_error_diagnostics[0]["shape_hint"] == "markdown_fence"
    assert exc.json_error_diagnostics[1]["shape_hint"] == "truncated_or_unclosed"
    assert exc.last_payload is None
    assert tracker.summary()["calls"][1]["json_postprocess_error"]["attempt"] == 2


def test_generate_json_schema_validation_diagnostic(monkeypatch) -> None:
    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="Supervisor",
        lane="supervisor",
        provider="google",
        model="gemini-3.1-flash-lite",
    )
    responses = [
        direct_llm.DirectLlmResponse(
            text='{"focus": "feed", "note": "' + ("A" * 900) + '"}',
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
        direct_llm.DirectLlmResponse(
            text='{"focus": "inbox", "note": "' + ("B" * 900) + '"}',
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
    ]

    async def fake_generate_text(**kwargs):
        call_order = tracker.next_call_order()
        provider_call_order = tracker.next_provider_call_order()
        tracker.record_call(
            context=kwargs["context"],
            call_order=call_order,
            provider_call_order=provider_call_order,
            status="ok",
            duration_ms=1,
            usage={},
        )
        return responses.pop(0)

    def validator(_payload):
        raise ValueError("schema validation failed")

    monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)

    with pytest.raises(direct_llm.DirectLlmJsonError) as exc_info:
        asyncio.run(
            direct_llm.generate_json(
                api_key="key",
                context=context,
                tracker=tracker,
                system_prompt="system",
                user_prompt="user",
                response_schema={},
                validator=validator,
            )
        )

    assert exc_info.value.json_error_diagnostics[0]["shape_hint"] == "schema_validation"
    assert exc_info.value.last_payload == {"focus": "inbox", "note": "B" * 900}
    assert tracker.summary()["calls"][0]["json_postprocess_error"]["response_length"] > 0
    calls_text = str(tracker.summary()["calls"])
    assert "B" * 900 not in calls_text
    assert "last_payload" not in calls_text


def test_generate_json_retry_hook_can_stop_after_first_validation_failure(
    monkeypatch,
) -> None:
    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="StateRecorder",
        lane="state_recorder",
        provider="google",
        model="gemini-3.1-flash-lite",
    )
    responses = [
        direct_llm.DirectLlmResponse(
            text='{"mood": "' + ("m" * 120) + '", "summary": "ok"}',
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
        direct_llm.DirectLlmResponse(
            text='{"mood": "retry should not happen", "summary": "ok"}',
            parsed=None,
            usage={},
            finish_reason="STOP",
        ),
    ]
    retry_calls: list[dict[str, object]] = []

    async def fake_generate_text(**kwargs):
        call_order = tracker.next_call_order()
        provider_call_order = tracker.next_provider_call_order()
        tracker.record_call(
            context=kwargs["context"],
            call_order=call_order,
            provider_call_order=provider_call_order,
            status="ok",
            duration_ms=1,
            usage={},
        )
        return responses.pop(0)

    def validator(payload):
        if len(payload["mood"]) > 80:
            raise ValueError("schema validation failed")
        return payload

    def stop_retry(exc, payload, diagnostic, attempt):
        retry_calls.append(
            {
                "exc": type(exc).__name__,
                "payload": payload,
                "shape_hint": diagnostic.get("shape_hint"),
                "attempt": attempt,
            }
        )
        return False

    monkeypatch.setattr(direct_llm, "generate_text", fake_generate_text)

    with pytest.raises(direct_llm.DirectLlmJsonError) as exc_info:
        asyncio.run(
            direct_llm.generate_json(
                api_key="key",
                context=context,
                tracker=tracker,
                system_prompt="system",
                user_prompt="user",
                response_schema={},
                validator=validator,
                should_retry_json_error=stop_retry,
            )
        )

    assert tracker.summary()["call_count"] == 1
    assert exc_info.value.attempt_count == 1
    assert exc_info.value.last_payload == {"mood": "m" * 120, "summary": "ok"}
    assert retry_calls == [
        {
            "exc": "ValueError",
            "payload": {"mood": "m" * 120, "summary": "ok"},
            "shape_hint": "schema_validation",
            "attempt": 1,
        }
    ]


def test_direct_llm_retries_provider_overload_once(monkeypatch) -> None:
    direct_llm._RATE_LIMITER._buckets.clear()
    responses: list[object] = [
        RuntimeError("503 UNAVAILABLE. This model is currently experiencing high demand."),
        SimpleNamespace(
            text="retry ok",
            parsed=None,
            usage_metadata=SimpleNamespace(
                prompt_token_count=3,
                candidates_token_count=2,
                total_token_count=5,
                cached_content_token_count=None,
            ),
            candidates=[],
        ),
    ]

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self.models = self

        def generate_content(self, **_kwargs):
            response = responses.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(direct_llm.genai, "Client", FakeClient)
    monkeypatch.setattr(direct_llm.asyncio, "sleep", fake_sleep)

    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="Supervisor",
        lane="supervisor",
        provider="google",
        model="gemini-3.1-flash-lite",
    )

    result = asyncio.run(
        direct_llm.generate_text(
            api_key="key",
            context=context,
            tracker=tracker,
            system_prompt="system",
            user_prompt="user",
        )
    )

    summary = tracker.summary()
    assert result.text == "retry ok"
    assert sleeps == [60.0]
    assert summary["call_count"] == 2
    assert summary["generate_call_count"] == 2
    assert summary["embedding_call_count"] == 0
    assert summary["provider_call_count"] == 2
    assert summary["calls"][0]["status"] == "error"
    assert summary["calls"][0]["provider_error_hint"] == "provider_overloaded"
    assert summary["calls"][1]["status"] == "ok"
    assert summary["rate_limit_waits"][0]["reason"] == "provider_overloaded_retry"


def test_direct_llm_retries_google_bad_gateway_once(monkeypatch) -> None:
    direct_llm._RATE_LIMITER._buckets.clear()
    responses: list[object] = [
        google_errors.ServerError(
            502,
            {
                "error": {
                    "code": 502,
                    "message": "Bad Gateway",
                    "status": "BAD_GATEWAY",
                }
            },
        ),
        SimpleNamespace(
            text="retry ok",
            parsed=None,
            usage_metadata=SimpleNamespace(
                prompt_token_count=3,
                candidates_token_count=2,
                total_token_count=5,
                cached_content_token_count=None,
            ),
            candidates=[],
        ),
    ]

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self.models = self

        def generate_content(self, **_kwargs):
            response = responses.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(direct_llm.genai, "Client", FakeClient)
    monkeypatch.setattr(direct_llm.asyncio, "sleep", fake_sleep)

    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="Supervisor",
        lane="supervisor",
        provider="google",
        model="gemini-3.1-flash-lite",
    )

    result = asyncio.run(
        direct_llm.generate_text(
            api_key="key",
            context=context,
            tracker=tracker,
            system_prompt="system",
            user_prompt="user",
        )
    )

    summary = tracker.summary()
    assert result.text == "retry ok"
    assert sleeps == [60.0]
    assert summary["call_count"] == 2
    assert summary["generate_call_count"] == 2
    assert summary["embedding_call_count"] == 0
    assert summary["provider_call_count"] == 2
    assert summary["calls"][0]["status"] == "error"
    assert summary["calls"][0]["provider_error_hint"] == "provider_overloaded"
    assert summary["calls"][0]["provider_error"]["provider_http_status"] == 502
    assert summary["calls"][0]["provider_error"]["provider_status"] == "BAD_GATEWAY"
    assert summary["calls"][1]["status"] == "ok"
    assert summary["rate_limit_waits"][0]["reason"] == "provider_overloaded_retry"


def test_direct_llm_does_not_overload_retry_rate_limit(monkeypatch) -> None:
    direct_llm._RATE_LIMITER._buckets.clear()

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self.models = self

        def generate_content(self, **_kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(direct_llm.genai, "Client", FakeClient)
    monkeypatch.setattr(direct_llm.asyncio, "sleep", fake_sleep)

    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="Supervisor",
        lane="supervisor",
        provider="google",
        model="gemini-3.1-flash-lite",
    )

    with pytest.raises(direct_llm.DirectLlmError):
        asyncio.run(
            direct_llm.generate_text(
                api_key="key",
                context=context,
                tracker=tracker,
                system_prompt="system",
                user_prompt="user",
            )
        )

    assert sleeps == []
    assert tracker.summary()["call_count"] == 1


def test_google_provider_error_details_extracts_quota_and_retry_info() -> None:
    exc = google_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "Resource exhausted for key AIza12345678901234567890",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {
                                "quotaMetric": "generativelanguage.googleapis.com/generate_content_requests",
                                "quotaId": "GenerateRequestsPerMinutePerProject",
                                "quotaDimensions": {
                                    "model": "gemini-3.1-flash-lite",
                                    "location": "global",
                                },
                                "subject": "projects/private-project-id",
                            }
                        ],
                    },
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "12s",
                    },
                ],
            }
        },
    )

    provider_error = direct_llm.provider_error_details(exc)

    assert provider_error is not None
    assert provider_error["provider_http_status"] == 429
    assert provider_error["provider_status"] == "RESOURCE_EXHAUSTED"
    assert provider_error["provider_message"] == "Resource exhausted for key [REDACTED_GEMINI_API_KEY]"
    assert provider_error["quota_metric"] == "generativelanguage.googleapis.com/generate_content_requests"
    assert provider_error["quota_id"] == "GenerateRequestsPerMinutePerProject"
    assert provider_error["quota_dimensions"] == {
        "model": "gemini-3.1-flash-lite",
        "location": "global",
    }
    assert provider_error["quota_subject_hash"] != "projects/private-project-id"
    assert provider_error["retry_delay_seconds"] == 12.0
    assert provider_error["details_present"] is True


def test_google_provider_error_details_handles_plain_429() -> None:
    exc = google_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "Resource has been exhausted.",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )

    provider_error = direct_llm.provider_error_details(exc)

    assert provider_error is not None
    assert provider_error["provider_http_status"] == 429
    assert provider_error["provider_status"] == "RESOURCE_EXHAUSTED"
    assert provider_error["details_present"] is False
    assert "quota_metric" not in provider_error
    assert "quota_id" not in provider_error


def test_direct_llm_provider_error_is_tracked_and_raised(monkeypatch) -> None:
    direct_llm._RATE_LIMITER._buckets.clear()

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            self.models = self

        def generate_content(self, **_kwargs):
            raise google_errors.ClientError(
                429,
                {
                    "error": {
                        "code": 429,
                        "message": "Resource has been exhausted.",
                        "status": "RESOURCE_EXHAUSTED",
                    }
                },
            )

    monkeypatch.setattr(direct_llm.genai, "Client", FakeClient)

    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="Supervisor",
        lane="supervisor",
        provider="google",
        model="gemini-3.1-flash-lite",
    )

    with pytest.raises(direct_llm.DirectLlmError) as exc_info:
        asyncio.run(
            direct_llm.generate_text(
                api_key="key",
                context=context,
                tracker=tracker,
                system_prompt="system",
                user_prompt="user",
            )
        )

    summary = tracker.summary()
    assert summary["call_count"] == 1
    call = summary["calls"][0]
    assert call["status"] == "error"
    assert call["provider_error_hint"] == "provider_rate_limit"
    assert call["provider_error"]["provider_http_status"] == 429
    assert call["provider_error"]["provider_status"] == "RESOURCE_EXHAUSTED"
    assert exc_info.value.provider_error_hint == "provider_rate_limit"
    assert exc_info.value.provider_error["provider_http_status"] == 429


def test_llm_tracker_counts_embedding_separately_from_generate_budget() -> None:
    tracker = direct_llm.RunLlmTracker(max_calls=1)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        key_fingerprint="key-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="CharacterLoreEmbedding",
        lane="lore_query_embedding",
        provider="google",
        model="gemini-embedding-2",
    )

    provider_order = tracker.next_provider_call_order()
    tracker.record_embedding_call(
        context=context,
        provider_call_order=provider_order,
        status="ok",
        duration_ms=7,
    )

    assert tracker.next_call_order() == 1
    with pytest.raises(direct_llm.DirectLlmMaxCallsExceeded):
        tracker.next_call_order()
    summary = tracker.summary()
    assert summary["call_count"] == 0
    assert summary["generate_call_count"] == 0
    assert summary["embedding_call_count"] == 1
    assert summary["provider_call_count"] == 1
    assert summary["calls"][0]["call_type"] == "embed_content"












































































































































































































































































def test_writer_split_call_budget_allows_json_retry_worst_case(monkeypatch) -> None:
    monkeypatch.setattr(direct_llm.settings, "DIRECT_LLM_MAX_CALLS_PER_RUN", 20)
    logical_calls_with_writer_repairs = 10
    json_attempts_per_call = 2

    assert (
        logical_calls_with_writer_repairs * json_attempts_per_call
        <= direct_llm.settings.direct_llm_max_calls_per_run
    )






def test_direct_llm_rate_limiter_waits_instead_of_failing(monkeypatch) -> None:
    direct_llm._RATE_LIMITER._buckets.clear()
    monkeypatch.setattr(direct_llm.settings, "DIRECT_LLM_DEFAULT_RPM_LIMIT", 1)
    monkeypatch.setattr(direct_llm.settings, "DIRECT_LLM_RATE_LIMIT_BUFFER_SECONDS", 0)
    monkeypatch.setattr(direct_llm.settings, "DIRECT_LLM_MAX_WAIT_SECONDS", 120)

    class FakeTime:
        def __init__(self) -> None:
            self._ticks = iter([0.0, 0.0, 61.0])

        def monotonic(self) -> float:
            return next(self._ticks)

    sleeps: list[float] = []

    monkeypatch.setattr(direct_llm, "time", FakeTime())

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(direct_llm.asyncio, "sleep", fake_sleep)

    tracker = direct_llm.RunLlmTracker(max_calls=3)
    context = direct_llm.DirectLlmCallContext(
        credential_id="cred-1",
        character_id="char-1",
        agent_run_id="run-1",
        node="Supervisor",
        lane="supervisor",
        provider="google",
        model="gemini-3.1-flash-lite",
    )

    async def run_waits() -> None:
        await direct_llm._RATE_LIMITER.wait_if_needed(
            context=context, tracker=tracker
        )
        await direct_llm._RATE_LIMITER.wait_if_needed(
            context=context, tracker=tracker
        )

    asyncio.run(run_waits())

    assert sleeps == [60.0]
    assert tracker.rate_limit_waits[0]["reason"] == "rpm_window_full"
    assert tracker.rate_limit_waits[0]["call_type"] == "generate_content"
    assert tracker.rate_limit_waits[0]["provider"] == "google"
    assert tracker.rate_limit_waits[0]["model"] == "gemini-3.1-flash-lite"
    assert tracker.rate_limit_waits[0]["node"] == "Supervisor"
    assert tracker.rate_limit_waits[0]["lane"] == "supervisor"
