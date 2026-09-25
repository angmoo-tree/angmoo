"""Bounded JSON recovery policy owned by the SNS V2 runtime."""

import json
from typing import Any

from app.providers.contracts import JsonRetryDecision, StructuredOutputValidationError

NORMAL_CALL_BUDGET = 10
RECOVERABLE_NODES = frozenset({"InboxTargetSelector", "FeedTargetSelector",
                              "InboxActionPlanner", "FeedActionPlanner", "RoutineWriter"})
RECOVERY_CALL_BUDGET = len(RECOVERABLE_NODES)
MAX_CALL_BUDGET = NORMAL_CALL_BUDGET + RECOVERY_CALL_BUDGET
FIRST_OUTPUT_TOKENS = 4096
RETRY_OUTPUT_TOKENS = 8192


class ActivityRetryGuardError(Exception):
    def __init__(self, original: Exception):
        self.original = original
        super().__init__(type(original).__name__)


def _finish_reason(value: Any) -> str:
    # Gemini adapters may expose an enum or its normalized string value.
    return str(value or "").rsplit(".", 1)[-1].upper()


def retry_truncated_json(exc: BaseException, payload: dict | None,
                         diagnostic: dict, attempt: int) -> bool:
    """Retry only unusable output stopped by the provider token ceiling."""
    if attempt != 1 or _finish_reason(diagnostic.get("finish_reason")) != "MAX_TOKENS":
        return False
    if payload is None:
        return isinstance(exc, json.JSONDecodeError) or diagnostic.get("shape_hint") in {
            "empty", "truncated_or_unclosed", "unknown"}
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return False
    try:
        details = errors()
    except Exception:
        return False
    return bool(details) and all(isinstance(item, dict) and item.get("type") == "missing"
                                 for item in details)


def planner_json_retry(exc: BaseException, payload: dict | None,
                       diagnostic: dict, attempt: int) -> JsonRetryDecision | None:
    """Allow one full regeneration for the two observed Planner failure modes."""
    if attempt != 1:
        return None
    brief_missing = (isinstance(exc, StructuredOutputValidationError)
                     and exc.validation_code == "action_brief_missing")
    if _finish_reason(diagnostic.get("finish_reason")) == "MAX_TOKENS" and (
        brief_missing or retry_truncated_json(exc, payload, diagnostic, attempt)
    ):
        return JsonRetryDecision(
            "planner_output_truncated", RETRY_OUTPUT_TOKENS,
            "The previous JSON output was incomplete. Regenerate the complete result "
            "for the same supplied targets, with a non-blank brief for each actual action.",
        )
    if _finish_reason(diagnostic.get("finish_reason")) == "STOP" and brief_missing:
        return JsonRetryDecision(
            "action_brief_missing", FIRST_OUTPUT_TOKENS,
            f"action_brief_missing at {exc.field_path}: every non-no_action decision "
            "requires a non-blank brief; regenerate the complete result for the supplied targets.",
        )
    return None
