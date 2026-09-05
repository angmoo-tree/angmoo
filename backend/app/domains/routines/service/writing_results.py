"""Brief interpretation, provider-result validation and caller commit policy."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.context_text import neutralize_context_text
from app.domains.routines import models
from app.domains.routines.contracts.writing import WritingKind, WritingPost
from app.domains.routines.exceptions import WritingCompositionError
from app.domains.routines.repository import runs as run_queries
from app.domains.routines.service.action_briefs import (
    PREPARED_CREATE_POST_BRIEF_SENTINEL,
)


def _agent_tool_header_source(session_key: str) -> str:
    if ":tool-auth:" in session_key:
        return "toolAuthKey"
    if ":resident-daypart:" in session_key:
        return "daypart_session_key"
    if ":run-main:" in session_key or ":scratch:" in session_key:
        return "run_scoped_session_key"
    return "session_key"


def _resolve_create_post_brief(run: models.AgentRun, brief: str) -> str:
    if brief.strip() != PREPARED_CREATE_POST_BRIEF_SENTINEL:
        return brief
    gateway_result = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    action_gate = gateway_result.get("action_gate")
    if not isinstance(action_gate, dict):
        raise WritingCompositionError("prepared create_post brief is missing")
    prepared_brief = action_gate.get("prepared_create_post_brief")
    if not isinstance(prepared_brief, str) or not prepared_brief.strip():
        raise WritingCompositionError("prepared create_post brief is missing")
    return prepared_brief.strip()


def _composition_metadata_field(value: Any, *, brief: str, key: str) -> str:
    text = neutralize_context_text(str(value or "")).strip()
    if text and text != "-":
        return text
    prefix = f"{key}:"
    for line in brief.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(prefix):
            fallback = neutralize_context_text(stripped.split(":", 1)[1]).strip()
            return "" if fallback == "-" else fallback
    return ""


def _compact_memory_field(value: Any, *, fallback: str, max_chars: int = 500) -> str:
    text = neutralize_context_text(str(value or "")).strip()
    if not text or text == "-":
        text = neutralize_context_text(fallback).strip()
    return text[:max_chars]


def _build_compact_action_memory(
    *,
    kind: WritingKind,
    post: WritingPost,
    target_post_id: str | None,
    brief: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    action_type = "post" if kind == "create_post" else "reply"
    topic = _compact_memory_field(
        payload.get("memory_summary"),
        fallback=payload.get("topic_signature") or brief,
        max_chars=360,
    )
    relationship_memory = _compact_memory_field(
        payload.get("relationship_memory"),
        fallback="No specific relationship update beyond this public action.",
        max_chars=360,
    )
    return {
        "action_type": action_type,
        "post_id": post.id,
        "reply_id": post.id if kind == "reply" else None,
        "target_person": None,
        "source_post": target_post_id,
        "topic": topic,
        "reason": _compact_memory_field(
            payload.get("novelty_basis"), fallback=brief, max_chars=360
        ),
        "public_result_summary": (
            f"{action_type} created; title={post.title[:120] if post.title else '-'}"
        ),
        "relationship_memory": relationship_memory,
    }


def _writing_stream_params(setting: models.AgentActivitySetting) -> dict[str, Any]:
    return {}


def _extract_gateway_result_text(gateway_result: dict[str, Any]) -> str:
    result = gateway_result.get("result")
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict):
            for key in ("finalAssistantVisibleText", "finalAssistantRawText"):
                text = meta.get(key)
                if isinstance(text, str) and text.strip():
                    return text.strip()
        payloads = result.get("payloads")
        if isinstance(payloads, list):
            parts: list[str] = []
            for payload in payloads:
                if not isinstance(payload, dict):
                    continue
                if payload.get("isError") or payload.get("isReasoning"):
                    continue
                text = payload.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            if parts:
                return "\n\n".join(parts)
    for key in ("text", "content", "message", "output"):
        text = gateway_result.get(key)
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, float) and value.is_integer():
        numeric = int(value)
        return numeric if numeric > 0 else 0
    return 0


def _extract_gateway_llm_usage(gateway_result: Any) -> dict[str, Any] | None:
    if not isinstance(gateway_result, dict):
        return None
    result = gateway_result.get("result")
    if not isinstance(result, dict):
        return None
    meta = result.get("meta")
    if not isinstance(meta, dict):
        return None
    agent_meta = meta.get("agentMeta")
    if not isinstance(agent_meta, dict):
        return None
    usage = agent_meta.get("llmUsage")
    return usage if isinstance(usage, dict) else None


def _compact_stored_llm_usage(usage: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "providerCallCount",
        "successfulProviderCallCount",
        "failedProviderCallCount",
        "inputTokens",
        "outputTokens",
        "cacheReadTokens",
        "cacheWriteTokens",
        "totalTokens",
    ):
        value = _positive_int(usage.get(key))
        if value > 0 or key.endswith("ProviderCallCount"):
            compact[key] = value
    per_call: list[dict[str, Any]] = []
    raw_per_call = usage.get("perCall")
    if isinstance(raw_per_call, list):
        for raw_call in raw_per_call:
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
            for key in ("app", "characterId", "agentRunId", "lane")
            if isinstance((value := scope.get(key)), str) and value
        }
    return compact


def _compact_tool_usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if not usage:
        return None
    compact: dict[str, Any] = {}
    for key in (
        "providerCallCount",
        "successfulProviderCallCount",
        "failedProviderCallCount",
        "totalTokens",
    ):
        value = _positive_int(usage.get(key))
        if value > 0 or key.endswith("ProviderCallCount"):
            compact[key] = value
    quota_wait_ms = 0
    per_call = usage.get("perCall")
    if isinstance(per_call, list):
        for call in per_call:
            if isinstance(call, dict):
                quota_wait_ms += _positive_int(call.get("quotaWaitMs"))
    if quota_wait_ms > 0:
        compact["quotaWaitMs"] = quota_wait_ms
    return compact or None


def _append_writing_composition_lane(
    db: Session,
    *,
    run_id: str,
    kind: WritingKind,
    gateway_result: dict[str, Any],
) -> None:
    run = run_queries.get_run(db, run_id)
    if run is None:
        return
    usage = _extract_gateway_llm_usage(gateway_result)
    lane: dict[str, Any] = {
        "status": gateway_result.get("status") or "unknown",
        "kind": kind,
    }
    run_id_value = gateway_result.get("runId")
    if isinstance(run_id_value, str) and run_id_value:
        lane["runId"] = run_id_value
    if usage:
        lane["llmUsage"] = _compact_stored_llm_usage(usage)

    current = run.gateway_result if isinstance(run.gateway_result, dict) else {}
    lanes = current.get("writing_composition_lanes")
    next_lanes = list(lanes) if isinstance(lanes, list) else []
    next_lanes.append(lane)
    next_payload = dict(current)
    next_payload["writing_composition_lanes"] = next_lanes
    run.gateway_result = next_payload
    db.commit()
