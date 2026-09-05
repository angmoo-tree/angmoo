"""Retry read-only provider lanes without duplicating public activity execution."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from app.core.redaction import redact_secret_text
from app.domains.routines.exceptions import ReadOnlyLaneRetryExhausted
from app.domains.runtime.contracts import OpenClawGatewayError

# Keep the established diagnostic category while moving the actual executor.
logger = logging.getLogger("app.services.agent_runs")

READ_ONLY_LANE_TIMEOUT_SECONDS = 180
READ_ONLY_LANE_RETRY_DELAY_MIN_SECONDS = 15
READ_ONLY_LANE_RETRY_DELAY_MAX_SECONDS = 45
READ_ONLY_LANE_DEFERRED_RETRY_MINUTES = 30
FEED_HISTORY_SANITIZE_TIMEOUT_SECONDS = 60
FEED_HISTORY_SANITIZE_MAX_ATTEMPTS = 2


def _is_read_only_lane_retryable_error(raw: str) -> bool:
    lowered = raw.lower()
    uppered = raw.upper()
    return any(
        marker in lowered or marker in uppered
        for marker in (
            "timeout",
            "timed out",
            "UNAVAILABLE",
        )
    )


def _classify_read_only_lane_error(raw: str) -> str:
    lowered = raw.lower()
    uppered = raw.upper()
    if "google generative ai api error (503)" in lowered or "high demand" in lowered:
        return "google_503_high_demand"
    if "openclaw gateway request timed out" in lowered:
        return "backend_gateway_timeout"
    if "failovererror: llm request timed out" in lowered:
        return "openclaw_failover_timeout"
    if "UNAVAILABLE" in uppered:
        return "google_unavailable_unknown"
    if "timeout" in lowered or "timed out" in lowered:
        return "retryable_timeout_unknown"
    return "unknown"


def _classify_read_only_lane_timeout_source(raw: str) -> str:
    lowered = raw.lower()
    if "google generative ai api error (503)" in lowered or "high demand" in lowered:
        return "provider_error"
    if "llm idle timeout" in lowered:
        return "openclaw_llm_idle_timeout"
    if "failovererror: llm request timed out" in lowered:
        return "openclaw_embedded_run_timeout"
    if "openclaw gateway request timed out" in lowered:
        return "backend_gateway_timeout"
    if "timed out" in lowered or "timeout" in lowered:
        return "retryable_timeout_unknown"
    return "unknown"


def _read_only_lane_retry_delay_seconds() -> int:
    low = max(0, READ_ONLY_LANE_RETRY_DELAY_MIN_SECONDS)
    high = max(low, READ_ONLY_LANE_RETRY_DELAY_MAX_SECONDS)
    return random.randint(low, high)


def _read_only_lane_deferred_retry_at(now: datetime) -> datetime:
    return now + timedelta(minutes=READ_ONLY_LANE_DEFERRED_RETRY_MINUTES)


def _build_read_only_lane_attempt_error(
    *,
    lane_name: str,
    attempt: int,
    raw_error: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if metadata:
        payload.update(metadata)
    payload.setdefault("lane", lane_name)
    payload["attempt"] = attempt
    payload["error_class"] = _classify_read_only_lane_error(raw_error)
    payload.setdefault("timeout_source", _classify_read_only_lane_timeout_source(raw_error))
    payload["error"] = raw_error[:1500]
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != ""
    }


async def _run_read_only_lane_with_retry(
    *,
    lane_name: str,
    operation: Callable[[int], Awaitable[dict[str, Any]]],
    attempt_metadata: Callable[[int], dict[str, Any]] | None = None,
    max_attempts: int = 2,
) -> dict[str, Any]:
    first_error: str | None = None
    first_error_class: str | None = None
    retry_delay_seconds: int | None = None
    attempt_errors: list[dict[str, Any]] = []

    attempts_limit = max(1, max_attempts)
    for attempt in range(1, attempts_limit + 1):
        try:
            lane_result = await operation(attempt)
        except OpenClawGatewayError as exc:
            raw_error = redact_secret_text(str(exc))
            if not _is_read_only_lane_retryable_error(raw_error):
                raise
            metadata: dict[str, Any] = {}
            if attempt_metadata:
                metadata.update(attempt_metadata(attempt))
            exc_diagnostics = getattr(exc, "diagnostics", None)
            if isinstance(exc_diagnostics, dict):
                metadata.update(exc_diagnostics)
            attempt_error = _build_read_only_lane_attempt_error(
                lane_name=lane_name,
                attempt=attempt,
                raw_error=raw_error,
                metadata=metadata,
            )
            attempt_errors.append(attempt_error)
            logger.warning(
                "read_only_lane_retryable_error agent_run_id=%s lane=%s "
                "attempt=%s call_order_in_run=%s openclaw_run_id=%s provider=%s model=%s "
                "auth_profile_id=%s timeout_seconds=%s backend_duration_ms=%s "
                "error_class=%s timeout_source=%s error=%s",
                attempt_error.get("agent_run_id"),
                attempt_error.get("lane"),
                attempt_error.get("attempt"),
                attempt_error.get("call_order_in_run"),
                attempt_error.get("openclaw_run_id"),
                attempt_error.get("provider"),
                attempt_error.get("model"),
                attempt_error.get("auth_profile_id"),
                attempt_error.get("timeout_seconds"),
                attempt_error.get("backend_duration_ms"),
                attempt_error.get("error_class"),
                attempt_error.get("timeout_source"),
                attempt_error.get("error"),
            )
            if attempt >= attempts_limit:
                raise ReadOnlyLaneRetryExhausted(
                    lane_name=lane_name,
                    lane_result={
                        "status": "failed",
                        "reason": "read_only_lane_retry_exhausted",
                        "attempts": attempt,
                        "error": raw_error,
                        "failure_class": attempt_error["error_class"],
                        "attempt_errors": attempt_errors,
                        **(
                            {"first_error": first_error[:1500]}
                            if first_error
                            else {}
                        ),
                        **(
                            {"first_error_class": first_error_class}
                            if first_error_class
                            else {}
                        ),
                        **(
                            {"retry_delay_seconds": retry_delay_seconds}
                            if retry_delay_seconds is not None
                            else {}
                        ),
                    },
                    raw_error=raw_error,
                ) from exc
            first_error = raw_error
            first_error_class = attempt_error["error_class"]
            retry_delay_seconds = _read_only_lane_retry_delay_seconds()
            await asyncio.sleep(retry_delay_seconds)
            continue

        if attempt > 1:
            lane_result = dict(lane_result)
            lane_result["attempts"] = attempt
            if first_error:
                lane_result["first_error"] = first_error[:1500]
            if first_error_class:
                lane_result["first_error_class"] = first_error_class
            if retry_delay_seconds is not None:
                lane_result["retry_delay_seconds"] = retry_delay_seconds
            if attempt_errors:
                lane_result["attempt_errors"] = attempt_errors
        return lane_result

    raise AssertionError("read-only lane retry loop exited unexpectedly")


def _build_read_only_lane_deferred_gateway_result(
    *,
    result: dict[str, Any],
    lane_name: str,
    lane_result: dict[str, Any],
    retry_at: datetime,
) -> dict[str, object]:
    gateway_result = dict(result)
    gateway_result[lane_name] = lane_result
    gateway_result["status"] = "deferred"
    gateway_result["reason"] = "read_only_lane_retry_exhausted"
    gateway_result["retry_at"] = retry_at.isoformat()
    return gateway_result


def _feed_history_sanitize_metadata_fallback_reason(*, retry_exhausted: bool) -> str:
    return (
        "feed_history_sanitize_retry_exhausted_metadata_fallback"
        if retry_exhausted
        else "feed_history_sanitize_metadata_fallback"
    )
