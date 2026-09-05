from __future__ import annotations

from app.core.redaction import redact_secret_text
from app.domains.routines.constants import RUNTIME_LAST_ERROR_PREFIX
from typing import Any


def _is_success_status(status: str) -> bool:
    return status.lower() not in {
        "failed",
        "failure",
        "error",
        "cancelled",
        "canceled",
        "tool_call_missing",
    }


def _runtime_last_error(*, kind: str, message: str, raw: str) -> str:
    raw_text = redact_secret_text(raw.strip() or "empty error message")
    return (
        f"{RUNTIME_LAST_ERROR_PREFIX}kind={kind}; "
        f"message={message}; raw={raw_text[:1500]}"
    )


def _combined_runtime_evidence_post_id(
    gateway_result: dict[str, Any],
) -> str | None:
    """Choose one truthful representative post for the combined P4/P5/P6 run."""
    publish_result = gateway_result.get("publish_result")
    if not isinstance(publish_result, dict):
        return None

    inbox_result = publish_result.get("inbox")
    if isinstance(inbox_result, dict):
        target_post_id = inbox_result.get("target_post_id")
        if (
            int(inbox_result.get("public_action_count") or 0) > 0
            and isinstance(target_post_id, str)
            and target_post_id
        ):
            return target_post_id

    feed_result = publish_result.get("feed")
    if isinstance(feed_result, dict):
        target_post_id = feed_result.get("target_post_id")
        if (
            int(feed_result.get("public_action_count") or 0) > 0
            and isinstance(target_post_id, str)
            and target_post_id
        ):
            return target_post_id

    routine_result = publish_result.get("routine")
    if isinstance(routine_result, dict):
        post_id = routine_result.get("post_id")
        if (
            int(routine_result.get("public_action_count") or 0) > 0
            and isinstance(post_id, str)
            and post_id
        ):
            return post_id
    return None
