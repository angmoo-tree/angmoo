"""Opt-in, thread-scoped query details. Nothing here is persisted to disk."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from threading import RLock
from typing import Any
from uuid import uuid4
from app.contracts.search_diagnostics import bounded_capture

Scope = tuple[str, str, str]


@dataclass
class Capture:
    until: datetime
    remaining: int = 10
    generation: str = ""


class DiagnosticCapture:
    def __init__(self) -> None:
        self._lock = RLock()
        self._enabled: dict[Scope, Capture] = {}
        self._admitted: dict[str, tuple[Scope, datetime, str]] = {}
        self._results: OrderedDict[str, tuple[Scope, datetime, str]] = OrderedDict()
        self._collectors = {}

    def _prune(self, now: datetime) -> None:
        self._enabled = {k: v for k, v in self._enabled.items() if v.until > now}
        self._admitted = {k: v for k, v in self._admitted.items() if v[1] > now
            and v[0] in self._enabled and self._enabled[v[0]].generation == v[2]}
        self._results = OrderedDict((k, v) for k, v in self._results.items() if v[1] > now)
        self._collectors = {k: v for k, v in self._collectors.items() if k in self._admitted}

    def configure(self, scope: Scope, enabled: bool) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(UTC)
            self._prune(now)
            if enabled:
                if len(self._enabled) >= 20 and scope not in self._enabled:
                    return {"enabled": False, "remaining": 0, "reason": "capture_capacity"}
                self._enabled[scope] = Capture(now + timedelta(minutes=30), generation=uuid4().hex)
            else:
                self._enabled.pop(scope, None)
                self._admitted = {k: v for k, v in self._admitted.items() if v[0] != scope}
                self._results = OrderedDict((k, v) for k, v in self._results.items() if v[0] != scope)
            self._prune(now)
            return self.status(scope)

    def status(self, scope: Scope) -> dict[str, Any]:
        with self._lock:
            self._prune(datetime.now(UTC))
            entry = self._enabled.get(scope)
            return {"enabled": entry is not None and entry.remaining > 0, "remaining": 0 if entry is None else entry.remaining, "expires_at": None if entry is None else entry.until.isoformat()}

    def admit(self, scope: Scope, request_id: str) -> None:
        with self._lock:
            now = datetime.now(UTC)
            self._prune(now)
            entry = self._enabled.get(scope)
            if entry is None or entry.remaining <= 0 or len(self._admitted) >= 20:
                return
            entry.remaining -= 1
            self._admitted[request_id] = (scope, entry.until, entry.generation)

    def generation(self, scope):
        # OFF is the common path: no clock, collector, timer or SQL listener.
        with self._lock:
            entry = self._enabled.get(scope)
            if entry is None or entry.remaining <= 0:
                return None
            return entry.generation if entry.until > datetime.now(UTC) else None

    def generation_active(self, scope, generation):
        with self._lock:
            entry = self._enabled.get(scope)
            return entry is not None and entry.generation == generation and entry.until > datetime.now(UTC)

    def bind_db(self, scope, request_id, generation, collector, attempt_number):
        with self._lock:
            if self.active(scope, request_id) and self._admitted[request_id][2] == generation:
                collector.bind(request_id, attempt_number)
                self._collectors[request_id] = (generation, collector)
                self._bound_results()

    def db_collector(self, scope, request_id):
        with self._lock:
            if not self.active(scope, request_id):
                return None
            return self._collectors.get(request_id)

    def _bound_results(self):
        # Reserve bounded numeric collectors as part of the 1 MiB budget.
        budget = 1024 * 1024 - 32 * 1024 * len(self._collectors)
        while self._results and (len(self._results) > 20 or sum(len(v[2].encode()) for v in self._results.values()) > budget):
            self._results.popitem(last=False)

    def active(self, scope: Scope, request_id: str) -> bool:
        with self._lock:
            self._prune(datetime.now(UTC))
            admitted = self._admitted.get(request_id)
            return admitted is not None and admitted[0] == scope

    def store(self, scope: Scope, request_id: str, details: list[dict], search_trace=None) -> None:
        with self._lock:
            if not self.active(scope, request_id):
                return
            owned = self._collectors.get(request_id)
            reserved = {"db_write": owned[1].payload()} if owned else None
            payload = json.dumps(bounded_capture(details, search_trace, reserved=reserved), ensure_ascii=True)
            if len(payload.encode()) > 64 * 1024:
                return
            self._results[request_id] = (scope, datetime.now(UTC) + timedelta(minutes=60), payload)
            self._results.move_to_end(request_id)
            self._bound_results()

    def read(self, scope: Scope, request_id: str) -> list[dict] | None:
        result = self.read_full(scope, request_id)
        return None if result is None else result["details"]

    def read_full(self, scope: Scope, request_id: str) -> dict | None:
        with self._lock:
            self._prune(datetime.now(UTC))
            row = self._results.get(request_id)
            if row is None or row[0] != scope:
                return None
            result = json.loads(row[2])
            result = {"details": result, "search_trace": None} if isinstance(result, list) else result
            owned = self._collectors.get(request_id)
            if owned is not None:
                result = bounded_capture(result["details"], result.get("search_trace"),
                    reserved={"db_write": owned[1].payload()})
            return result


capture = DiagnosticCapture()
