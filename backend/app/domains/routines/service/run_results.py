from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.redaction import redact_secrets
from app.domains.routines.repository import runs as run_queries


def _safe_gateway_result(value: dict[str, object]) -> dict[str, object]:
    redacted = redact_secrets(value)
    return redacted if isinstance(redacted, dict) else {}


def _compact_stored_llm_usage(usage: dict[str, Any]) -> dict[str, Any]:
    compact = _compact_llm_usage(usage)
    per_call: list[dict[str, Any]] = []
    raw_calls = usage.get("perCall")
    if isinstance(raw_calls, list):
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
            call: dict[str, Any] = {}
            for key in (
                "index",
                "provider",
                "model",
                "authProfileId",
                "status",
                "startedAt",
                "endedAt",
                "durationMs",
                "quotaWaitMs",
                "quotaReason",
                "quotaKeyHash",
                "errorReason",
            ):
                value = raw_call.get(key)
                if value is not None:
                    call[key] = value
            for key in (
                "inputTokens",
                "outputTokens",
                "cacheReadTokens",
                "cacheWriteTokens",
                "totalTokens",
            ):
                value = _positive_int(raw_call.get(key))
                if value > 0:
                    call[key] = value
            if call:
                per_call.append(call)
    if per_call:
        compact["perCall"] = per_call
    scope = usage.get("scope")
    if isinstance(scope, dict):
        compact["scope"] = {
            key: value
            for key in (
                "app",
                "characterId",
                "agentRunId",
                "lane",
                "attempt",
                "callOrderInRun",
                "idempotencyKey",
                "backendRequestStartedAt",
            )
            if isinstance((value := scope.get(key)), str) and value
        }
    return compact


def _compact_stored_lane_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, Any] = {}
    for key in ("status", "runId", "summary", "reason"):
        item = value.get(key)
        if item is not None:
            compact[key] = item
    for key in ("outcome", "decision_source"):
        item = value.get(key)
        if isinstance(item, str) and item:
            compact[key] = item
    for key in (
        "candidate_count",
        "provider_call_count",
        "public_action_count",
        "handled_notification_count",
    ):
        item = value.get(key)
        if isinstance(item, int) and item >= 0:
            compact[key] = item
    planner_invoked = value.get("planner_invoked")
    if isinstance(planner_invoked, bool):
        compact["planner_invoked"] = planner_invoked
    for key in (
        "backend_request_started_at",
        "backend_request_finished_at",
        "timeout_source",
        "idempotency_key",
        "openclaw_run_id",
    ):
        item = value.get(key)
        if isinstance(item, str) and item:
            compact[key] = item
    for key in ("backend_duration_ms", "call_order_in_run"):
        item = value.get(key)
        if isinstance(item, int) and item >= 0:
            compact[key] = item
    attempts = value.get("attempts")
    if isinstance(attempts, int) and attempts > 0:
        compact["attempts"] = attempts
    retry_delay_seconds = value.get("retry_delay_seconds")
    if isinstance(retry_delay_seconds, int) and retry_delay_seconds >= 0:
        compact["retry_delay_seconds"] = retry_delay_seconds
    for key in ("first_error_class", "failure_class"):
        item = value.get(key)
        if isinstance(item, str) and item:
            compact[key] = item
    first_error = value.get("first_error")
    if isinstance(first_error, str):
        compact["first_error"] = first_error[:1500]
    error = value.get("error")
    if isinstance(error, str):
        compact["error"] = error[:1500]
    attempt_errors = value.get("attempt_errors")
    if isinstance(attempt_errors, list):
        compact_attempt_errors: list[dict[str, Any]] = []
        allowed_keys = {
            "attempt",
            "lane",
            "agent_run_id",
            "openclaw_run_id",
            "idempotency_key",
            "provider",
            "model",
            "auth_profile_id",
            "timeout_seconds",
            "backend_request_started_at",
            "backend_request_finished_at",
            "backend_duration_ms",
            "timeout_source",
            "call_order_in_run",
            "error_class",
            "error",
        }
        for raw_attempt in attempt_errors:
            if not isinstance(raw_attempt, dict):
                continue
            compact_attempt: dict[str, Any] = {}
            for key in allowed_keys:
                item = raw_attempt.get(key)
                if item is None or item == "":
                    continue
                compact_attempt[key] = item[:1500] if key == "error" and isinstance(item, str) else item
            if compact_attempt:
                compact_attempt_errors.append(compact_attempt)
        if compact_attempt_errors:
            compact["attempt_errors"] = compact_attempt_errors
    usage = _extract_gateway_llm_usage(value)
    if usage:
        compact["llmUsage"] = _compact_stored_llm_usage(usage)
    return compact


def _compact_writing_composition_lane(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, Any] = {}
    for key in ("status", "kind", "runId", "summary", "reason"):
        item = value.get(key)
        if item is not None:
            compact[key] = item
    usage = value.get("llmUsage")
    if isinstance(usage, dict):
        compact["llmUsage"] = _compact_stored_llm_usage(usage)
    else:
        extracted_usage = _extract_gateway_llm_usage(value)
        if extracted_usage:
            compact["llmUsage"] = _compact_stored_llm_usage(extracted_usage)
    error = value.get("error")
    if isinstance(error, str):
        compact["error"] = error[:1500]
    return compact


def _stored_gateway_result(value: dict[str, object]) -> dict[str, object]:
    redacted = _safe_gateway_result(value)
    stored: dict[str, object] = {}
    for key in (
        "status",
        "engine",
        "runId",
        "flow",
        "feature_flag",
        "summary",
        "reason",
        "retry_at",
        "repeated_overload",
        "cooldown_until",
        "effective_policy",
        "node_trace",
        "supervisor_decision",
        "active_topic_arc",
        "selected_action_bundle",
        "planner_results",
        "relationship_review",
        "action_budget_trim_summary",
        "write_task_summary",
        "writer_results",
        "publish_result",
        "topic_arc_result",
        "state_result",
        "failure_class",
        "failure_node",
        "failure_lane",
        "parse_error_type",
        "attempt_count",
        "validation_summary",
        "json_error_diagnostics",
        "provider_error_hint",
        "provider_error",
        "independent_post_decision",
        "independent_post_roll",
        "independent_post_probability",
        "independent_post_roll_passed",
        "independent_post_topic_key",
        "independent_post_topic_pool_size",
        "independent_post_topic_prompt_count",
        "llm_usage_summary",
        "llm_rate_limit_waits",
        "resident_success_validation",
        "memory_note_refined",
        "memory_note_refine_warning",
        "activity_policy",
        "feed_history_sanitize_fallback",
        "feed_history_sanitize_fallback_reason",
        "session_context",
    ):
        if key in redacted:
            stored[key] = redacted[key]
    if isinstance(redacted.get("action_gate"), dict):
        stored["action_gate"] = redacted["action_gate"]
    for key in (
        "inbox_lane",
        "feed_history_sanitize_lane",
        "feed_scan_lane",
        "final_action_lane",
        "state_lane",
        "feed_perception",
        "action_decision",
        "complete_tick_followup",
        "memory_note_refine",
    ):
        lane = _compact_stored_lane_result(redacted.get(key))
        if lane:
            stored[key] = lane
    writing_lanes = redacted.get("writing_composition_lanes")
    if isinstance(writing_lanes, list):
        stored_lanes = [
            lane
            for lane in (
                _compact_writing_composition_lane(item) for item in writing_lanes
            )
            if lane
        ]
        if stored_lanes:
            stored["writing_composition_lanes"] = stored_lanes
    lane = _compact_stored_lane_result(redacted)
    if lane:
        stored["gateway"] = lane
    error = redacted.get("error")
    if isinstance(error, str):
        stored["error"] = error[:1500]
    return stored


def _persist_agent_run_gateway_snapshot(
    db: Session, *, run_id: str, payload: dict[str, object]
) -> None:
    run = run_queries.get_run(db, run_id)
    if run is None:
        return
    current = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    merged = dict(current)
    merged.update(payload)
    run.gateway_result = _stored_gateway_result(merged)
    db.commit()


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float) and value.is_integer():
        numeric = int(value)
        return numeric if numeric > 0 else 0
    return 0


def _extract_gateway_llm_usage(lane_result: Any) -> dict[str, Any] | None:
    if not isinstance(lane_result, dict):
        return None
    result = lane_result.get("result")
    if not isinstance(result, dict):
        return None
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return None
    agent_meta = meta.get("agentMeta")
    if not isinstance(agent_meta, dict):
        return None
    llm_usage = agent_meta.get("llmUsage")
    return llm_usage if isinstance(llm_usage, dict) else None


def _compact_llm_usage(usage: dict[str, Any]) -> dict[str, Any]:
    count_keys = (
        "providerCallCount",
        "successfulProviderCallCount",
        "failedProviderCallCount",
    )
    token_keys = (
        "inputTokens",
        "outputTokens",
        "cacheReadTokens",
        "cacheWriteTokens",
        "totalTokens",
    )
    compact = {key: _positive_int(usage.get(key)) for key in count_keys}
    compact.update(
        {
            key: value
            for key in token_keys
            if (value := _positive_int(usage.get(key))) > 0
        }
    )
    return compact if compact["providerCallCount"] > 0 else {}


def _build_llm_usage_summary(gateway_result: dict[str, Any]) -> dict[str, Any] | None:
    lane_map = {
        "inbox_lane": "inbox",
        "feed_history_sanitize_lane": "feed_history_sanitize",
        "feed_scan_lane": "feed_scan",
        "final_action_lane": "final_action",
        "state_lane": "state",
    }
    by_lane: dict[str, dict[str, Any]] = {}
    total = {
        "providerCallCount": 0,
        "successfulProviderCallCount": 0,
        "failedProviderCallCount": 0,
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "totalTokens": 0,
    }

    for result_key, lane_name in lane_map.items():
        usage = _extract_gateway_llm_usage(gateway_result.get(result_key))
        if not usage:
            continue
        compact = _compact_llm_usage(usage)
        if not compact:
            continue
        by_lane[lane_name] = compact
        for key in total:
            total[key] += _positive_int(usage.get(key))

    writing_lanes = gateway_result.get("writing_composition_lanes")
    if isinstance(writing_lanes, list):
        writing_total = {
            "providerCallCount": 0,
            "successfulProviderCallCount": 0,
            "failedProviderCallCount": 0,
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
            "totalTokens": 0,
        }
        for lane_result in writing_lanes:
            if not isinstance(lane_result, dict):
                continue
            usage = lane_result.get("llmUsage")
            if not isinstance(usage, dict):
                usage = _extract_gateway_llm_usage(lane_result)
            if not usage:
                continue
            for key in writing_total:
                value = _positive_int(usage.get(key))
                writing_total[key] += value
                total[key] += value
        compact = {
            key: value
            for key, value in writing_total.items()
            if value > 0 or key.endswith("ProviderCallCount")
        }
        if _positive_int(compact.get("providerCallCount")) > 0:
            by_lane["writing_composition"] = compact

    if not by_lane:
        return None
    return {
        "by_lane": by_lane,
        "total": {
            key: value
            for key, value in total.items()
            if value > 0 or key.endswith("ProviderCallCount")
        },
    }


def _pending_writing_composition_lanes(db: Session, run_id: str) -> list[dict[str, Any]]:
    run = run_queries.get_run(db, run_id)
    if run is None or not isinstance(run.gateway_result, dict):
        return []
    lanes = run.gateway_result.get("writing_composition_lanes")
    if not isinstance(lanes, list):
        return []
    return [
        lane
        for lane in (_compact_writing_composition_lane(item) for item in lanes)
        if lane
    ]
