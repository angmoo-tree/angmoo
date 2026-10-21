"""Thread-scoped lease execution budget and bounded, content-free diagnostics.

The executor owns this scope; the SQLite adapter forwards its deadline to the
writer. Domain lease rules and repository ports do not depend on executor time.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from app.core.sqlite_concurrency import SqliteRetryPolicy


@dataclass
class LeaseOperation:
    operation_id: str
    deadline: float | None
    retry_policy: SqliteRetryPolicy | None = None
    _facts: dict[str, Any] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def record(self, facts: dict[str, Any]) -> None:
        allowed = {"result", "attempt", "sqlite_code", "sqlite_primary_code", "sqlite_name",
                   "queue_ms", "checkout_ms", "acquire_ms", "lock_wait_ms", "transaction_ms", "attempt_ms",
                   "total_ms", "cleanup_ms", "retry_delay_ms", "caller_cancelled", "worker_state"}
        with self._lock:
            self._facts.update({k: v for k, v in facts.items() if k in allowed})
            if facts.get("result") in {"committed", "busy", "exhausted"}:
                self._facts["write_result"] = facts["result"]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"operation_id": self.operation_id, **self._facts}


_operation: ContextVar[LeaseOperation | None] = ContextVar("scheduler_lease_operation", default=None)


def current_lease_operation() -> LeaseOperation | None:
    return _operation.get()


@contextmanager
def lease_operation_scope(operation: LeaseOperation):
    token = _operation.set(operation)
    try:
        yield
    finally:
        _operation.reset(token)
