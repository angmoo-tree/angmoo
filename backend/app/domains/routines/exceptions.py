"""Stable activity lifecycle errors."""
from __future__ import annotations

from datetime import datetime
from typing import Any


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


class JointActivitySchedulingError(Exception):
    reason_code = "joint_activity_schedule_error"


class JointActivityNotFoundError(JointActivitySchedulingError):
    reason_code = "joint_activity_not_found"


class JointActivityConflictError(JointActivitySchedulingError):
    reason_code = "joint_activity_schedule_conflict"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class JointActivityValidationError(JointActivitySchedulingError):
    reason_code = "joint_activity_invalid"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class JointActivityRuntimeError(Exception):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class ActivityPolicyDeniedError(Exception):
    pass


class AgentRunConflictError(Exception):
    pass


class AgentRunServiceError(Exception):
    pass


class AgentSlotUnavailableError(AgentRunServiceError):
    pass


class ReadOnlyLaneRetryExhausted(AgentRunServiceError):
    def __init__(
        self,
        *,
        lane_name: str,
        lane_result: dict[str, Any],
        raw_error: str,
    ) -> None:
        self.lane_name = lane_name
        self.lane_result = lane_result
        self.raw_error = raw_error
        super().__init__(raw_error)


class ReadOnlyLaneDeferredError(AgentRunServiceError):
    def __init__(
        self,
        *,
        lane_name: str,
        retry_at: datetime,
        gateway_result: dict[str, object],
        raw_error: str,
    ) -> None:
        self.lane_name = lane_name
        self.retry_at = retry_at
        self.gateway_result = gateway_result
        self.raw_error = raw_error
        super().__init__(raw_error)
