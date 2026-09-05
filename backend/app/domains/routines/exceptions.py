"""Stable activity lifecycle errors."""
from __future__ import annotations


class ActivityRuntimeError(Exception):
    reason_code = "activity_runtime_error"


class ActivityRuntimeNotFoundError(ActivityRuntimeError):
    reason_code = "activity_runtime_not_found"


class ActivityRuntimeConflictError(ActivityRuntimeError):
    reason_code = "activity_runtime_conflict"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class ActivityRuntimeValidationError(ActivityRuntimeError):
    reason_code = "activity_runtime_invalid"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


__all__ = ['ActivityRuntimeError', 'ActivityRuntimeNotFoundError', 'ActivityRuntimeConflictError', 'ActivityRuntimeValidationError']
