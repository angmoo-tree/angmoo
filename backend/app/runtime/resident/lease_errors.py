"""Execution failures; distinct from lease ownership loss and business errors."""


class SchedulerHeartbeatDeadlineExceeded(RuntimeError):
    reason_code = "scheduler_heartbeat_deadline_exceeded"
