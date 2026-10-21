from datetime import datetime, timezone
import json
import logging
import logging.config
import sys

import pytest

from app.runtime import service_log_policy as policy
from app.runtime.logging_config import uvicorn_logging_config


def envelope(mode="detailed", seconds=900, remaining=500):
    return {"profile_version": policy.VERSION, "service": "backend", "launch_id": "a"*32,
            "requested_mode": mode, "started_at_utc": datetime.fromtimestamp(1000, timezone.utc).isoformat(),
            "duration_seconds": seconds, "remaining_seconds": remaining,
            "detailed_until_utc": datetime.fromtimestamp(1000+seconds, timezone.utc).isoformat() if seconds else None}


def test_decode_rejects_scope_duration_and_unknown_fields():
    value = envelope()
    assert policy.decode(json.dumps(value), "a"*32) == value
    for change in ({"remaining_seconds": float("inf")}, {"remaining_seconds": True}, {"duration_seconds": 3601}, {"service": "frontend"}, {"launch_id": "b"*32}, {"body": "private"}, {"detailed_until_utc": "1900-01-01T00:00:00+00:00"}):
        with pytest.raises((ValueError, TypeError)):
            policy.decode(json.dumps({**value, **change}), "a"*32)


def test_late_init_uses_absolute_expiry_and_never_reenters_after_clock_rollback():
    wall, mono = [1800], [10]
    value = policy.ServiceLogPolicy(envelope(), wall=lambda: wall[0], monotonic=lambda: mono[0])
    assert value.detailed()
    wall[0] = 1900
    assert not value.detailed()
    wall[0] = 1700
    assert not value.detailed()
    value = policy.ServiceLogPolicy(envelope(remaining=1), wall=lambda: wall[0], monotonic=lambda: mono[0])
    mono[0] += 2
    assert not value.detailed()


def test_invalid_explicit_policy_falls_back_once_and_absent_keeps_original(monkeypatch, capsys):
    monkeypatch.setattr(policy, "_initialized", False); monkeypatch.setattr(policy, "_policy", None)
    monkeypatch.delenv(policy.ENVIRONMENT, raising=False)
    assert policy.configured_policy() is None
    assert capsys.readouterr().err == ""
    monkeypatch.setenv(policy.ENVIRONMENT, "private invalid JSON")
    monkeypatch.setenv("ANGMOO_LAUNCH_ID", "a"*32)
    assert not policy.configured_policy().detailed()
    assert policy.configured_policy() is policy.configured_policy()
    events = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [event["event"] for event in events] == ["service_log_policy_invalid", "service_log_policy_applied"]
    assert "private" not in str(events)


def test_basic_retains_failures_but_source_filters_access_success_and_preparation_success(monkeypatch):
    current = policy.ServiceLogPolicy(envelope("basic", 0, 0))
    monkeypatch.setattr(policy, "configured_policy", lambda: current)
    filter_ = policy.ServiceLogFilter()
    def record(name, level, text, args=()):
        return logging.LogRecord(name, level, "", 0, text, args, None)
    assert not filter_.filter(record("uvicorn.access", logging.INFO, "access", ("ip", "GET", "/api/v1/chat?api_key=private", "1.1", 200)))
    failure = record("uvicorn.access", logging.INFO, "access", ("ip", "GET", "/api/v1/chat?api_key=private", "1.1", 500))
    assert filter_.filter(failure)
    assert failure.args == ("local", "GET", "api", "1.1", 500)
    assert "private" not in failure.getMessage()
    assert not filter_.filter(record("app.runtime.memory.search_worker_pool", logging.INFO, "memory_worker_preparation ready"))
    assert filter_.filter(record("app.runtime.memory.search_worker_pool", logging.WARNING, "memory_worker_preparation timeout"))
    assert filter_.filter(record("app.runtime.resident.scheduler", logging.WARNING, "scheduler_recovery code=deadline"))
    assert filter_.filter(record("uvicorn.error", logging.INFO, "Application startup complete."))
    assert not filter_.filter(record("unknown", logging.INFO, "private"))


def test_detailed_is_allowlisted_not_global_debug(monkeypatch):
    current = policy.ServiceLogPolicy(envelope(), wall=lambda: 1200)
    monkeypatch.setattr(policy, "configured_policy", lambda: current)
    filter_ = policy.ServiceLogFilter()
    for name, text in (("app.runtime.memory.search_worker_pool", "memory_worker_preparation ready"), ("app.runtime.resident.lease_executor", "scheduler_lease_queue operation=heartbeat")):
        assert filter_.filter(logging.LogRecord(name, logging.INFO, "", 0, text, (), None))
    assert not filter_.filter(logging.LogRecord("sqlalchemy.engine", logging.DEBUG, "", 0, "parameters", (), None))


def test_only_explicit_runtime_configuration_adds_owned_filters(monkeypatch):
    monkeypatch.delenv(policy.ENVIRONMENT, raising=False)
    assert "filters" not in uvicorn_logging_config()
    monkeypatch.setenv(policy.ENVIRONMENT, json.dumps(envelope("basic", 0, 0)))
    monkeypatch.setenv("ANGMOO_LAUNCH_ID", "a"*32)
    monkeypatch.setattr(policy, "_initialized", False); monkeypatch.setattr(policy, "_policy", None)
    config = uvicorn_logging_config()
    assert config["handlers"]["default"]["filters"] == ["termux_policy"]
    assert "root" not in config
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # Sidecar never calls this builder; even a frozen embedding host does not
    # attach Termux filters to its JSON stdout protocol.
