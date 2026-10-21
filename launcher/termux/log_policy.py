"""Launch-scoped log policy. No product imports, persistent preference or timer."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import re
import time

VERSION = "angmoo-service-log.v1"
ENVIRONMENT = "ANGMOO_SERVICE_LOG_POLICY"


def duration(mode, value=None):
    if mode not in ("basic", "detailed") or mode == "basic" and value is not None:
        raise ValueError("log_options_invalid")
    if mode == "basic":
        return 0
    if value is None:
        return 900
    if not re.fullmatch(r"(?:[1-9]|[1-5][0-9]|60)m", value):
        raise ValueError("log_options_invalid")
    return int(value[:-1]) * 60


def new_policy(launch_id, mode, seconds, *, now=None):
    now = now or datetime.now(timezone.utc)
    return {"profile_version": VERSION, "launch_id": launch_id, "requested_mode": mode,
            "started_at_utc": now.isoformat(), "duration_seconds": seconds,
            "detailed_until_utc": (now + timedelta(seconds=seconds)).isoformat() if seconds else None}


class PolicyClock:
    def __init__(self, policy, *, monotonic=time.monotonic, wall=time.time):
        self.policy, self.monotonic, self.wall = policy, monotonic, wall
        self.expiry = datetime.fromisoformat(policy["detailed_until_utc"]).timestamp() if policy["detailed_until_utc"] else 0
        remaining = min(policy["duration_seconds"], max(0, self.expiry - wall()))
        self.deadline = monotonic() + remaining
        self.expired = policy["requested_mode"] != "detailed" or remaining <= 0

    def remaining(self):
        value = min(self.deadline - self.monotonic(), self.expiry - self.wall())
        self.expired = self.expired or value <= 0
        return 0 if self.expired else value

    def envelope(self, service):
        return json.dumps({**self.policy, "service": service, "remaining_seconds": self.remaining()}, separators=(",", ":"))


def acknowledge(raw, service, launch_id, policy):
    """Only an owned service pipe can confirm its own immutable launch policy."""
    if service not in ("backend", "frontend") or len(raw) > 2048 or not policy:
        return None
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    fields = {"event", "profile_version", "service", "launch_id", "effective_mode", "detailed_until_utc"}
    if not isinstance(value, dict) or set(value) != fields or value["event"] != "service_log_policy_applied":
        return None
    if value["profile_version"] != VERSION or value["service"] != service or value["launch_id"] != launch_id:
        return None
    if value["effective_mode"] not in ("basic", "detailed") or value["detailed_until_utc"] != policy["detailed_until_utc"]:
        return None
    if policy["requested_mode"] == "basic" and value["effective_mode"] != "basic":
        return None
    return value


def describe(policy, acknowledgements=None, *, now=None):
    if not policy:
        return {"requested_mode": "legacy", "effective_mode": "unknown", "source_confirmation": "legacy"}
    current = now or datetime.now(timezone.utc)
    expiry = policy.get("detailed_until_utc")
    effective = "detailed" if policy["requested_mode"] == "detailed" and expiry and current < datetime.fromisoformat(expiry) else "basic"
    return {**policy, "effective_mode": effective, "mode_basis": "utc_estimate; source_monotonic_not_observed",
            "sources": {service: (acknowledgements or {}).get(service, {"state": "unconfirmed"}) for service in ("backend", "frontend")}}
