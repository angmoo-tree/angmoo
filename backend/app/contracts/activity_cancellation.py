"""Task-scoped cancellation intent; never a process-wide mutable flag."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum

class CancellationReason(StrEnum):
    HEARTBEAT = "scheduler_heartbeat_unavailable"
    LEASE_LOST = "scheduler_lease_lost"
    SHUTDOWN = "runtime_shutdown"
    UNKNOWN = "unknown_cancelled"

@dataclass
class CancellationIntent:
    reason: CancellationReason = CancellationReason.UNKNOWN

_intent: ContextVar[CancellationIntent | None] = ContextVar("activity_cancellation", default=None)

@contextmanager
def cancellation_scope(intent):
    token = _intent.set(intent)
    try:
        yield
    finally:
        _intent.reset(token)

def cancellation_reason():
    current = _intent.get()
    return current.reason if current else CancellationReason.UNKNOWN

RECOVERY_POLICY_KEY = "activity_recovery_policy"
RECOVERY_REVISION = "sns-activity-recovery.v1"
