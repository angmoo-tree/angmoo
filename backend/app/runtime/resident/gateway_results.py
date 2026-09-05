from __future__ import annotations

from typing import Any


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


def _build_llm_trace_context(
    *,
    character_id: str,
    agent_run_id: str,
    lane: str,
    attempt: int | None = None,
    call_order_in_run: int | None = None,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    trace_context = {
        "app": "angmoo",
        "characterId": character_id,
        "agentRunId": agent_run_id,
        "lane": lane,
    }
    if attempt is not None:
        trace_context["attempt"] = str(attempt)
    if call_order_in_run is not None:
        trace_context["callOrderInRun"] = str(call_order_in_run)
    if idempotency_key:
        trace_context["idempotencyKey"] = idempotency_key
    return trace_context
