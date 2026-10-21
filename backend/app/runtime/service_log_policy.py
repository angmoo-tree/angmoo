"""Opt-in Termux service logging at the runtime boundary; no capture or DB I/O."""
from __future__ import annotations

from datetime import datetime
import json
import logging
import math
import os
import re
import sys
import time

VERSION = "angmoo-service-log.v1"
ENVIRONMENT = "ANGMOO_SERVICE_LOG_POLICY"
FIELDS = {"profile_version", "service", "launch_id", "requested_mode", "started_at_utc",
          "duration_seconds", "detailed_until_utc", "remaining_seconds"}


def decode(raw: str, launch_id: str) -> dict:
    if len(raw) > 4096:
        raise ValueError("policy_size")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != FIELDS or value["profile_version"] != VERSION or value["service"] != "backend":
        raise ValueError("policy_schema")
    if not re.fullmatch(r"[0-9a-f]{32}", launch_id) or value["launch_id"] != launch_id:
        raise ValueError("policy_launch")
    seconds, remaining = value["duration_seconds"], value["remaining_seconds"]
    if type(seconds) is not int or not 0 <= seconds <= 3600 or type(remaining) not in (float, int) or not math.isfinite(remaining) or not 0 <= remaining <= seconds:
        raise ValueError("policy_duration")
    started = datetime.fromisoformat(value["started_at_utc"])
    if started.tzinfo is None:
        raise ValueError("policy_clock")
    if value["requested_mode"] == "basic":
        if seconds or remaining or value["detailed_until_utc"] is not None:
            raise ValueError("policy_basic")
    elif value["requested_mode"] == "detailed":
        expiry = datetime.fromisoformat(value["detailed_until_utc"])
        if not 60 <= seconds <= 3600 or seconds % 60 or expiry.tzinfo is None or (expiry - started).total_seconds() != seconds:
            raise ValueError("policy_clock")
    else:
        raise ValueError("policy_mode")
    return value


class ServiceLogPolicy:
    def __init__(self, value, *, monotonic=time.monotonic, wall=time.time):
        self.value, self.monotonic, self.wall = value, monotonic, wall
        self.deadline = monotonic() + value["remaining_seconds"]
        self.expiry = datetime.fromisoformat(value["detailed_until_utc"]).timestamp() if value["detailed_until_utc"] else 0
        self.expired = value["requested_mode"] != "detailed"

    def detailed(self):
        self.expired = self.expired or self.monotonic() >= self.deadline or self.wall() >= self.expiry
        return not self.expired

    def acknowledgement(self):
        return {"event": "service_log_policy_applied", "profile_version": VERSION, "service": "backend",
                "launch_id": self.value["launch_id"], "effective_mode": "detailed" if self.detailed() else "basic",
                "detailed_until_utc": self.value["detailed_until_utc"]}


_policy = None
_initialized = False


def configured_policy():
    global _policy, _initialized
    raw = os.environ.get(ENVIRONMENT)
    if raw is None:
        return None  # Docker, embedding hosts and sidecar keep their existing contract.
    if not _initialized:
        _initialized = True
        launch = os.environ.get("ANGMOO_LAUNCH_ID", "")
        try:
            value = decode(raw, launch)
        except (ValueError, TypeError, KeyError, OverflowError):
            value = {"launch_id": launch if re.fullmatch(r"[0-9a-f]{32}", launch) else "", "requested_mode": "basic",
                     "remaining_seconds": 0, "detailed_until_utc": None}
            if sys.stderr is not None:
                print('{"event":"service_log_policy_invalid","service":"backend","fallback":"basic"}', file=sys.stderr, flush=True)
        _policy = ServiceLogPolicy(value)
        if sys.stderr is not None:
            print(json.dumps(_policy.acknowledgement(), separators=(",", ":")), file=sys.stderr, flush=True)
    return _policy


def route_class(path):
    # Only fixed categories reach the access formatter, never paths/queries/IDs.
    if isinstance(path, str):
        clean = path.split("?", 1)[0]
        if clean == "/health":
            return "health"
        if clean.startswith("/api/v1/"):
            return "api"
    return "other"


class ServiceLogFilter(logging.Filter):
    def filter(self, record):
        policy = configured_policy()
        if policy is None:
            return True
        detailed = policy.detailed()
        if record.name == "uvicorn.access":
            if not isinstance(record.args, tuple) or len(record.args) != 5:
                return False
            _, method, path, _, status = record.args
            if type(status) is not int or not 100 <= status <= 599:
                return False
            if not detailed and status < 400:
                return False
            record.msg = '%s - "%s %s HTTP/%s" %d'
            record.args = ("local", method if method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS") else "OTHER", route_class(path), "1.1", status)
            return True
        if record.levelno >= logging.WARNING:
            return True
        if record.levelno < logging.INFO:
            return False
        if record.name.startswith("uvicorn"):
            return str(record.msg).startswith(("Started server process", "Waiting for application", "Application startup", "Shutting down", "Application shutdown", "Finished server process", "Uvicorn running"))
        if record.name == "app.runtime.memory.search_worker_pool":
            # Preparation failures must remain visible in basic mode.
            return detailed or "phase=failed" in record.getMessage() or "phase=retired" in record.getMessage()
        return detailed and str(record.msg).startswith(("scheduler_lease_queue ", "scheduler_lease_transaction "))
