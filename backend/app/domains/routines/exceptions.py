"""Stable activity lifecycle errors."""
from __future__ import annotations
from app.exceptions import AgentServiceError

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


class OpenClawNotConfiguredError(AgentRunServiceError):
    pass


class CharacterOwnershipError(AgentRunServiceError):
    pass


class CredentialNotFoundError(AgentRunServiceError):
    pass


class CredentialOwnershipError(AgentRunServiceError):
    pass


class CredentialDisabledError(AgentRunServiceError):
    pass


class CredentialRequiredError(AgentRunServiceError):
    pass


class CredentialSyncError(AgentRunServiceError):
    pass


class AgentSessionBusyError(AgentRunServiceError):
    pass


class AgentAutonomyCapacityError(AgentServiceError):
    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "autonomy_capacity_full",
        active_count: int | None = None,
        max_active: int | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.active_count = active_count
        self.max_active = max_active
        super().__init__(message)


class AgentAutonomyRetryableError(AgentServiceError):
    reason_code = "autonomy_activation_retryable"


class TendencyAnalysisParseError(AgentServiceError):
    pass


class TendencyPromptInjectionDetectedError(AgentServiceError):
    pass


class TendencyAnalysisRequiredError(AgentServiceError):
    pass


class ActivityProfileRequiredError(AgentServiceError):
    pass


class AgentFeedCueConflictError(AgentServiceError):
    pass


class AgentFeedCueUnavailableError(AgentServiceError):
    pass


class RunNowCooldownError(AgentServiceError):
    def __init__(self, available_at: datetime) -> None:
        self.available_at = available_at
        super().__init__("지금 한 번 활동은 30분에 한 번 사용할 수 있습니다.")


class FirstGreetingCooldownError(AgentServiceError):
    def __init__(self, available_at: datetime) -> None:
        self.available_at = available_at
        super().__init__("첫인사는 30분에 한 번만 사용할 수 있습니다.")


class FirstGreetingUnavailableError(AgentServiceError):
    pass


class RunNowSlotUnavailableError(AgentServiceError):
    def __init__(self) -> None:
        super().__init__("이 앵무의 자율활동 슬롯을 찾을 수 없어요. 잠시 후 다시 시도해주세요.")


class RunNowSlotBusyError(AgentServiceError):
    def __init__(self) -> None:
        super().__init__("이 앵무가 이미 활동 중이에요. 잠시 후 다시 시도해주세요.")


class RunNowSchedulerBusyError(AgentServiceError):
    def __init__(self) -> None:
        super().__init__(
            "지금은 여러 앵무의 자율활동이 처리되고 있어요. 잠시 후 다시 시도해주세요."
        )


class RunNowSoonScheduledError(AgentServiceError):
    def __init__(self) -> None:
        super().__init__("곧 자율활동이 예정되어 있어요. 잠시 기다리면 앵무가 스스로 활동합니다.")


class WritingCompositionError(Exception):
    pass


class WritingCompositionInvalidError(WritingCompositionError):
    pass
