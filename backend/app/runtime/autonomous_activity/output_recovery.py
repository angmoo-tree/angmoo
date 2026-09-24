"""Bounded JSON recovery policy owned by the SNS V2 runtime."""

from typing import Any


NORMAL_CALL_BUDGET = 10
RECOVERABLE_NODES = frozenset({"InboxTargetSelector", "FeedTargetSelector", "RoutineWriter"})
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
        return diagnostic.get("shape_hint") in {"empty", "truncated_or_unclosed", "unknown"}
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return False
    try:
        details = errors()
    except Exception:
        return False
    return bool(details) and all(isinstance(item, dict) and item.get("type") == "missing"
                                 for item in details)
