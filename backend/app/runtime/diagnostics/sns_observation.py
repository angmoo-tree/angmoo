"""Opt-in, bounded diagnostics for real SNS V2 activity.

This module only observes existing decisions and effects. It never participates in
their transactions, retries, or checkpoint state.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
import sqlite3
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import Any
from uuid import uuid4


logger = logging.getLogger(__name__)
SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
EVENT_LIMIT = 8192
FILE_LIMIT = 4 * 1024 * 1024
SESSION_LIMIT = 64 * 1024 * 1024
_CODE = re.compile(r"[A-Za-z0-9_./:@-]{1,160}\Z")
_SESSION = re.compile(r"sns-[0-9a-f]{32}\Z")


def utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if _CODE.fullmatch(text) else None


def identifier(value: Any) -> str | None:
    """IDs are backend supplied; arbitrary prose is never copied as an ID."""
    return code(value)


def numbers(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def ids(values: Any, *, limit: int = 20) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return [item for value in list(values)[:limit] if (item := identifier(value))]


def digest(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return sha256(value.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                # Windows can temporarily deny replacement while a recorder
                # thread has the old manifest open. Keep the operation atomic.
                if os.name != "nt" or attempt == 4:
                    raise
                sleep(0.01 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def observation_root(data_root: Path) -> Path:
    return data_root.resolve() / "diagnostics" / "sns"


def session_path(data_root: Path, session_id: str) -> Path:
    if not _SESSION.fullmatch(session_id):
        raise ValueError("sns_session_id_invalid")
    return observation_root(data_root) / session_id


def read_session(data_root: Path, session_id: str) -> dict:
    value = json.loads((session_path(data_root, session_id) / "manifest.json").read_text(encoding="utf-8"))
    if value.get("session_id") != session_id or value.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError("sns_session_manifest_invalid")
    return value


def active_session(data_root: Path) -> dict | None:
    pointer = observation_root(data_root) / "active.json"
    if not pointer.is_file():
        return None
    try:
        selected = json.loads(pointer.read_text(encoding="utf-8"))
        return read_session(data_root, selected["session_id"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        logger.warning("sns_observation_active_manifest_unreadable")
        return None


def deadline(manifest: dict) -> datetime:
    return min(filter(None, (utc(manifest["tail_ends_at"]), utc(manifest.get("stopped_at")))))


def _safe_error(exc: BaseException) -> dict[str, Any]:
    details: dict[str, Any] = {"error_type": type(exc).__name__}
    message = code(str(exc))
    # Provider exception text may contain payloads. Keep only known backend codes.
    if message is not None and re.fullmatch(
        r"(?:activity|feed|routine|inbox|sns|social|world|state|relationship|memory|direct_llm)_[a-z0-9_]{1,100}",
        message,
    ):
        details["error_code"] = message
    for key in ("failure_class", "parse_error_type"):
        value = code(getattr(exc, key, None))
        if value is not None:
            details[key] = value
    retry_at = utc(getattr(exc, "retry_at", None))
    if retry_at is not None:
        details["retry_at"] = retry_at.isoformat()
    wait_seconds = numbers(getattr(exc, "wait_seconds", None))
    if wait_seconds is not None:
        details["wait_seconds"] = wait_seconds
    summary = getattr(exc, "validation_summary", None)
    if isinstance(summary, list):
        details["validation"] = [
            {"path": code(item.get("path")), "type": code(item.get("type"))}
            for item in summary[:4] if isinstance(item, dict)
        ]
    diagnostics = getattr(exc, "json_error_diagnostics", None)
    if isinstance(diagnostics, list):
        details["json_diagnostics"] = [
            {"attempt": numbers(item.get("attempt")), "response_length": numbers(item.get("response_length")),
             "finish_reason": code(item.get("finish_reason")), "shape_hint": code(item.get("shape_hint")),
             "parsed_present": item.get("parsed_present") is True}
            for item in diagnostics[:2] if isinstance(item, dict)
        ]
    return details


def _node_summary(name: str, state: dict, result: dict) -> dict:
    """Select structural facts only, never LangGraph State or generated text."""
    if name == "LoadCandidates":
        candidates = result.get("candidates") or []
        feed = (result.get("lane_data") or {}).get("_feed") or {}
        return {"candidate_count": len(candidates), "candidate_ids": ids([c.get("target_id") for c in candidates]),
                "candidate_revisions": [{"target_id": identifier(c.get("target_id")),
                    "source_revisions": {identifier(key): code(value) for key, value in
                        list((c.get("source_revisions") or {}).items())[:3]},
                    "relationship_hash": code((c.get("relationship") or {}).get("content_hash"))}
                    for c in candidates[:20]],
                "raw_candidate_count": numbers(feed.get("raw_candidate_count")),
                "query_latency_ms": numbers(feed.get("query_latency_ms"))}
    if name == "TargetSelector":
        selected = result.get("selections") or []
        return {"selection_count": len(selected), "selected_ids": ids([s.get("target_id") for s in selected]),
                "selector_bypassed": len(state.get("candidates") or []) == 1,
                "backend_limit": 3 if state.get("_diagnostic_lane") == "inbox" else 1}
    if name == "ResolveQuery":
        return {"queries": [{"target_id": identifier(q.get("target_id")), "origin": code(q.get("origin")),
                 "fallback_reason": code(q.get("fallback_reason")), "query_length": len(q.get("query") or ""),
                 "query_sha256": digest(q.get("query"))} for q in (result.get("queries") or [])[:3]]}
    if name == "RecallSelected":
        return {"targets": [{"target_id": identifier(target), "status": code(value.get("status")),
                 "reason": code(value.get("reason")), "retrieved_count": len(value.get("ranked_memory_ids") or []),
                 "retrieved_ids": ids(value.get("ranked_memory_ids")),
                 "packet_refs": ids([packet.get("ref") for packet in value.get("packets", [])]),
                 "omitted_packets": numbers(value.get("omitted_packets")),
                 "omitted_units": numbers(value.get("omitted_units")),
                 "duration_ms": numbers(value.get("duration_ms")),
                 "axes": [{"axis": code(axis.get("axis")), "status": code(axis.get("status")),
                           "candidate_count": numbers(axis.get("candidate_count")),
                           "reason_code": code(axis.get("reason_code")),
                           "duration_ms": numbers(axis.get("duration_ms"))}
                          for axis in (value.get("axes") or [])[:3] if isinstance(axis, dict)],
                 "embedding_usage": {key: numbers((value.get("embedding_usage") or {}).get(key))
                     for key in ("logical_calls", "physical_attempts", "input_tokens", "duration_ms")}}
                for target, value in list((result.get("memories") or {}).items())[:3] if isinstance(value, dict)]}
    if name == "BuildDecisionContext":
        context = result.get("decision_context") or {}
        memory = context.get("memories") or {}
        return {"memory_packet_refs": ids([p.get("ref") for v in memory.values() if isinstance(v, dict)
                 for p in v.get("packets", [])]), "source_ids": ids([r.get("post_id") for r in context.get("source_manifest", [])]),
                "state_version": numbers((context.get("current_state") or {}).get("version"))}
    if name == "ActionPlanner":
        decision = result.get("decision") or {}
        return {"actions": [{"target_id": identifier(d.get("target_id")), "action": code(d.get("action")),
                 "interaction_intent": code(d.get("interaction_intent")), "comment_purpose": code(d.get("comment_purpose"))}
                for d in (decision.get("decisions") or [])[:3]], "state_status": code(decision.get("state_status")),
                "state_update_proposed": decision.get("state_update") is not None,
                "routine_plan_present": decision.get("plan") is not None}
    if name == "ValidateDecision":
        return {"assignment_count": len(result.get("assignments") or []),
                "task_ids": ids([item.get("task_id") or item.get("beat_id") for item in result.get("assignments") or []])}
    if name == "Writer":
        return {"draft_count": len(result.get("drafts") or []), "soft_failure": bool(result.get("failure"))}
    if name == "Execute":
        return {"effects": [{"target_id": identifier(item.get("target_id")), "status": code(item.get("status")),
                 "execution_id": numbers(item.get("execution_id")),
                 "routine_outcome": code(item.get("routine_outcome"))}
                for item in (result.get("executions") or [])[:3] if isinstance(item, dict)]}
    if name == "Settle":
        settlement = result.get("settlement") or {}
        return {"state_outcome": code(settlement.get("state")), "decision_key": identifier(settlement.get("decision_key"))}
    if name == "PathResult":
        value = result.get("result") or {}
        failure = value.get("failure") or {}
        return {"status": code(value.get("status")), "public_action_count": numbers(value.get("public_action_count")),
                "selected_ids": ids(value.get("selected_ids")), "failure_stage": code(failure.get("stage")),
                "failure_type": code(failure.get("reason"))}
    return {}


@dataclass
class SNSAttempt:
    recorder: "SNSObserver"
    manifest: dict
    activity_id: str
    agent_run_id: str
    world_id: str
    actor_id: str
    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    last_error_event_id: str | None = None
    last_error_lane: str | None = None

    def emit(self, event_type: str, *, lane: str | None = None, node: str | None = None,
             classification: str | None = None, details: dict | None = None,
             exc: BaseException | None = None, caused_by_event_id: str | None = None) -> str | None:
        try:
            current = active_session(self.recorder.data_root)
            if (current is None or current["session_id"] != self.manifest["session_id"]
                or datetime.now(UTC) >= deadline(current)):
                return None
        except (OSError, ValueError, KeyError):
            return None
        event_id = uuid4().hex
        payload = {"schema_version": SCHEMA_VERSION, "session_id": self.manifest["session_id"],
                   "event_id": event_id, "process_instance_id": self.recorder.process_instance_id,
                   "occurred_at": datetime.now(UTC).isoformat(), "activity_id": self.activity_id,
                   "agent_run_id": self.agent_run_id, "attempt_id": self.attempt_id,
                   "world_id": self.world_id, "actor_id": self.actor_id, "engine": "personalized_graph_v2",
                   "event_type": event_type, "lane": lane, "node": node,
                   "classification": classification, "caused_by_event_id": caused_by_event_id,
                   "details": {**(details or {}), **(_safe_error(exc) if exc is not None else {})}}
        try:
            if not self.recorder.enqueue(self.manifest["session_id"], payload):
                return None
        except Exception:
            self.recorder.dropped += 1
            logger.warning("sns_observation_enqueue_failed")
            return None
        if exc is not None:
            self.last_error_event_id = event_id
            self.last_error_lane = lane
        return event_id

    def node(self, event_type: str, *, lane: str, node: str, state: dict | None = None,
             result: dict | None = None, phase: str | None = None, duration_ms: int | None = None,
             stage_attempt_id: str | None = None, exc: BaseException | None = None) -> None:
        facts = _node_summary(node, {**(state or {}), "_diagnostic_lane": lane}, result or {}) if result is not None else {}
        source_lane = node.removesuffix("ActivityGraph").lower() if node.endswith("ActivityGraph") else None
        caused_by = (self.last_error_event_id if exc is not None and lane == "parent"
                     and source_lane == self.last_error_lane else None)
        self.emit(event_type, lane=lane, node=node, classification="failed" if exc else None,
                  details={"phase": phase, "duration_ms": duration_ms,
                           "stage_attempt_id": identifier(stage_attempt_id), **facts},
                  exc=exc, caused_by_event_id=caused_by)

    def tracker_event(self, kind: str, payload: dict) -> None:
        if kind == "input_manifest":
            self.emit("input_manifest", lane=code(payload.get("lane")), node=code(payload.get("node")), details={
                "input_chars": numbers(payload.get("input_chars")),
                "schema_sha256": code(payload.get("schema_sha256")),
                "prompt_sha256": code(payload.get("prompt_sha256")),
                "selection_limit": numbers(payload.get("selection_limit")),
                "candidate_count": numbers(payload.get("candidate_count")),
                "selected_target_count": numbers(payload.get("selected_target_count")),
                "memory_packet_refs": ids(payload.get("memory_packet_refs")),
                "source_ids": ids(payload.get("source_ids")),
                "omissions": {key: numbers((payload.get("omissions") or {}).get(key))
                    for key in ("today_activity", "memory_packets")},
            })
            return
        if kind == "relationship_lookup":
            manifest = payload.get("manifest") or {}
            self.emit("relationship_lookup", lane=code(payload.get("lane")), details={
                "target_id": identifier(payload.get("counterpart_id")),
                "status": code(manifest.get("status")),
                "coverage": code(manifest.get("coverage")),
                "content_hash": code(manifest.get("content_hash")),
                "selected_count": numbers(manifest.get("selected_count")),
                "candidate_count": numbers(manifest.get("candidate_count")),
                "excluded_count": numbers(manifest.get("excluded_count")),
                "query_count": numbers(manifest.get("query_count")),
                "sources": ids(payload.get("sources"), limit=12),
                "relationship_versions": [
                    [identifier(row[0]), numbers(row[1])]
                    for row in (manifest.get("relationship_versions") or [])[:12]
                    if isinstance(row, (list, tuple)) and len(row) == 2],
            })
            return
        details = {"call_type": code(payload.get("call_type")), "call_order": numbers(payload.get("call_order_in_run")),
                   "provider_call_order": numbers(payload.get("provider_call_order_in_run")),
                   "json_attempt": numbers(payload.get("json_attempt")),
                   "provider": code(payload.get("provider")), "model": code(payload.get("model")),
                   "status": code(payload.get("status")), "duration_ms": numbers(payload.get("duration_ms")),
                   "finish_reason": code(payload.get("finish_reason")), "failure_class": code(payload.get("failure_class")),
                   "max_output_tokens": numbers(payload.get("max_output_tokens")),
                   "wait_seconds": numbers(payload.get("wait_seconds")), "wait_reason": code(payload.get("reason"))}
        usage = payload.get("usage")
        details["usage"] = {key: numbers(usage.get(key)) for key in ("prompt_token_count", "candidates_token_count",
                            "thoughts_token_count", "total_token_count")} if isinstance(usage, dict) else None
        diagnostic = payload.get("json_postprocess_error")
        if isinstance(diagnostic, dict):
            details["json_postprocess"] = {"parse_error_type": code(diagnostic.get("parse_error_type")),
                "response_length": numbers(diagnostic.get("response_length")),
                "finish_reason": code(diagnostic.get("finish_reason")), "shape_hint": code(diagnostic.get("shape_hint"))}
        self.emit("llm_" + kind, lane=code(payload.get("lane")), node=code(payload.get("node")), details=details,
                  classification="degraded" if kind == "json_postprocess_error" else None)


def _scheduler_snapshot(data_root: Path, manifest: dict) -> dict:
    """Small, read-only scheduler inventory for a once-per-minute heartbeat."""
    started = monotonic()
    try:
        root = data_root.resolve()
        path = (root / manifest["database_relative_path"]).resolve(strict=True)
        if not path.is_relative_to(root / "canonical") or path.name != "angmoo.sqlite3":
            return {"scheduler_snapshot": "database_scope_invalid"}
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.set_progress_handler(lambda: 1 if monotonic() - started > 2 else 0, 1000)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA busy_timeout=2000")
            actors = manifest["actor_ids"]
            placeholders = ",".join("?" for _ in actors)
            rows = db.execute(f"SELECT s.agent_id, s.status, s.next_tick_at, s.locked_by_run_id "
                f"FROM agent_slots s JOIN world_characters c ON c.character_id=s.assigned_character_id "
                f"WHERE c.world_id=? AND c.id IN ({placeholders})", (manifest["world_id"], *actors))
            slots = [{"agent_id": identifier(row["agent_id"]), "status": code(row["status"]),
                      "next_tick_at": row["next_tick_at"], "locked": row["locked_by_run_id"] is not None}
                     for row in rows]
            pending = db.execute(f"SELECT status, COUNT(*) AS count FROM activity_graph_runs WHERE world_id=? "
                f"AND world_character_id IN ({placeholders}) AND status IN ('running','waiting','interrupted') "
                "GROUP BY status", (manifest["world_id"], *actors))
            return {"scheduler_snapshot": "ready", "slots": slots,
                    "unfinished_runs": {row["status"]: row["count"] for row in pending},
                    "duration_ms": int((monotonic() - started) * 1000)}
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return {"scheduler_snapshot": "unavailable",
                "duration_ms": int((monotonic() - started) * 1000)}


_writer_lock = Lock()
_writers: dict[Path, "SNSObserver"] = {}


class SNSObserver:
    """One bounded, non-blocking process writer for successive V2 sessions."""

    def __init__(self, data_root: Path, *, heartbeat_seconds: float = 60.0,
                 now=None, monotonic_clock=None, scheduler_reader=None):
        self.data_root = data_root.resolve()
        self.process_instance_id = uuid4().hex
        self.heartbeat_seconds = heartbeat_seconds
        self.now = now or (lambda: datetime.now(UTC))
        self.monotonic_clock = monotonic_clock or monotonic
        self.scheduler_reader = scheduler_reader or _scheduler_snapshot
        self.queue: Queue[tuple[str, dict] | None] = Queue(maxsize=512)
        self.closed = Event()
        self._admission = Lock()
        self._cutoff_sessions: set[str] = set()
        self._finalized: set[str] = set()
        self._counts: dict[str, dict[str, int]] = {}
        self._sequence: dict[str, int] = {}
        self._total: dict[str, int] = {}
        self.dropped = 0
        self.last_saved_at: str | None = None
        self.last_loop_at: str | None = None
        self._last_heartbeat_wall = self.now()
        self.last_error_stage: str | None = None
        self.lifecycle_state = "starting"
        self._active: dict | None = None
        self._thread = Thread(target=self._loop, name="sns-observation", daemon=True)
        with _writer_lock:
            prior = _writers.get(self.data_root)
            if prior is not None and prior._thread.is_alive():
                raise RuntimeError("sns_observation_writer_still_running")
            _writers[self.data_root] = self
            self._thread.start()

    def _counter(self, session_id: str) -> dict[str, int]:
        return self._counts.setdefault(session_id,
            {"admitted": 0, "written": 0, "failed": 0, "dropped": 0})

    def _control(self, manifest: dict, event_type: str, *, reason: str | None = None,
                 details: dict | None = None) -> None:
        event = {"schema_version": SCHEMA_VERSION, "session_id": manifest["session_id"],
            "event_id": uuid4().hex, "process_instance_id": self.process_instance_id,
            "occurred_at": self.now().isoformat(), "event_type": event_type,
            "activity_id": None, "actor_id": None, "world_id": manifest["world_id"],
            "details": {"reason_code": reason, **(details or {})}}
        if not self._write_event(manifest["session_id"], event):
            self.last_error_stage = "control_write"
        self._safe_health(manifest["session_id"])

    def begin(self, *, activity_id: str, agent_run_id: str, world_id: str, actor_id: str,
              activity_started_at: datetime | str) -> SNSAttempt | None:
        manifest = active_session(self.data_root)
        if manifest is None:
            return None
        now = self.now()
        start, end = utc(manifest["started_at"]), utc(manifest["ends_at"])
        began = utc(activity_started_at)
        if (self.closed.is_set() or now >= deadline(manifest) or manifest["world_id"] != world_id
            or actor_id not in manifest["actor_ids"] or began is None
            or began >= end or (began < start and activity_id not in manifest.get("carry_in_ids", []))):
            return None
        attempt = SNSAttempt(self, manifest, activity_id, agent_run_id, world_id, actor_id)
        attempt.emit("activity_attempt_started", classification="running",
                     details={"carry_in": began < start, "resumed": activity_id != agent_run_id,
                              "activity_started_at": began.isoformat()})
        return attempt

    def enqueue(self, session_id: str, payload: dict) -> bool:
        with self._admission:
            if self.closed.is_set() or session_id in self._cutoff_sessions:
                return False
            try:
                current = active_session(self.data_root)
                occurred = utc(payload.get("occurred_at"))
            except (OSError, ValueError, TypeError):
                self.last_error_stage = "admission_manifest"
                return False
            if (current is None or current["session_id"] != session_id
                    or occurred is None or occurred >= deadline(current)):
                return False
            try:
                encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if len(encoded.encode("utf-8")) > EVENT_LIMIT:
                    payload = {**payload, "details": {"truncated": True}}
                self.queue.put_nowait((session_id, payload))
                self._counter(session_id)["admitted"] += 1
                return True
            except (Full, TypeError, ValueError):
                self.dropped += 1
                self._counter(session_id)["dropped"] += 1
                self.last_error_stage = "enqueue"
                if self.dropped == 1:
                    logger.warning("sns_observation_queue_drop")
                return False

    def _health(self, session_id: str) -> None:
        directory = session_path(self.data_root, session_id)
        count = self._counter(session_id)
        _atomic_json(directory / f"recorder-health-{self.process_instance_id}.json", {
            "schema_version": SCHEMA_VERSION, "session_id": session_id,
            "process_instance_id": self.process_instance_id,
            "heartbeat_at": self.now().isoformat(), "last_loop_at": self.last_loop_at,
            "last_saved_at": self.last_saved_at, "last_error_stage": self.last_error_stage,
            "lifecycle_state": self.lifecycle_state, "dropped_count": count["dropped"],
            "queued_count": self.queue.qsize(), **count,
            "flush_complete": session_id in self._finalized and
                count["admitted"] == count["written"] + count["failed"]})

    def _safe_health(self, session_id: str) -> None:
        try:
            self._health(session_id)
        except (OSError, ValueError, TypeError):
            self.last_error_stage = "health_write"
            logger.warning("sns_observation_health_write_failed")

    def _write_event(self, session_id: str, event: dict) -> bool:
        try:
            directory = session_path(self.data_root, session_id)
            directory.mkdir(parents=True, exist_ok=True)
            index = self._sequence.get(session_id, 1)
            path = directory / f"events-{self.process_instance_id}-{index:04d}.jsonl"
            encoded = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            if path.exists() and path.stat().st_size + len(encoded) > FILE_LIMIT:
                index += 1
                self._sequence[session_id] = index
                path = directory / f"events-{self.process_instance_id}-{index:04d}.jsonl"
            used = self._total.get(session_id)
            if used is None:
                used = sum(p.stat().st_size for p in directory.glob("events-*.jsonl"))
            if used + len(encoded) > SESSION_LIMIT:
                self.last_error_stage = "session_limit"
                return False
            with path.open("ab") as output:
                output.write(encoded)
            self._total[session_id] = used + len(encoded)
            self.last_saved_at = self.now().isoformat()
            return True
        except (OSError, ValueError, TypeError):
            self.last_error_stage = "event_write"
            logger.warning("sns_observation_write_failed")
            return False

    def _attach(self, manifest: dict) -> None:
        previous = self._active
        if previous and previous["session_id"] != manifest["session_id"]:
            self._control(previous, "recorder_closed", reason="session_rebound")
        self._active = manifest
        # Health files are per session. A recovered write failure from the
        # previous session must not appear as this session's own failure.
        self.last_error_stage = None
        self.last_saved_at = None
        self._last_heartbeat_wall = self.now()
        self.lifecycle_state = "attached"
        self._control(manifest, "recorder_attached",
            reason="session_rebound" if previous else "session_discovered")

    def _heartbeat(self, manifest: dict, *, elapsed_seconds: float) -> None:
        session_id = manifest["session_id"]
        occurred = self.now()
        wall_elapsed = (occurred - self._last_heartbeat_wall).total_seconds()
        self._last_heartbeat_wall = occurred
        details = {"queued_count": self.queue.qsize(),
            "dropped_count": self._counter(session_id)["dropped"],
            "monotonic_elapsed_seconds": round(elapsed_seconds, 3),
            "wall_elapsed_seconds": round(wall_elapsed, 3),
            "clock_shift_seconds": round(wall_elapsed - elapsed_seconds, 3)
                if abs(wall_elapsed - elapsed_seconds) > 150 else None,
            "last_saved_at": self.last_saved_at}
        self._write_event(session_id, {"schema_version": SCHEMA_VERSION, "session_id": session_id,
            "event_id": uuid4().hex, "process_instance_id": self.process_instance_id,
            "occurred_at": occurred.isoformat(), "event_type": "heartbeat",
            "activity_id": None, "actor_id": None, "world_id": manifest["world_id"],
            "details": details})
        # A slow or unavailable scheduler cannot suppress the preceding heartbeat.
        try:
            snapshot = self.scheduler_reader(self.data_root, manifest)
        except Exception:
            snapshot = {"scheduler_snapshot": "unavailable"}
            self.last_error_stage = "scheduler_sample"
            logger.warning("sns_observation_scheduler_sample_failed")
        self._control(manifest, "scheduler_sample", details={
            "heartbeat_at": occurred.isoformat(),
            "scheduler_snapshot": code(snapshot.get("scheduler_snapshot")),
            "duration_ms": numbers(snapshot.get("duration_ms")),
            "slot_count": len(snapshot.get("slots") or []),
            "unfinished_runs": snapshot.get("unfinished_runs") or {}})
        self._safe_health(session_id)

    def _finalize(self, manifest: dict) -> None:
        session_id = manifest["session_id"]
        if session_id in self._finalized or not self.queue.empty():
            return
        count = self._counter(session_id)
        flush = count["admitted"] == count["written"] + count["failed"]
        self.lifecycle_state = "finalized"
        self._control(manifest, "session_finalized", details={
            "scheduled_cutoff_at": deadline(manifest).isoformat(),
            "finalized_at": self.now().isoformat(), "flush_complete": flush,
            "pending": count["admitted"] - count["written"] - count["failed"],
            **count})
        self._finalized.add(session_id)
        self._safe_health(session_id)

    def _loop(self) -> None:
        next_heartbeat = self.monotonic_clock() + self.heartbeat_seconds
        last_heartbeat = self.monotonic_clock()
        try:
            while True:
                self.last_loop_at = self.now().isoformat()
                manifest = active_session(self.data_root)
                if manifest is not None and (self._active is None
                    or self._active["session_id"] != manifest["session_id"]):
                    self._attach(manifest)
                if manifest is not None and self.now() >= deadline(manifest):
                    with self._admission:
                        self._cutoff_sessions.add(manifest["session_id"])
                tick = self.monotonic_clock()
                if (manifest is not None and manifest["session_id"] not in self._cutoff_sessions
                    and tick >= next_heartbeat):
                    self._heartbeat(manifest, elapsed_seconds=tick - last_heartbeat)
                    last_heartbeat = tick
                    next_heartbeat = tick + self.heartbeat_seconds
                if manifest is not None and manifest["session_id"] in self._cutoff_sessions:
                    self._finalize(manifest)
                if self.closed.is_set() and self.queue.empty():
                    break
                try:
                    item = self.queue.get(timeout=min(1.0,
                        max(0.01, next_heartbeat - self.monotonic_clock())))
                except Empty:
                    continue
                try:
                    if item is not None:
                        session_id, event = item
                        counter = self._counter(session_id)
                        if self._write_event(session_id, event):
                            counter["written"] += 1
                        else:
                            counter["failed"] += 1
                            counter["dropped"] += 1
                            self.dropped += 1
                        self._safe_health(session_id)
                finally:
                    self.queue.task_done()
        except Exception:
            self.lifecycle_state = "fatal"
            self.last_error_stage = "writer_loop"
            logger.exception("sns_observation_writer_fatal")
            if self._active is not None:
                self._safe_health(self._active["session_id"])
        finally:
            if self._active is not None:
                self.lifecycle_state = "closed" if self.lifecycle_state != "fatal" else "fatal"
                self._control(self._active, "recorder_closed",
                    reason="runtime_close" if self.closed.is_set() else "writer_fatal")
            with _writer_lock:
                if _writers.get(self.data_root) is self:
                    del _writers[self.data_root]

    def close(self) -> bool:
        until = self.monotonic_clock() + 10.0
        if not self.closed.is_set():
            with self._admission:
                self.closed.set()
            if self._active is not None:
                self.lifecycle_state = "closing"
                self._control(self._active, "recorder_closing", reason="runtime_close")
            try:
                self.queue.put(None, timeout=max(0, min(0.5, until - self.monotonic_clock())))
            except Full:
                self.last_error_stage = "close_queue_full"
        self._thread.join(timeout=max(0, until - self.monotonic_clock()))
        if self._thread.is_alive():
            self.lifecycle_state = "close_timeout"
            self.last_error_stage = "close_timeout"
            if self._active is not None:
                self._safe_health(self._active["session_id"])
            return False
        return True
