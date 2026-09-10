"""Opt-in, thread-scoped query details. Nothing here is persisted to disk."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from threading import RLock
from typing import Any

Scope = tuple[str, str, str]


@dataclass
class Capture:
    until: datetime
    remaining: int = 10


class DiagnosticCapture:
    def __init__(self) -> None:
        self._lock = RLock()
        self._enabled: dict[Scope, Capture] = {}
        self._admitted: dict[str, tuple[Scope, datetime]] = {}
        self._results: OrderedDict[str, tuple[Scope, datetime, str]] = OrderedDict()

    def _prune(self, now: datetime) -> None:
        self._enabled = {k: v for k, v in self._enabled.items() if v.until > now and v.remaining > 0}
        self._admitted = {k: v for k, v in self._admitted.items() if v[1] > now}
        self._results = OrderedDict((k, v) for k, v in self._results.items() if v[1] > now)

    def configure(self, scope: Scope, enabled: bool) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(UTC)
            self._prune(now)
            if enabled:
                if len(self._enabled) >= 20 and scope not in self._enabled:
                    return {"enabled": False, "remaining": 0, "reason": "capture_capacity"}
                self._enabled[scope] = Capture(now + timedelta(minutes=30))
            else:
                self._enabled.pop(scope, None)
                self._admitted = {k: v for k, v in self._admitted.items() if v[0] != scope}
                self._results = OrderedDict((k, v) for k, v in self._results.items() if v[0] != scope)
            return self.status(scope)

    def status(self, scope: Scope) -> dict[str, Any]:
        with self._lock:
            self._prune(datetime.now(UTC))
            entry = self._enabled.get(scope)
            return {"enabled": entry is not None, "remaining": 0 if entry is None else entry.remaining, "expires_at": None if entry is None else entry.until.isoformat()}

    def admit(self, scope: Scope, request_id: str) -> None:
        with self._lock:
            now = datetime.now(UTC)
            self._prune(now)
            entry = self._enabled.get(scope)
            if entry is None or len(self._admitted) >= 20:
                return
            entry.remaining -= 1
            self._admitted[request_id] = (scope, now + timedelta(minutes=60))

    def active(self, scope: Scope, request_id: str) -> bool:
        with self._lock:
            self._prune(datetime.now(UTC))
            admitted = self._admitted.get(request_id)
            return admitted is not None and admitted[0] == scope

    def store(self, scope: Scope, request_id: str, details: list[dict]) -> None:
        with self._lock:
            if not self.active(scope, request_id):
                return
            payload = json.dumps(details, ensure_ascii=True)
            if len(payload.encode()) > 64 * 1024:
                return
            self._results[request_id] = (scope, datetime.now(UTC) + timedelta(minutes=60), payload)
            self._results.move_to_end(request_id)
            while len(self._results) > 20 or sum(len(v[2].encode()) for v in self._results.values()) > 1024 * 1024:
                self._results.popitem(last=False)

    def read(self, scope: Scope, request_id: str) -> list[dict] | None:
        with self._lock:
            self._prune(datetime.now(UTC))
            row = self._results.get(request_id)
            return json.loads(row[2]) if row is not None and row[0] == scope else None


capture = DiagnosticCapture()
