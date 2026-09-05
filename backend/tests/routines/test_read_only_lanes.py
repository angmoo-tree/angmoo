import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.runtime.resident import read_only_lanes as agent_runs


def test_read_only_lane_retry_success_after_timeout(monkeypatch):
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MIN_SECONDS", 0)
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MAX_SECONDS", 0)
    attempts: list[int] = []

    async def operation(attempt: int):
        attempts.append(attempt)
        if attempt == 1:
            raise agent_runs.OpenClawGatewayError(
                "UNAVAILABLE: FailoverError: LLM request timed out."
            )
        return {"status": "ok", "runId": "retry-success"}

    result = asyncio.run(
        agent_runs._run_read_only_lane_with_retry(
            lane_name="feed_scan_lane",
            operation=operation,
            attempt_metadata=lambda attempt: {
                "agent_run_id": "run-1",
                "lane": "feed_scan",
                "openclaw_run_id": f"run-1-v6-feed-scan-attempt-{attempt}",
                "provider": "google",
                "model": "gemini-3.1-flash-lite",
                "auth_profile_id": "google:char-1",
                "timeout_seconds": 180,
            },
        )
    )

    assert attempts == [1, 2]
    assert result["status"] == "ok"
    assert result["attempts"] == 2
    assert result["first_error_class"] == "openclaw_failover_timeout"
    assert result["retry_delay_seconds"] == 0
    assert "LLM request timed out" in result["first_error"]
    assert result["attempt_errors"][0] == {
        "agent_run_id": "run-1",
        "lane": "feed_scan",
        "openclaw_run_id": "run-1-v6-feed-scan-attempt-1",
        "provider": "google",
        "model": "gemini-3.1-flash-lite",
        "auth_profile_id": "google:char-1",
        "timeout_seconds": 180,
        "attempt": 1,
        "error_class": "openclaw_failover_timeout",
        "timeout_source": "openclaw_embedded_run_timeout",
        "error": "UNAVAILABLE: FailoverError: LLM request timed out.",
    }


def test_feed_history_sanitize_retry_success_after_timeout(monkeypatch):
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MIN_SECONDS", 0)
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MAX_SECONDS", 0)
    attempts: list[int] = []

    async def operation(attempt: int):
        attempts.append(attempt)
        if attempt == 1:
            raise agent_runs.OpenClawGatewayError(
                "UNAVAILABLE: FailoverError: LLM request timed out."
            )
        return {"status": "ok", "runId": "sanitize-retry-success"}

    result = asyncio.run(
        agent_runs._run_read_only_lane_with_retry(
            lane_name="feed_history_sanitize_lane",
            operation=operation,
            attempt_metadata=lambda attempt: {
                "agent_run_id": "run-1",
                "lane": "feed_history_sanitize",
                "openclaw_run_id": (
                    f"run-1-v6-feed-history-sanitize-attempt-{attempt}"
                ),
                "provider": "google",
                "model": "gemini-3.1-flash-lite",
                "auth_profile_id": "google:char-1",
                "timeout_seconds": agent_runs.FEED_HISTORY_SANITIZE_TIMEOUT_SECONDS,
            },
            max_attempts=agent_runs.FEED_HISTORY_SANITIZE_MAX_ATTEMPTS,
        )
    )

    assert attempts == [1, 2]
    assert result["status"] == "ok"
    assert result["attempts"] == 2
    assert result["runId"] == "sanitize-retry-success"
    assert "feed_history_sanitize_fallback" not in result
    assert result["attempt_errors"][0]["timeout_seconds"] == 60
    assert result["attempt_errors"][0]["attempt"] == 1


def test_feed_history_sanitize_retry_exhaustion_uses_two_60s_attempts(monkeypatch):
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MIN_SECONDS", 0)
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MAX_SECONDS", 0)
    attempts: list[int] = []

    async def operation(attempt: int):
        attempts.append(attempt)
        raise agent_runs.OpenClawGatewayError(
            "UNAVAILABLE: FailoverError: LLM request timed out."
        )

    with pytest.raises(agent_runs.ReadOnlyLaneRetryExhausted) as exc_info:
        asyncio.run(
            agent_runs._run_read_only_lane_with_retry(
                lane_name="feed_history_sanitize_lane",
                operation=operation,
                attempt_metadata=lambda attempt: {
                    "agent_run_id": "run-1",
                    "lane": "feed_history_sanitize",
                    "openclaw_run_id": (
                        f"run-1-v6-feed-history-sanitize-attempt-{attempt}"
                    ),
                    "provider": "google",
                    "model": "gemini-3.1-flash-lite",
                    "auth_profile_id": "google:char-1",
                    "timeout_seconds": agent_runs.FEED_HISTORY_SANITIZE_TIMEOUT_SECONDS,
                },
                max_attempts=agent_runs.FEED_HISTORY_SANITIZE_MAX_ATTEMPTS,
            )
        )

    lane_result = exc_info.value.lane_result
    assert attempts == [1, 2]
    assert lane_result["attempts"] == 2
    assert lane_result["attempt_errors"][0]["timeout_seconds"] == 60
    assert lane_result["attempt_errors"][1]["timeout_seconds"] == 60
    assert lane_result["attempt_errors"][0]["attempt"] == 1
    assert lane_result["attempt_errors"][1]["attempt"] == 2


def test_feed_scan_retry_exhaustion_defers_without_final_action(monkeypatch):
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MIN_SECONDS", 0)
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MAX_SECONDS", 0)
    attempts: list[int] = []

    async def operation(attempt: int):
        attempts.append(attempt)
        raise agent_runs.OpenClawGatewayError(
            "UNAVAILABLE: FailoverError: LLM request timed out."
        )

    with pytest.raises(agent_runs.ReadOnlyLaneRetryExhausted) as exc_info:
        asyncio.run(
            agent_runs._run_read_only_lane_with_retry(
                lane_name="feed_scan_lane",
                operation=operation,
                attempt_metadata=lambda attempt: {
                    "agent_run_id": "run-1",
                    "lane": "feed_scan",
                    "openclaw_run_id": f"run-1-v6-feed-scan-attempt-{attempt}",
                    "provider": "google",
                    "model": "gemini-3.1-flash-lite",
                    "auth_profile_id": "google:char-1",
                    "timeout_seconds": 180,
                },
            )
        )

    retry_at = datetime(2026, 6, 6, 9, 30, tzinfo=UTC)
    gateway_result = agent_runs._build_read_only_lane_deferred_gateway_result(
        result={"flow": "resident_v6_individual_tools"},
        lane_name=exc_info.value.lane_name,
        lane_result=exc_info.value.lane_result,
        retry_at=retry_at,
    )

    assert attempts == [1, 2]
    assert gateway_result["status"] == "deferred"
    assert gateway_result["reason"] == "read_only_lane_retry_exhausted"
    assert gateway_result["retry_at"] == "2026-06-06T09:30:00+00:00"
    assert gateway_result["feed_scan_lane"]["attempts"] == 2
    assert gateway_result["feed_scan_lane"]["failure_class"] == (
        "openclaw_failover_timeout"
    )
    assert "first_error" in gateway_result["feed_scan_lane"]
    assert gateway_result["feed_scan_lane"]["attempt_errors"][1]["attempt"] == 2
    assert gateway_result["feed_scan_lane"]["attempt_errors"][1]["timeout_source"] == (
        "openclaw_embedded_run_timeout"
    )
    assert "final_action_lane" not in gateway_result


def test_read_only_lane_retry_records_gateway_timing_diagnostics(monkeypatch):
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MIN_SECONDS", 0)
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_RETRY_DELAY_MAX_SECONDS", 0)

    async def operation(attempt: int):
        raise agent_runs.OpenClawGatewayError(
            "OpenClaw Gateway request timed out after 225s",
            diagnostics={
                "backend_request_started_at": "2026-06-06T09:00:00+00:00",
                "backend_request_finished_at": "2026-06-06T09:03:45+00:00",
                "backend_duration_ms": 225000,
                "timeout_source": "backend_gateway_timeout",
                "call_order_in_run": attempt,
                "idempotency_key": f"run-1-attempt-{attempt}",
            },
        )

    with pytest.raises(agent_runs.ReadOnlyLaneRetryExhausted) as exc_info:
        asyncio.run(
            agent_runs._run_read_only_lane_with_retry(
                lane_name="feed_scan_lane",
                operation=operation,
                attempt_metadata=lambda attempt: {
                    "agent_run_id": "run-1",
                    "lane": "feed_scan",
                    "openclaw_run_id": f"run-1-attempt-{attempt}",
                    "provider": "google",
                    "model": "gemini-3.1-flash-lite",
                    "auth_profile_id": "google:char-1",
                    "timeout_seconds": 180,
                },
            )
        )

    attempt_error = exc_info.value.lane_result["attempt_errors"][0]
    assert attempt_error["backend_duration_ms"] == 225000
    assert attempt_error["timeout_source"] == "backend_gateway_timeout"
    assert attempt_error["call_order_in_run"] == 1
    assert attempt_error["idempotency_key"] == "run-1-attempt-1"


def test_read_only_lane_error_classifier_distinguishes_timeout_sources():
    assert agent_runs._classify_read_only_lane_error(
        "Google Generative AI API error (503): high demand [code=UNAVAILABLE]"
    ) == "google_503_high_demand"
    assert agent_runs._classify_read_only_lane_error(
        "UNAVAILABLE: FailoverError: LLM request timed out."
    ) == "openclaw_failover_timeout"
    assert agent_runs._classify_read_only_lane_error(
        "OpenClaw Gateway request timed out after 225s"
    ) == "backend_gateway_timeout"
    assert agent_runs._classify_read_only_lane_error(
        "UNAVAILABLE: The AI service is temporarily overloaded."
    ) == "google_unavailable_unknown"
    assert agent_runs._classify_read_only_lane_timeout_source(
        "LLM idle timeout (180s): no response from model"
    ) == "openclaw_llm_idle_timeout"


def test_feed_history_sanitize_retry_exhaustion_uses_metadata_fallback_reason():
    assert agent_runs._feed_history_sanitize_metadata_fallback_reason(
        retry_exhausted=True
    ) == "feed_history_sanitize_retry_exhausted_metadata_fallback"
    assert agent_runs._feed_history_sanitize_metadata_fallback_reason(
        retry_exhausted=False
    ) == "feed_history_sanitize_metadata_fallback"


def test_read_only_lane_deferred_retry_at_uses_30_minutes(monkeypatch):
    monkeypatch.setattr(agent_runs, "READ_ONLY_LANE_DEFERRED_RETRY_MINUTES", 30)
    now = datetime(2026, 6, 6, 9, 0, tzinfo=UTC)

    assert agent_runs._read_only_lane_deferred_retry_at(now) == now + timedelta(
        minutes=30
    )


@pytest.mark.parametrize(
    "error_type",
    (asyncio.CancelledError, agent_runs.OpenClawGatewayError),
    ids=("caller-cancelled", "permanent-gateway-error"),
)
def test_non_retryable_lane_exit_preserves_original_error_without_sleep(
    monkeypatch, error_type,
):
    attempts = []
    sleeps = []
    failure = error_type("permanent authorization failure")

    async def operation(attempt):
        attempts.append(attempt)
        raise failure

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(agent_runs.asyncio, "sleep", sleep)
    with pytest.raises(error_type) as caught:
        asyncio.run(
            agent_runs._run_read_only_lane_with_retry(
                lane_name="feed_scan_lane", operation=operation, max_attempts=3,
            )
        )
    assert caught.value is failure
    assert attempts == [1]
    assert sleeps == []
