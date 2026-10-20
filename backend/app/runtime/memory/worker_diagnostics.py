"""Process-local stage reporting and nonblocking, fixed-size progress snapshots."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import sqlite3
from time import monotonic

from app.contracts.search_diagnostics import SearchFailure, SearchStage

current_worker: ContextVar[WorkerTrace | None] = ContextVar("search_worker_trace", default=None)


def failure(exc, stage=None):
    code = getattr(exc, "sqlite_errorcode", None)
    code = code if isinstance(code, int) and 0 <= code <= 65535 else None
    known = {
        "memory_vector_extension_integrity": "extension_integrity_failed",
        "memory_vector_mapping_missing": "mapping_missing",
        "memory_vector_invalid": "invalid_query",
        "memory_vector_worker_exited": "worker_exited",
        "memory_vector_cancelled": "cancelled",
        "memory_search_binding_mismatch": "result_decode_failed",
        "memory_search_result_mismatch": "result_decode_failed",
        "memory_search_cleanup_mismatch": "result_decode_failed",
    }
    args = getattr(exc, "args", ())
    internal = known.get(args[0]) if args and isinstance(args[0], str) else None
    reason = ("cancelled" if type(exc).__name__ == "CancelledError" else
        "deadline_exceeded" if isinstance(exc, TimeoutError) else
        "result_eof" if isinstance(exc, EOFError) or (stage == "result_transport" and isinstance(exc, OSError)
            and (getattr(exc, "winerror", None) in {109, 232, 233} or getattr(exc, "errno", None) == 32)) else
        "sqlite_busy" if code is not None and code & 255 == sqlite3.SQLITE_BUSY else
        "sqlite_locked" if code is not None and code & 255 == sqlite3.SQLITE_LOCKED else
        internal or ("extension_load_failed" if stage == "extension_load" else
        "worker_start_failed" if stage == "process_start" else
        "sqlite_error" if isinstance(exc, sqlite3.Error) else "unknown_error"))
    kind = type(exc).__name__
    allowed = {"TimeoutError", "OperationalError", "DatabaseError", "OSError",
        "MemoryVectorProjectionError", "EOFError", "ValueError"}
    if kind not in allowed and isinstance(exc, OSError):
        kind = "OSError"
    return SearchFailure(failure_code=reason, failure_stage=stage,
        exception_kind=kind if kind in allowed else "Unknown", sqlite_error_code=code)


@dataclass
class WorkerTrace:
    axis: str
    deadline: float
    domain: str = "child"
    progress: object = None
    detailed: bool = False
    started: float = field(default_factory=monotonic)
    stages: dict = field(default_factory=dict)
    last_stage: str | None = None
    error: SearchFailure | None = None
    metadata: dict = field(default_factory=dict)
    dropped: int = 0

    def publish(self, row):
        if self.detailed:
            self.stages[row.stage] = row
        if self.progress is not None:
            try:
                if not self.progress.write(row.model_dump(mode="json"), self.metadata):
                    self.dropped += 1
            except Exception:
                self.dropped += 1

    @contextmanager
    def phase(self, name):
        started = monotonic()
        self.last_stage = name
        if name == "nn_query":
            self.metadata["nn_query_started"] = True
        row = SearchStage(axis=self.axis, stage=name, clock_domain=self.domain,
            state="running", start_ms=(started-self.started)*1000,
            budget_at_start_ms=max(0, self.deadline-started)*1000)
        self.publish(row)
        state = "completed"
        try:
            yield
        except BaseException as exc:
            state = "cancelled" if type(exc).__name__ == "CancelledError" else "failed"
            if self.error is None:
                self.error = failure(exc, name)
            raise
        finally:
            now = monotonic()
            self.publish(row.model_copy(update={"state": state, "end_ms": (now-self.started)*1000,
                "elapsed_ms": (now-started)*1000, "remaining_at_end_ms": max(0,self.deadline-now)*1000,
                "deadline_exceeded": now >= self.deadline}))

    def snapshot(self):
        return {"stages": [row.model_dump(mode="json") for row in self.stages.values()],
            "failure": None if self.error is None else self.error.model_dump(mode="json"),
            "last_stage": self.last_stage, "metadata": self.metadata, "dropped": self.dropped}


@contextmanager
def phase(name):
    trace = current_worker.get()
    if trace is None:
        yield
    else:
        with trace.phase(name):
            yield


def capture_failure(exc):
    trace = current_worker.get()
    if trace is not None and trace.error is None:
        trace.error = failure(exc, trace.last_stage)
