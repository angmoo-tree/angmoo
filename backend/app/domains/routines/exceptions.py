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


class DailyActivityPlanError(Exception):
    reason_code = "daily_activity_plan_error"


class DailyActivityPlanNotFoundError(DailyActivityPlanError):
    reason_code = "activity_plan_not_found"


class DailyActivityPlanForbiddenError(DailyActivityPlanError):
    reason_code = "character_not_owned"


class DailyActivityPlanConflictError(DailyActivityPlanError):
    reason_code = "activity_plan_conflict"

    def __init__(self, reason_code: str | None = None) -> None:
        if reason_code is not None:
            self.reason_code = reason_code
        super().__init__(self.reason_code)


class DailyActivityPlanValidationError(DailyActivityPlanError):
    reason_code = "activity_plan_invalid"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

__all__ += ['DailyActivityPlanError', 'DailyActivityPlanNotFoundError', 'DailyActivityPlanForbiddenError', 'DailyActivityPlanConflictError', 'DailyActivityPlanValidationError']
