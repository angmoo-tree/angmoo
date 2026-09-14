"""Bounded, content-free observations shared by retrieval participants.

This is not a logger or a query executor. Request-local context follows async
tasks; each observation is copied immediately and never retains domain objects.
"""
from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import math
import re
from time import monotonic
from typing import Any

VERSION = "chat-retrieval-diagnostics.v1"
MAX_BYTES = 16 * 1024
MAX_EVENTS = 48
_CRITICAL = frozenset({"router", "planner", "both_merge", "crg_input", "crg_completed", "workflow_failed", "evidence_kind", "planner_validation", "graph_failure", "decision_failure", "decision_summary"})
_CRITICAL |= frozenset({"social_context_prepared", "social_context_consumed", "hybrid_axis", "hybrid_embedding", "hybrid_fusion"})
_CODES = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,79}$")
_TEXT_KEYS = frozenset({"axis", "operation", "method", "status", "reason", "recipe", "direction", "ranking", "route", "model", "thinking_level", "source", "phase", "validation_code", "failure_stage", "finish_reason", "call_ref", "terminal_code", "repair_node"})
_NUM_KEYS = frozenset({"relationships", "evidence", "nodes", "paths", "step", "queries", "planned", "candidates", "accepted", "excluded", "returned", "input", "output", "duplicates", "unmatched", "limit", "hops", "depth", "fanout", "items", "chars", "elapsed_ms", "input_tokens", "output_tokens", "thought_tokens", "response_chars", "logical_calls", "physical_attempts", "groups", "scanned", "bytes_scanned", "attempt"})
_BOOL_KEYS = frozenset({"executed", "skipped", "counterpart_filter", "thread_filter", "time_filter", "limit_reached", "repair_used", "first_pass_valid", "parallel", "truncated", "search_text_present", "repair_exhausted", "physical_count_complete"})
_TEXT_KEYS |= frozenset({"field_path", "validation_pass", "applied_rule", "expected_direction", "returned_direction", "response_state", "provider", "trace_version", "function", "check", "failure_reason"})
_NUM_KEYS |= frozenset({"tool_count", "total_tokens", "max_output_tokens", "timeout_seconds", "detail_omitted", "call", "entity_index"})
_BOOL_KEYS |= frozenset({"matched", "response_observed", "trace_complete", "detail_captured"})
_TEXT_KEYS |= frozenset({"snapshot_id", "content_hash", "recall_mode", "capability_fingerprint"})


@dataclass(slots=True)
class Observation:
    request_id: str = ""
    detailed: bool = False
    started: float = field(default_factory=monotonic)
    events: list[dict[str, Any]] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    omitted: int = 0
    trace_active: bool = False
    detail_omitted: int = 0
    trace_aliases: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)

    def payload(self) -> dict[str, Any]:
        events = list(self.events)
        if self.trace_active:
            events.append({"event": "decision_summary", "trace_version": "decision-trace.v2",
                           "detail_captured": self.detailed, "detail_omitted": self.detail_omitted,
                           "trace_complete": self.omitted == 0 and self.detail_omitted == 0})
        result = {"version": VERSION, "events": events, "omitted_events": self.omitted}
        while (len(events) > MAX_EVENTS or len(json.dumps(result, ensure_ascii=True).encode()) > MAX_BYTES) and events:
            index = next((i for i, row in enumerate(events) if row["event"] not in _CRITICAL), 0)
            events.pop(index)
            result["omitted_events"] += 1
        if self.trace_active and events and events[-1]["event"] == "decision_summary":
            events[-1]["trace_complete"] = result["omitted_events"] == 0 and self.detail_omitted == 0
        return result


current: ContextVar[Observation | None] = ContextVar("retrieval_observation", default=None)
step_context: ContextVar[tuple[str, int] | None] = ContextVar("retrieval_step", default=None)


@contextmanager
def observing_step(axis: str, index: int):
    token = step_context.set((axis, index))
    started = monotonic()
    try:
        yield
    finally:
        observe("step_elapsed", elapsed_ms=(monotonic() - started) * 1000)
        step_context.reset(token)


def observe(event: str, **values: object) -> None:
    """Only caller-selected codes, numbers and flags cross the basic boundary."""
    target = current.get()
    if target is None:
        return
    try:
        if len(target.events) >= MAX_EVENTS:
            target.omitted += 1
            if event not in _CRITICAL:
                return
            index = next((i for i, row in enumerate(target.events) if row["event"] not in _CRITICAL), 0)
            target.events.pop(index)
        if not _CODES.fullmatch(event):
            return
        row: dict[str, Any] = {"event": event}
        if step_context.get() is not None:
            row["axis"], row["step"] = step_context.get()  # type: ignore[misc]
        for key, value in values.items():
            if key in _BOOL_KEYS and isinstance(value, bool):
                row[key] = value
            elif key in _NUM_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1_000_000_000:
                row[key] = round(value, 3)
            elif key in _TEXT_KEYS and isinstance(value, str) and _CODES.fullmatch(value):
                row[key] = value
        target.events.append(row)
    except Exception:
        # Observation must never become a retrieval failure. No exception text.
        target.omitted += 1


def detail(**values: object) -> None:
    """Explicit, opt-in query fields only; never serialize query/domain objects."""
    target = current.get()
    if target is None or not target.detailed:
        return
    try:
        from app.core.redaction import redact_secret_text
        allowed = {"search_text", "normalized_query", "occurred_from", "occurred_to", "counterpart", "subject", "entity_ref", "operation"}
        row = {key: redact_secret_text(value[:1500]) for key, value in values.items() if key in allowed and isinstance(value, str)}
        if step_context.get() is not None:
            row["axis"], row["step"] = step_context.get()  # type: ignore[misc]
        if row:
            candidate = [*target.details, row]
            if len(target.details) < 24 and len(json.dumps(candidate, ensure_ascii=True).encode()) <= 64 * 1024:
                target.details.append(row)
            else:
                target.detail_omitted += 1
    except Exception:
        target.omitted += 1
