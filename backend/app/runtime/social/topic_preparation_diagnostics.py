"""Bounded, content-free diagnostics for explicit topic preparation failures.

No database writes or provider calls. Never log exception messages, prompts, generated
names, validation inputs, credential identifiers or secrets.
"""
from __future__ import annotations

import json
import logging
import re
from time import monotonic

from pydantic import ValidationError

from app.integrations.direct_llm import DirectLlmJsonError

logger = logging.getLogger(__name__)
_VALIDATION_TYPES = frozenset({
    "too_short", "too_long", "string_too_short", "string_too_long", "string_type",
    "list_type", "dict_type", "model_type", "missing", "extra_forbidden", "literal_error",
})
_SAFE_CODES = frozenset({
    "source_changed", "topic_preparation_limit", "topic_name_invalid", "topic_scope_invalid",
    "world_credential_required", "world_credential_binding_changed", "google_key_required",
    "name_binding_changed", "name_binding_invalid", "name_binding_missing",
    "invalid_topic_definition", "topic_name_too_short",
})
_FINISH_REASONS = frozenset({"STOP", "MAX_TOKENS", "SAFETY", "RECITATION", "OTHER", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "MALFORMED_FUNCTION_CALL"})
_SHAPES = frozenset({"schema_validation", "empty", "markdown_fence", "natural_text_only", "wrong_root_type", "extra_text", "truncated_or_unclosed", "bad_escape", "unknown"})


def _validation(exc):
    if isinstance(exc, ValidationError):
        errors = [{"path": ".".join(map(str, error["loc"])), "type": error["type"]}
                  for error in exc.errors(include_input=False, include_url=False, include_context=False)[:4]]
    else:
        errors = getattr(exc, "validation_summary", None) or []
    return [{
        "path": item["path"] if re.fullmatch(r"topics(?:\.\d+)?(?:\.(?:name|scope))?", item.get("path", "")) else "unknown_field",
        "type": item["type"] if item.get("type") in _VALIDATION_TYPES else "validation_error",
    } for item in errors[:4]]


def _provider_call(call):
    failure = call.get("failure_class")
    status = (call.get("provider_error") or {}).get("provider_http_status")
    return {
        "status": call.get("status") if call.get("status") in {"ok", "error"} else "unknown",
        "duration_ms": call.get("duration_ms"),
        "finish_reason": call.get("finish_reason") if call.get("finish_reason") in _FINISH_REASONS else None,
        "failure_class": failure if isinstance(failure, str) and re.fullmatch(r"[A-Za-z_]{1,80}", failure) else None,
        "http_status": status if isinstance(status, int) and 100 <= status <= 599 else None,
    }


def record_failure(*, exc, stage, request_id, world_id, world_character_id,
                   started_at, tracker=None, topic_count=None):
    """Logging is best effort and must not alter rollback or failure persistence."""
    try:
        validation = _validation(exc)
        code = "generation_failed"
        response = None
        if isinstance(exc, DirectLlmJsonError):
            stage = "output_validation"
            code = "response_schema_invalid" if validation else "response_json_invalid"
            payload = exc.last_payload
            if isinstance(payload, dict) and isinstance(payload.get("topics"), list):
                topic_count = len(payload["topics"])
            diagnostic = (exc.json_error_diagnostics or [{}])[-1]
            response = {
                "shape": diagnostic.get("shape_hint") if diagnostic.get("shape_hint") in _SHAPES else "unknown",
                "chars": diagnostic.get("response_length"),
                "parsed_present": diagnostic.get("parsed_present") is True,
                "finish_reason": diagnostic.get("finish_reason") if diagnostic.get("finish_reason") in _FINISH_REASONS else None,
            }
        elif isinstance(exc, ValidationError):
            code = "response_schema_invalid"
        elif str(exc) in _SAFE_CODES:
            code = str(exc)
        payload = {
            "diagnostic_version": "topic-preparation.v1", "request_id": request_id,
            "world_id": world_id, "world_character_id": world_character_id,
            "stage": stage, "code": code, "exception_type": type(exc).__name__,
            "validation": validation, "topic_count": topic_count, "response": response,
            "elapsed_ms": round((monotonic() - started_at) * 1000, 3),
            "call_counts_observed": tracker is not None,
            "logical_calls": tracker.call_order_in_run if tracker is not None else None,
            "sdk_attempts": tracker.provider_call_order_in_run if tracker is not None else None,
            "provider_calls": [_provider_call(call) for call in tracker.calls[-4:]] if tracker is not None else [],
        }
        logger.warning("topic_preparation_failed %s", json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    except Exception:
        # Diagnostics cannot replace the original failure or strand its lease.
        pass
