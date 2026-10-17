"""Bounded, content-free DB timings. Session spans are not writer lock durations."""
from threading import RLock
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Stage = Literal["admission", "workflow_checkpoint", "diagnostic_persist", "response_finalize", "cancel_or_failure", "post_commit"]


class WriteAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int
    stage: Stage
    database_id: str = Field(max_length=64)
    attempt: int = Field(ge=1)
    basis: Literal["begin_immediate", "write_span_only"]
    outcome: Literal["committed", "rolled_back", "busy", "partial"]
    start_offset_ms: float | None = None
    end_offset_ms: float | None = None
    checkout_ms: float | None = None
    acquire_ms: float | None = None
    hold_ms: float | None = None
    commit_ms: float | None = None
    rollback_ms: float | None = None
    write_span_ms: float | None = None
    retry_wait_ms: float | None = None
    diagnostic_persist_ms: float | None = None


class DbWriteDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["chat-db-write.v1"] = "chat-db-write.v1"
    request_id: str
    attempt_number: int
    coverage: Literal["complete", "partial", "write_span_only", "no_writes"]
    attempts: list[WriteAttempt] = Field(max_length=64)
    omitted_attempts: int
    completed_attempts: int
    longest_hold_ms: float | None
    total_hold_ms: float | None
    total_write_span_ms: float | None
    retry_count: int
    retry_wait_ms: float | None


def _ms(row, start, end):
    a, b = row.get(start), row.get(end)
    return round((b - a) / 1_000_000, 3) if type(a) is int and type(b) is int and b >= a else None


class DbWriteCollector:
    """O(1) bounded numeric work per boundary, serialization only on read/export."""
    def __init__(self):
        self.lock = RLock()
        self.request_id, self.attempt_number = "pending_admission", 1
        self.pending, self.rows = {}, []
        self.completed = self.omitted = self.retries = 0
        self.hold_total = self.hold_max = self.span_total = self.retry_total = None
        self.partial = self.spans = False
        self.origin_ns = None

    def bind(self, request_id, attempt_number):
        self.request_id, self.attempt_number = request_id, attempt_number

    def observe(self, event):
        if event.get("event") not in {"sqlite", "sqlite_attempt", "session_write"}:
            return
        with self.lock:
            span = event.get("span_id")
            if not isinstance(span, str) or len(span) > 64:
                return
            attempt = event.get("attempt", 1)
            stamp = event.get("monotonic_ns")
            if type(attempt) is not int or attempt < 1 or type(stamp) is not int or stamp < 0:
                self.partial = True
                return
            if self.origin_ns is None:
                self.origin_ns = stamp
            key = (span, attempt)
            boundary = event.get("boundary")
            if event.get("event") == "sqlite_attempt":
                if event.get("result") == "busy" and key in self.pending:
                    self.pending[key]["busy"] = event["monotonic_ns"]
                    self._finish(key, "busy")
                return
            if boundary == "cleanup_complete":
                for pending_key in tuple(self.pending):
                    if pending_key[0] == span:
                        self._finish(pending_key, "partial")
                return
            if key not in self.pending:
                if boundary not in {"checkout_started", "begin_started", "write_started", "retry_wait_started"}:
                    return
                if len(self.pending) >= 64:
                    self.omitted += 1; self.partial = True
                    return
                stage = event.get("chat_stage", "workflow_checkpoint")
                stage = stage if stage in {"admission", "workflow_checkpoint", "diagnostic_persist", "response_finalize", "cancel_or_failure", "post_commit"} else "workflow_checkpoint"
                identity = event.get("database_id", "unknown")
                identity = identity if isinstance(identity, str) and (identity == "in_memory" or len(identity) == 64 and all(c in "0123456789abcdef" for c in identity)) else "unknown"
                self.pending[key] = {"stage": stage, "database_id": identity, "attempt": attempt,
                    "basis": "write_span_only" if event["event"] == "session_write" else "begin_immediate"}
            row = self.pending[key]
            if boundary == "diagnostic_persist":
                duration = event.get("elapsed_ms")
                if type(duration) in (int, float) and 0 <= duration < float("inf"):
                    row["diagnostic_persist_ms"] = row.get("diagnostic_persist_ms", 0) + duration
                else:
                    self.partial = True
            if boundary in {"checkout_started", "checkout_complete", "begin_started", "acquired", "write_started",
                "commit_started", "committed", "rollback_started", "rolled_back", "retry_wait_started", "retry_wait_complete"}:
                row[boundary] = event["monotonic_ns"]
            if boundary == "retry_wait_complete":
                duration = _ms(row, "retry_wait_started", "retry_wait_complete")
                self.retries += 1
                if duration is not None: self.retry_total = (self.retry_total or 0) + duration
                self.pending.pop(key)
            elif boundary in {"committed", "rolled_back"}:
                self._finish(key, boundary)
            elif boundary in {"end_unwrapped", "end_missing", "finish_failed"}:
                self._finish(key, "partial")

    def _finish(self, key, outcome):
        row = self.pending.pop(key)
        end = outcome
        hold = _ms(row, "acquired", end) if row["basis"] == "begin_immediate" else None
        span = _ms(row, "write_started", end)
        partial = outcome == "partial" or (outcome in {"committed", "rolled_back"} and hold is None and span is None)
        self.partial |= partial
        self.spans |= row["basis"] == "write_span_only"
        self.completed += outcome in {"committed", "rolled_back"}
        if hold is not None:
            self.hold_total = (self.hold_total or 0) + hold
            self.hold_max = max(self.hold_max or 0, hold)
        if span is not None: self.span_total = (self.span_total or 0) + span
        if len(self.rows) >= 64:
            self.omitted += 1
            return
        self.rows.append(dict(sequence=len(self.rows) + 1, **{k: row[k] for k in ("stage", "database_id", "attempt", "basis")},
            start_offset_ms=_ms({**row, "origin": self.origin_ns}, "origin", "acquired" if row["basis"] == "begin_immediate" else "write_started"),
            end_offset_ms=_ms({**row, "origin": self.origin_ns}, "origin", end),
            outcome=outcome, checkout_ms=_ms(row, "checkout_started", "checkout_complete"),
            acquire_ms=_ms(row, "begin_started", "acquired" if "acquired" in row else "busy"),
            hold_ms=hold, commit_ms=_ms(row, "commit_started", "committed"),
            rollback_ms=_ms(row, "rollback_started", "rolled_back"), write_span_ms=span,
            retry_wait_ms=None, diagnostic_persist_ms=row.get("diagnostic_persist_ms")))

    def payload(self):
        with self.lock:
            coverage = "partial" if self.partial or self.pending or self.omitted else "write_span_only" if self.spans else "complete" if self.completed else "no_writes"
            return DbWriteDiagnostics(request_id=self.request_id, attempt_number=self.attempt_number,
                coverage=coverage, attempts=list(self.rows), omitted_attempts=self.omitted + len(self.pending),
                completed_attempts=self.completed, longest_hold_ms=self.hold_max, total_hold_ms=self.hold_total,
                total_write_span_ms=self.span_total, retry_count=self.retries, retry_wait_ms=self.retry_total).model_dump(mode="json")
