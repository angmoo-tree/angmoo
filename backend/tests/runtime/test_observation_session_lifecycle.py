"""Finished sessions retain evidence without restarting their runtime writers."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
from threading import Event
from time import monotonic

import pytest

from app.core import work_observation as observation
from app.runtime.diagnostics.sns_observation import SNSObserver, active_session
from app.runtime.diagnostics.sns_observation_report import (
    export_session, session_status, start_session, stop_session,
)
from tests.runtime.test_memory_pipeline_observation import recorded_files
from tests.runtime.test_sns_observation import data_root


def wait_until(predicate):
    until = monotonic() + 5
    while not predicate():
        assert monotonic() < until, "recorder did not reach the expected state"
        Event().wait(0.01)


def wake(observer):
    observer.queue.put(None)
    observer.queue.join()


def finalized(root, session):
    health = session_status(root, session)["recorder_health"]
    return bool(health) and health[0]["flush_complete"]


@pytest.mark.parametrize("ending", ["stop", "deadline"])
def test_finished_session_disconnects_preserves_files_and_accepts_next_session(data_root, tmp_path, ending):
    clock = [datetime.now(UTC)]
    manifest = start_session(data_root, world_id="world-1", minutes=1, tail_minutes=1, now=clock[0])
    observer = SNSObserver(data_root, now=lambda: clock[0], heartbeat_seconds=0.02)
    directory = data_root / "diagnostics/sns" / manifest["session_id"]
    try:
        wait_until(lambda: observation.enabled() and session_status(data_root, manifest["session_id"])["recorder_health"])
        with observation.scope(world_id="world-1", actor_id="actor-1"):
            observation.emit("result", item_id="accepted", boundary="committed")
        attempt = observer.begin(activity_id="activity", agent_run_id="run", world_id="world-1",
            actor_id="actor-1", activity_started_at=clock[0])
        assert attempt is not None
        observer.queue.join()
        if ending == "stop":
            stop_session(data_root, manifest["session_id"], now=clock[0])
        else:
            clock[0] += timedelta(minutes=2)
        wake(observer)
        wait_until(lambda: finalized(data_root, manifest["session_id"]))
        assert not observation.enabled()
        status = session_status(data_root, manifest["session_id"])
        assert status["memory_pipeline"]["processes"][0]["final"]
        assert status["memory_pipeline"]["processes"][0]["queued"] == 0
        assert status["recorder_health"][0]["queued_count"] == 0
        before = recorded_files(directory)
        for _ in range(3):
            wake(observer)
        assert recorded_files(directory) == before
        assert observer.close()
        assert recorded_files(directory) == before
    finally:
        observer.close()

    restarted = SNSObserver(data_root, now=lambda: clock[0], heartbeat_seconds=0.02)
    try:
        for _ in range(3):
            wake(restarted)
        assert not observation.enabled() and restarted._active is None
        assert active_session(data_root)["session_id"] == manifest["session_id"]
        assert recorded_files(directory) == before
        coverage = export_session(data_root, manifest["session_id"], destination=tmp_path / "export", now=clock[0])
        assert coverage["flush_complete"] is True
        assert recorded_files(directory) == before
        second = start_session(data_root, world_id="world-1", now=clock[0])
        wake(restarted)
        wait_until(lambda: observation.enabled())
        with observation.scope(world_id="world-1", actor_id="actor-1"):
            observation.emit("result", item_id="new-session", boundary="committed")
        assert restarted.close()
        second_directory = data_root / "diagnostics/sns" / second["session_id"]
        events = [json.loads(line) for path in (second_directory / "memory-pipeline").glob("events-*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()]
        assert [event["item_id"] for event in events] == ["new-session"]
        assert recorded_files(directory) == before
    finally:
        restarted.close()


@pytest.mark.parametrize("ending", ["stop", "deadline"])
def test_first_discovery_of_ended_session_creates_no_recorder_evidence(data_root, ending, monkeypatch):
    now = datetime.now(UTC)
    manifest = start_session(data_root, world_id="world-1", minutes=1, tail_minutes=1, now=now)
    if ending == "stop":
        stop_session(data_root, manifest["session_id"], now=now)
    else:
        now += timedelta(minutes=2)
    before = recorded_files(data_root / "diagnostics")
    observer = SNSObserver(data_root, now=lambda: now, heartbeat_seconds=0.02)
    waits = []
    get = observer.queue.get

    def observed_wait(*args, **kwargs):
        waits.append(kwargs.get("timeout"))
        return get(*args, **kwargs)

    monkeypatch.setattr(observer.queue, "get", observed_wait)
    try:
        for _ in range(3):
            wake(observer)
        assert not observation.enabled() and observer._active is None
        assert len(waits) >= 2 and all(value >= 0.5 for value in waits)
        assert observer.close()
        assert recorded_files(data_root / "diagnostics") == before
        restarted = subprocess.run([sys.executable, "-c", """
from datetime import datetime
import json
from pathlib import Path
import sys
from app.core import work_observation
from app.runtime.diagnostics.sns_observation import SNSObserver
observer = SNSObserver(Path(sys.argv[1]), now=lambda: datetime.fromisoformat(sys.argv[2]))
try:
    for _ in range(3):
        observer.queue.put(None)
        observer.queue.join()
    print(json.dumps({'connected': work_observation.enabled(), 'attached': observer._active is not None}))
finally:
    assert observer.close()
""", str(data_root), now.isoformat()], cwd=Path(__file__).resolve().parents[2],
            capture_output=True, text=True, timeout=20)
        assert restarted.returncode == 0, restarted.stderr
        assert json.loads(restarted.stdout) == {"connected": False, "attached": False}
        assert recorded_files(data_root / "diagnostics") == before
        assert session_status(data_root, manifest["session_id"], now=now)["recorder_health"] == []
    finally:
        observer.close()


@pytest.mark.parametrize("stop_next", [False, True])
def test_pointer_replacement_drains_the_owned_session_before_rebinding(data_root, monkeypatch, stop_next):
    manifest = start_session(data_root, world_id="world-1")
    observer = SNSObserver(data_root)
    entered, release = Event(), Event()
    write = observer._write_event

    def blocked(session, event):
        if session == manifest["session_id"] and event["event_type"] == "node_started":
            entered.set()
            assert release.wait(5)
        return write(session, event)

    monkeypatch.setattr(observer, "_write_event", blocked)
    try:
        wait_until(lambda: observation.enabled())
        attempt = observer.begin(activity_id="old", agent_run_id="old-run", world_id="world-1",
            actor_id="actor-1", activity_started_at=datetime.now(UTC))
        assert attempt is not None
        attempt.emit("node_started", lane="feed", node="WritePost")
        assert entered.wait(5)
        attempt.emit("node_completed", lane="feed", node="WritePost")
        stop_session(data_root, manifest["session_id"])
        second = start_session(data_root, world_id="world-1")
        second_directory = data_root / "diagnostics/sns" / second["session_id"]
        if stop_next:
            stop_session(data_root, second["session_id"])
            untouched = recorded_files(second_directory)
        else:
            assert observer.begin(activity_id="new", agent_run_id="new-run", world_id="world-1",
                actor_id="actor-1", activity_started_at=datetime.now(UTC)) is not None
        release.set()
        observer.queue.join()
        wait_until(lambda: finalized(data_root, manifest["session_id"]))
        first_status = session_status(data_root, manifest["session_id"])
        health = first_status["recorder_health"][0]
        assert health["flush_complete"] and health["queued_count"] == 0
        assert health["admitted"] == health["written"] == 3
        if stop_next:
            assert not observation.enabled()
            assert recorded_files(second_directory) == untouched
        else:
            wait_until(lambda: observer.memory_pipeline.active["session_id"] == second["session_id"])
            assert observation.enabled()
            assert session_status(data_root, second["session_id"])["recorder_health"][0]["written"] == 1
    finally:
        release.set()
        assert observer.close()
    if stop_next:
        assert recorded_files(second_directory) == untouched
