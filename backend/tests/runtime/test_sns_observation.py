"""The recorder observes, survives restarts and exports only safe evidence."""

import asyncio
import csv
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from queue import Full
import sqlite3
import time

import pytest

from app.runtime.autonomous_activity.contracts import identity_key
from app.runtime.autonomous_activity.graph import build_lane
from app.runtime.diagnostics.sns_observation import SNSObserver, active_session
from app.runtime.diagnostics.sns_observation_report import (
    export_session, session_status, start_session, stop_session,
)
from app.integrations.direct_llm import DirectLlmJsonError
from tests.runtime.test_autonomous_activity_graph import lane_ports


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    selected = root / "canonical" / "generations" / "test" / "angmoo.sqlite3"
    selected.parent.mkdir(parents=True)
    (root / "canonical" / "current-generation.json").write_text(
        json.dumps({"schema_version": 1, "relative_path": "generations/test"}), encoding="utf-8")
    with sqlite3.connect(selected) as db:
        db.executescript("""
            CREATE TABLE worlds (id TEXT, name TEXT, status TEXT, timezone TEXT);
            CREATE TABLE world_characters (id TEXT, world_id TEXT, character_id TEXT,
                status TEXT, control_mode TEXT, autonomous_enabled INTEGER);
            CREATE TABLE activity_engine_policies (scope_key TEXT, engine TEXT);
            CREATE TABLE agent_slots (agent_id TEXT, status TEXT, next_tick_at TEXT,
                heartbeat_interval_seconds INTEGER, locked_by_run_id TEXT, assigned_character_id TEXT);
            CREATE TABLE agent_runs (id TEXT, agent_id TEXT, status TEXT,
                created_at TEXT, completed_at TEXT);
            CREATE TABLE activity_graph_runs (activity_id TEXT, world_id TEXT,
                world_character_id TEXT, engine TEXT, status TEXT, stage TEXT,
                result TEXT, started_at TEXT, finished_at TEXT);
            CREATE TABLE agent_public_action_executions (id INTEGER, run_id TEXT,
                scope TEXT, action_type TEXT, target_post_id TEXT, status TEXT,
                failure_class TEXT, created_at TEXT, completed_at TEXT);
            CREATE TABLE world_character_state_receipts (decision_key TEXT,
                activity_id TEXT, outcome TEXT, expected_version INTEGER,
                resulting_version INTEGER, judged_at TEXT);
            CREATE TABLE relationship_experience_receipts (id TEXT, world_id TEXT,
                actor_world_character_id TEXT, target_world_character_id TEXT, source_key TEXT);
            CREATE TABLE relationship_metric_applications (id TEXT, experience_id TEXT,
                decision_key TEXT, status TEXT, state_version INTEGER, created_at TEXT, applied_at TEXT);
            INSERT INTO worlds VALUES ('world-1','Example World','published','UTC');
            INSERT INTO world_characters VALUES ('actor-1','world-1','character-1',
                'active','autonomous',1);
            INSERT INTO agent_slots VALUES ('agent-1','idle',NULL,1800,NULL,'character-1');
        """)
    return root


def _insert_run(root: Path, *, activity_id: str, started_at: datetime, status: str = "waiting"):
    selected = root / "canonical" / "generations" / "test" / "angmoo.sqlite3"
    with sqlite3.connect(selected) as db:
        db.execute("INSERT INTO activity_graph_runs VALUES (?,?,?,?,?,?,?,?,?)",
            (activity_id, "world-1", "actor-1", "personalized_graph_v2", status,
             "ActionPlanner", json.dumps({"paths": {}}), started_at.isoformat(), None))


def test_session_captures_validation_failure_without_payload_and_exports_read_only(data_root, tmp_path):
    now = datetime.now(UTC)
    _insert_run(data_root, activity_id="activity-1", started_at=now - timedelta(minutes=1))
    manifest = start_session(data_root, world_id="world-1", now=now)
    assert "activity-1" in manifest["carry_in_ids"]
    observer = SNSObserver(data_root, heartbeat_seconds=0.05)
    try:
        attempt = observer.begin(activity_id="activity-1", agent_run_id="lease-2",
            world_id="world-1", actor_id="actor-1", activity_started_at=now - timedelta(minutes=1))
        assert attempt is not None
        attempt.tracker_event("call", {"call_type": "generate_content", "node": "InboxActionPlanner",
            "lane": "inbox_action_planner", "status": "ok", "call_order_in_run": 1,
            "credential_id": "private-credential", "provider_error": {"body": "private-body"}})
        attempt.tracker_event("input_manifest", {"node": "InboxActionPlanner", "lane": "inbox_action_planner",
            "input_chars": 1234, "memory_packet_refs": ["memory-1"], "omissions": {"today_activity": 0}})
        error = ValueError("free text with private-body")
        error.validation_summary = [{"path": "decisions.0.action", "type": "literal_error",
                                     "message": "private-body"}]
        error.json_error_diagnostics = [{"response_length": 100, "finish_reason": "STOP",
                                         "shape_hint": "schema_validation", "preview_head": "private-body"}]
        attempt.node("node_failed", lane="inbox", node="ActionPlanner", phase="callback", exc=error)
        attempt.emit("lane_error", lane="inbox", exc=error, caused_by_event_id=attempt.last_error_event_id)
        observer.queue.join()
    finally:
        observer.close()
    source = "\n".join(path.read_text(encoding="utf-8") for path in
                       (data_root / "diagnostics" / "sns" / manifest["session_id"]).glob("events-*.jsonl"))
    assert "private-body" not in source
    assert "private-credential" not in source
    assert "memory-1" in source
    assert "decisions.0.action" in source
    destination = tmp_path / "report"
    coverage = export_session(data_root, manifest["session_id"], destination=destination)
    assert coverage["run_count"] == 1
    assert coverage["error_count"] == 1  # Lane wrapper points to the node failure.
    assert not coverage["complete_recording"]  # Two hours have not elapsed.
    assert "private-body" not in (destination / "errors.jsonl").read_text(encoding="utf-8")
    assert (destination / "calls.jsonl").read_text(encoding="utf-8").count("llm_call") == 1
    with (destination / "errors.csv").open(encoding="utf-8", newline="") as source:
        assert list(csv.DictReader(source))[0]["validation_code"] == "unknown"
    assert (destination / "report.md").is_file()


def test_export_separates_recovered_planner_output_from_final_failure(data_root, tmp_path):
    now = datetime.now(UTC)
    _insert_run(data_root, activity_id="recovered-activity", started_at=now)
    _insert_run(data_root, activity_id="failed-activity", started_at=now)
    manifest = start_session(data_root, world_id="world-1", now=now)
    observer = SNSObserver(data_root, heartbeat_seconds=0.05)
    try:
        recovered = observer.begin(activity_id="recovered-activity", agent_run_id="lease-1",
            world_id="world-1", actor_id="actor-1", activity_started_at=now)
        failed = observer.begin(activity_id="failed-activity", agent_run_id="lease-2",
            world_id="world-1", actor_id="actor-1", activity_started_at=now)
        assert recovered and failed
        payload = {"node": "InboxActionPlanner", "lane": "inbox_action_planner",
                   "json_postprocess_error": {
                       "attempt": 1, "parse_error_type": "StructuredOutputValidationError",
                       "finish_reason": "STOP", "shape_hint": "schema_validation",
                       "validation_code": "action_brief_missing",
                       "field_path": "decisions.0.brief",
                       "preview_head": "SECRET_PRIVATE",
                       "error_message": "SECRET_PRIVATE"}}
        recovered.tracker_event("json_postprocess_error", payload)
        recovered.tracker_event("json_attempt", {
            "node": "InboxActionPlanner", "lane": "inbox_action_planner",
            "json_attempt": 1, "status": "retry_scheduled",
            "retry_reason": "action_brief_missing", "max_output_tokens": 4096})
        recovered.tracker_event("json_attempt_input", {
            "node": "InboxActionPlanner", "lane": "inbox_action_planner",
            "json_attempt": 2, "input_sha256": "a" * 64,
            "retry_reason": "action_brief_missing", "max_output_tokens": 4096})
        recovered.tracker_event("json_attempt", {
            "node": "InboxActionPlanner", "lane": "inbox_action_planner",
            "json_attempt": 2, "status": "valid"})
        failed.tracker_event("json_postprocess_error", payload)
        error = DirectLlmJsonError(
            "direct LLM JSON parse failed", failure_class="json_parse_failed",
            parse_error_type="StructuredOutputValidationError", attempt_count=1,
            validation_code="action_brief_missing", field_path="decisions.0.brief",
            json_error_diagnostics=[payload["json_postprocess_error"]])
        failed.node("node_failed", lane="inbox", node="ActionPlanner", exc=error)
        observer.queue.join()
    finally:
        observer.close()
    output = tmp_path / "planner-export"
    coverage = export_session(data_root, manifest["session_id"], destination=output)
    assert coverage["planner_output_failures"] == 2
    assert coverage["planner_retries_scheduled"] == 1
    assert coverage["planner_recovered_activities"] == 1
    assert coverage["planner_final_failures"] == 1
    assert coverage["error_count"] == 1
    csv_text = (output / "errors.csv").read_text(encoding="utf-8")
    assert "action_brief_missing" in csv_text and "decisions.0.brief" in csv_text
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "recovered activities: 1; final path failures: 1" in report
    calls = (output / "calls.jsonl").read_text(encoding="utf-8")
    assert "a" * 64 in calls
    for filename in ("calls.jsonl", "errors.jsonl", "report.md"):
        assert "SECRET_PRIVATE" not in (output / filename).read_text(encoding="utf-8")


def test_scope_stop_and_recorder_failure_do_not_change_activity(data_root):
    manifest = start_session(data_root, world_id="world-1")
    observer = SNSObserver(data_root)
    try:
        assert observer.begin(activity_id="x", agent_run_id="x", world_id="other",
            actor_id="actor-1", activity_started_at=datetime.now(UTC)) is None
        attempt = observer.begin(activity_id="new-1", agent_run_id="new-1",
            world_id="world-1", actor_id="actor-1", activity_started_at=datetime.now(UTC))
        assert attempt is not None
        original = observer.enqueue
        observer.enqueue = lambda *_: (_ for _ in ()).throw(OSError("injected write failure"))
        assert attempt.emit("node_started", lane="feed", node="LoadCandidates") is None
        observer.enqueue = original
        stop_session(data_root, manifest["session_id"])
        assert attempt.emit("node_completed", lane="feed", node="LoadCandidates") is None
        assert session_status(data_root, manifest["session_id"])["state"] == "stopped"
        assert active_session(data_root)["session_id"] == manifest["session_id"]
    finally:
        observer.close()


def test_guard_failure_has_node_phase_and_keeps_original_exception():
    async def scenario():
        calls, events = [], []
        ports = lane_ports("inbox", calls)

        async def guard(state):
            if state["stage"] == "TargetSelector":
                raise ValueError("source_changed")

        ports = replace(ports, guard=guard,
                        observe=lambda event, node, **details: events.append((event, node, details)))
        with pytest.raises(ValueError, match="source_changed"):
            await build_lane("inbox", ports).ainvoke({"identity": {"world_id": "world"}})
        assert any(event == "node_failed" and node == "TargetSelector"
                   and details.get("phase") == "guard" for event, node, details in events)

    asyncio.run(scenario())

def test_export_joins_confirmed_actions_state_and_relationship_receipts(data_root, tmp_path):
    now = datetime.now(UTC)
    manifest = start_session(data_root, world_id="world-1", now=now)
    _insert_run(data_root, activity_id="activity-2", started_at=now + timedelta(seconds=1), status="completed")
    selected = data_root / "canonical" / "generations" / "test" / "angmoo.sqlite3"
    with sqlite3.connect(selected) as db:
        db.execute("INSERT INTO agent_public_action_executions VALUES (?,?,?,?,?,?,?,?,?)",
                   (42, "activity-2", "inbox", "reply", "post-1", "succeeded", None,
                    now.isoformat(), now.isoformat()))
        db.execute("INSERT INTO world_character_state_receipts VALUES (?,?,?,?,?,?)",
                   ("state-key", "activity-2", "changed", 1, 2, now.isoformat()))
        db.execute("INSERT INTO relationship_experience_receipts VALUES (?,?,?,?,?)",
                   ("receipt-1", "world-1", "actor-1", "other-actor", "post-1"))
        db.execute("INSERT INTO relationship_metric_applications VALUES (?,?,?,?,?,?,?)",
                   ("metric-1", "receipt-1", identity_key("activity-2", "inbox", "decision"),
                    "applied", 3, now.isoformat(), now.isoformat()))
    output = tmp_path / "export"
    coverage = export_session(data_root, manifest["session_id"], destination=output)
    assert coverage["effect_statuses"]["public_action"] == {"succeeded": 1}
    assert coverage["effect_statuses"]["state_receipt"] == {"changed": 1}
    assert coverage["effect_statuses"]["relationship_metric"] == {"applied": 1}
    assert "post-1" in (output / "effects.jsonl").read_text(encoding="utf-8")


def test_heartbeat_records_idle_scheduler_without_private_activity(data_root):
    manifest = start_session(data_root, world_id="world-1")
    observer = SNSObserver(data_root, heartbeat_seconds=0.05)
    try:
        directory = data_root / "diagnostics" / "sns" / manifest["session_id"]
        until = time.monotonic() + 2
        while time.monotonic() < until:
            observed = [json.loads(line) for path in directory.glob("events-*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]
            if any(item["event_type"] == "scheduler_sample" for item in observed):
                break
            time.sleep(0.03)
        observer.queue.join()
    finally:
        observer.close()
    events = [json.loads(line) for path in directory.glob("events-*.jsonl")
              for line in path.read_text(encoding="utf-8").splitlines()]
    assert any(item["event_type"] == "heartbeat" for item in events)
    assert any(item["event_type"] == "scheduler_sample" and
               item["details"]["scheduler_snapshot"] == "ready" for item in events)


def test_restart_keeps_session_and_tail_only_accepts_existing_activity(data_root, tmp_path):
    started = datetime.now(UTC) - timedelta(seconds=75)
    manifest = start_session(data_root, world_id="world-1", minutes=1,
                             tail_minutes=1, now=started)
    first = SNSObserver(data_root, heartbeat_seconds=0.05)
    try:
        attempt = first.begin(activity_id="within-window", agent_run_id="lease-1",
                              world_id="world-1", actor_id="actor-1",
                              activity_started_at=started + timedelta(seconds=30))
        assert attempt is not None
        first.queue.join()
        process_id = first.process_instance_id
    finally:
        first.close()
    second = SNSObserver(data_root, heartbeat_seconds=0.05)
    try:
        resumed = second.begin(activity_id="within-window", agent_run_id="lease-2",
                               world_id="world-1", actor_id="actor-1",
                               activity_started_at=started + timedelta(seconds=30))
        assert resumed is not None and resumed.attempt_id != attempt.attempt_id
        assert second.process_instance_id != process_id
        assert second.begin(activity_id="too-late", agent_run_id="lease-3",
                            world_id="world-1", actor_id="actor-1",
                            activity_started_at=started + timedelta(seconds=65)) is None
        second.queue.join()
    finally:
        second.close()
    directory = data_root / "diagnostics" / "sns" / manifest["session_id"]
    events = [json.loads(line) for path in directory.glob("events-*.jsonl")
              for line in path.read_text(encoding="utf-8").splitlines()]
    starts = [row for row in events if row["event_type"] == "activity_attempt_started"]
    assert len(starts) == 2
    assert {row["activity_id"] for row in starts} == {"within-window"}
    assert len({row["process_instance_id"] for row in starts}) == 2


def test_parent_lane_failure_is_linked_to_one_root_error(data_root, tmp_path):
    manifest = start_session(data_root, world_id="world-1")
    observer = SNSObserver(data_root)
    try:
        attempt = observer.begin(activity_id="failed-activity", agent_run_id="failed-lease",
                                 world_id="world-1", actor_id="actor-1",
                                 activity_started_at=datetime.now(UTC))
        error = ValueError("activity_source_changed")
        attempt.node("node_failed", lane="inbox", node="ActionPlanner", exc=error)
        attempt.node("node_failed", lane="parent", node="InboxActivityGraph", exc=error)
        attempt.emit("lane_error", lane="inbox", exc=error,
                     caused_by_event_id=attempt.last_error_event_id)
        observer.queue.join()
    finally:
        observer.close()
    output = tmp_path / "dedup"
    coverage = export_session(data_root, manifest["session_id"], destination=output)
    assert coverage["error_count"] == 1
    errors = [json.loads(line) for line in (output / "errors.jsonl").read_text().splitlines()]
    assert errors[0]["node"] == "ActionPlanner"


def test_accelerated_idle_120_minute_window_and_tail_finalize_with_heartbeat(data_root, tmp_path):
    started = datetime.now(UTC)
    origin = time.monotonic()
    def virtual_now():
        return started + timedelta(seconds=(time.monotonic() - origin) * 1500)
    manifest = start_session(data_root, world_id="world-1", minutes=120,
        tail_minutes=10, now=started)
    observer = SNSObserver(data_root, heartbeat_seconds=0.01, now=virtual_now,
        scheduler_reader=lambda *_: {"scheduler_snapshot": "ready", "duration_ms": 0})
    directory = data_root / "diagnostics" / "sns" / manifest["session_id"]
    try:
        until = time.monotonic() + 12
        while time.monotonic() < until:
            events = [json.loads(line) for path in directory.glob("events-*.jsonl")
                for line in path.read_text(encoding="utf-8").splitlines()]
            if any(event["event_type"] == "session_finalized" for event in events):
                break
            time.sleep(0.02)
        else:
            pytest.fail("virtual session did not finalize")
        observer.queue.join()
    finally:
        assert observer.close()
    output = tmp_path / "virtual-export"
    coverage = export_session(data_root, manifest["session_id"], destination=output,
        now=virtual_now())
    # The wall clock is accelerated 1500x, so a brief Windows scheduling pause
    # can represent a real observation gap. The report must not call it complete.
    assert coverage["complete_recording"] is (not coverage["heartbeat_gap_seconds"])
    assert coverage["observed_any_activity"] is False
    assert coverage["flush_complete"] is True
    assert all(gap > 150 for gap in coverage["heartbeat_gap_seconds"])
    assert (output / "control.jsonl").read_text(encoding="utf-8").count('"event_type":"heartbeat"') > 100


def test_scheduler_failure_does_not_suppress_heartbeat(data_root):
    manifest = start_session(data_root, world_id="world-1")
    def unavailable(*_):
        raise sqlite3.OperationalError("synthetic scheduler failure")
    observer = SNSObserver(data_root, heartbeat_seconds=0.02, scheduler_reader=unavailable)
    directory = data_root / "diagnostics" / "sns" / manifest["session_id"]
    try:
        time.sleep(0.12)
        observer.queue.join()
    finally:
        observer.close()
    events = [json.loads(line) for path in directory.glob("events-*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()]
    assert any(item["event_type"] == "heartbeat" for item in events)
    assert any(item["event_type"] == "scheduler_sample" and
        item["details"]["scheduler_snapshot"] == "unavailable" for item in events)


def test_tail_stop_and_v1_reader_do_not_claim_complete_recording(data_root, tmp_path):
    started = datetime.now(UTC) - timedelta(seconds=70)
    manifest = start_session(data_root, world_id="world-1", minutes=1,
        tail_minutes=1, now=started)
    stop_session(data_root, manifest["session_id"], now=started + timedelta(seconds=90))
    status = session_status(data_root, manifest["session_id"],
        now=started + timedelta(seconds=130))
    assert status["window_elapsed"] and status["tail_elapsed"]
    assert status["stopped_early"]
    assert status["admission_cutoff_at"] == (started + timedelta(seconds=90)).isoformat()
    directory = data_root / "diagnostics" / "sns" / manifest["session_id"]
    old = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    old["schema_version"] = 1
    old["event_schema_version"] = 1
    (directory / "manifest.json").write_text(json.dumps(old), encoding="utf-8")
    legacy_event = {"schema_version": 1, "session_id": manifest["session_id"],
        "event_id": "old-heartbeat", "occurred_at": (started + timedelta(seconds=30)).isoformat(),
        "event_type": "heartbeat", "actor_id": None, "activity_id": None, "details": {}}
    (directory / "events-old-0001.jsonl").write_text(json.dumps(legacy_event) + "\n", encoding="utf-8")
    coverage = export_session(data_root, manifest["session_id"],
        destination=tmp_path / "legacy-export", now=started + timedelta(seconds=130))
    assert coverage["control_event_count"] == 1
    assert coverage["complete_recording"] is False
    assert coverage["flush_complete"] is None
    assert coverage["stopped_early"] is True
    assert coverage["planner_output_failures"] == 0


def test_single_writer_per_data_root_and_rebind_after_close(data_root):
    start_session(data_root, world_id="world-1")
    first = SNSObserver(data_root, heartbeat_seconds=0.05)
    try:
        with pytest.raises(RuntimeError, match="sns_observation_writer_still_running"):
            SNSObserver(data_root)
    finally:
        assert first.close()
    second = SNSObserver(data_root, heartbeat_seconds=0.05)
    try:
        assert second.process_instance_id != first.process_instance_id
    finally:
        assert second.close()


def test_full_queue_is_counted_and_subsequent_event_can_be_recorded(data_root, monkeypatch):
    manifest = start_session(data_root, world_id="world-1")
    observer = SNSObserver(data_root)
    try:
        attempt = observer.begin(activity_id="activity-queue", agent_run_id="lease-queue",
            world_id="world-1", actor_id="actor-1", activity_started_at=datetime.now(UTC))
        assert attempt is not None
        original = observer.queue.put_nowait
        monkeypatch.setattr(observer.queue, "put_nowait", lambda *_: (_ for _ in ()).throw(Full()))
        assert attempt.emit("node_started", lane="inbox", node="TargetSelector") is None
        monkeypatch.setattr(observer.queue, "put_nowait", original)
        assert attempt.emit("node_completed", lane="inbox", node="TargetSelector") is not None
        observer.queue.join()
        assert observer.dropped >= 1
        assert observer._counter(manifest["session_id"])["dropped"] >= 1
    finally:
        assert observer.close()


def test_event_write_failure_is_counted_without_failing_activity(data_root, monkeypatch):
    manifest = start_session(data_root, world_id="world-1")
    observer = SNSObserver(data_root)
    try:
        attempt = observer.begin(activity_id="activity-file", agent_run_id="lease-file",
            world_id="world-1", actor_id="actor-1", activity_started_at=datetime.now(UTC))
        assert attempt is not None
        observer.queue.join()
        original = observer._write_event

        def fail_one(session_id, event):
            if event.get("event_type") == "node_started":
                return False
            return original(session_id, event)

        monkeypatch.setattr(observer, "_write_event", fail_one)
        assert attempt.emit("node_started", lane="feed", node="LoadCandidates") is not None
        observer.queue.join()
        assert observer._counter(manifest["session_id"])["failed"] == 1
        assert observer._counter(manifest["session_id"])["dropped"] == 1
        assert attempt.emit("node_completed", lane="feed", node="LoadCandidates") is not None
        observer.queue.join()
        assert observer._counter(manifest["session_id"])["written"] >= 2
    finally:
        assert observer.close()


def test_new_session_health_does_not_inherit_prior_session_error(data_root):
    first = start_session(data_root, world_id="world-1")
    observer = SNSObserver(data_root, heartbeat_seconds=0.03)
    try:
        until = time.monotonic() + 2
        while time.monotonic() < until and observer._active is None:
            time.sleep(0.01)
        assert observer._active is not None
        observer.last_error_stage = "event_write"
        stop_session(data_root, first["session_id"])
        second = start_session(data_root, world_id="world-1")
        until = time.monotonic() + 2
        while time.monotonic() < until and (
            observer._active is None or observer._active["session_id"] != second["session_id"]
        ):
            time.sleep(0.01)
        assert observer._active["session_id"] == second["session_id"]
        health = []
        while time.monotonic() < until and not health:
            health = session_status(data_root, second["session_id"])["recorder_health"]
            if not health:
                time.sleep(0.01)
        assert len(health) == 1
        assert health[0]["last_error_stage"] is None
    finally:
        assert observer.close()
