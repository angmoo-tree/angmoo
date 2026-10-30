"""Background memory evidence on the existing opt-in recorder lifetime.

Business threads only consult cached scope and enqueue bounded safe facts.
The SNS recorder thread owns all files, watermarks and manifest refreshes.
"""
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
from pathlib import Path
from queue import Empty, Full, Queue
import re
from threading import Lock
from time import monotonic
from app.core import work_observation
from app.runtime.diagnostics.observation_storage import atomic_json, session_path

CAPABILITY = "memory-pipeline-observation.v1"
EVENT_LIMIT = 16 * 1024
SESSION_LIMIT = 64 * 1024 * 1024
_CODE = re.compile(r"[A-Za-z0-9_./:@+\-]{1,240}\Z")
TEXT = frozenset({"world_id", "actor_id", "run_id", "receipt_id", "item_id", "content_hash", "profile", "generation",
    "batch_id", "logical_id", "attempt_id", "span_id", "parent_span_id", "queue_id", "task_id", "operation", "writer",
    "database_id", "purpose", "reason", "outcome", "boundary", "transport", "endpoint", "event", "occurred_at",
    "credential_alias", "result", "stage", "sqlite_name", "sqlstate"})
NUMBERS = frozenset({"monotonic_ns", "version", "receipt_sequence", "cursor", "cutoff", "byte_size", "input_count",
    "response_count", "dimension", "status_code", "credential_revision", "desired_revision", "applied_revision", "change_sequence",
    "group_size", "planned_wait_ms", "attempt", "max_attempts", "acquire_ms", "transaction_ms", "attempt_ms", "total_ms", "retry_delay_ms",
    "sqlite_code", "sqlite_primary_code", "count", "duration_ms", "due_at"})
BOOLS = frozenset({"transport_observable", "acknowledged", "current", "reused", "truncated"})
LISTS = frozenset({"item_ids", "receipt_ids", "source_ids", "members", "outcomes"})


def safe_event(value):
    result = {}
    for key, item in value.items():
        if key in TEXT and isinstance(item, str) and _CODE.fullmatch(item):
            result[key] = item
        elif key in NUMBERS and isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item):
            result[key] = item
        elif key in BOOLS and isinstance(item, bool):
            result[key] = item
        elif key in LISTS and isinstance(item, (list, tuple)):
            result[key] = [safe_event(row) if isinstance(row, dict) else row for row in item[:64]
                           if isinstance(row, dict) or isinstance(row, str) and _CODE.fullmatch(row)]
            if len(item) > 64:
                result["truncated"] = True
    return result


class MemoryPipelineObserver:
    def __init__(self, data_root, process_id, *, capacity=512, wake=None):
        self.root, self.process_id = Path(data_root), process_id
        self.queue = Queue(maxsize=capacity)
        self.lock = Lock()
        self.active = None
        self.sessions = {}
        self.last_flush = 0
        self.aliases = {}
        self.item_scopes = {}
        self.closed = False
        self.source_digest = None
        self.remove = lambda: None
        self.registered = False
        self.wake = wake
        self.wake_pending = False

    def attach(self, manifest):
        session_id = manifest["session_id"]
        if self.closed or self.sessions.get(session_id, {}).get("final"):
            return
        if self.source_digest is None:
            try:
                self.source_digest = sha256(Path(__file__).read_bytes()).hexdigest()
            except OSError:
                self.source_digest = "unavailable"  # Frozen package/source access is not assumed.
        previous = self.active
        if previous and previous["session_id"] != session_id:
            self.flush(final=True)
            self.aliases.clear()
            self.item_scopes.clear()
        self.active = dict(manifest)
        self.active["database_id"] = work_observation.database_id(self.root / manifest["database_relative_path"])
        self.sessions.setdefault(session_id, {"expected": Counter(), "written": Counter(), "sequence": 0,
            "dropped": 0, "dropped_lock_busy": 0, "dropped_queue_full": 0,
            "failed": 0, "truncated": 0, "bytes": 0, "final": False})
        if not self.registered:
            # An in-flight caller may still hold the previous callback at rebind.
            self.remove = work_observation.install(lambda value: self.observe(value, session_id=session_id))
            self.registered = True
            self.last_flush = 0
        self.flush()

    def refresh(self, manifest):
        if manifest and self.active and manifest["session_id"] == self.active["session_id"]:
            self.active["stopped_at"] = manifest.get("stopped_at")

    def observe(self, value, *, session_id):
        manifest = self.active
        if manifest is None or self.closed or manifest["session_id"] != session_id:
            return
        state = self.sessions[session_id]
        if state["final"]:
            return
        # No manifest/DB/file reads on the caller's thread.
        end = manifest.get("stopped_at") or manifest["tail_ends_at"]
        if datetime.now(UTC) >= datetime.fromisoformat(end.replace("Z", "+00:00")):
            return
        if not self.lock.acquire(blocking=False):
            if not state["final"]:
                state["dropped"] += 1
                state["dropped_lock_busy"] += 1
            return
        notify = False
        try:
            # Finalization closes admission under the same short lock BEFORE
            # draining. A caller captured before cutoff must not enqueue later.
            if self.closed or self.active is not manifest or state["final"]:
                return
            if value.get("event") == "diagnostic_loss":
                state["dropped"] += 1
                return
            actor, world = value.get("actor_id"), value.get("world_id")
            if (world and world != manifest["world_id"]) or (actor and actor not in manifest["actor_ids"]):
                return
            if actor and world and value.get("item_id") and len(self.item_scopes) < 4096:
                self.item_scopes[value["item_id"]] = (actor, world)
            if not actor and value.get("item_id"):
                known = self.item_scopes.get(value["item_id"])
                if not known:
                    return
                actor, world = known
                value = {**value, "actor_id": actor, "world_id": world}
            if (world and world != manifest["world_id"]) or (actor and actor not in manifest["actor_ids"]):
                return
            if actor is None:
                # Competing writers carry timing only; unscoped memory does not.
                if value.get("event") not in {"sqlite", "sqlite_attempt", "postgresql", "postgresql_attempt", "queue", "stage", "wait"}:
                    return
                database = value.get("database_id")
                if database and database != manifest["database_id"]:
                    return
            state["sequence"] += 1
            key = f"{value.get('event')}:{value.get('boundary', '')}"
            state["expected"][key] += 1  # Independent denominator, BEFORE enqueue.
            event = safe_event(value)
            credential = value.get("credential_id")
            if credential is not None:
                event["credential_alias"] = self.aliases.setdefault(str(credential), f"key-{len(self.aliases) + 1}")
            event.update(schema=CAPABILITY, process_instance_id=self.process_id, session_id=manifest["session_id"], sequence=state["sequence"])
            if event.get("truncated"):
                state["truncated"] += 1
            try:
                self.queue.put_nowait((manifest["session_id"], key, event))
                if self.wake is not None and not self.wake_pending:
                    self.wake_pending = True
                    notify = True
            except Full:
                state["dropped"] += 1
                state["dropped_queue_full"] += 1
        finally:
            self.lock.release()
        if notify:
            try:
                self.wake()  # Coalesced non-blocking signal; no caller-side disk I/O.
            except Exception:
                pass  # The existing discovery tick remains the fallback.

    def flush(self, *, final=False):
        # Called only by the recorder thread (or its closing owner after join).
        manifest = self.active
        if manifest is None:
            return
        state = self.sessions[manifest["session_id"]]
        if state["final"]:
            return
        with self.lock:
            self.wake_pending = False
        if final:
            with self.lock:
                state["final"] = True
                self.remove()
                self.registered = False
            # No file I/O under the admission lock. Drain only accepted events;
            # final health is attempted once, including when its write fails.
        for _ in range(self.queue.qsize() if final else 512):
            try:
                session, key, event = self.queue.get_nowait()
            except Empty:
                break
            state = self.sessions[session]
            try:
                directory = session_path(self.root, session) / "memory-pipeline"
                directory.mkdir(parents=True, exist_ok=True)
                data = (json.dumps(event, separators=(",", ":")) + "\n").encode()
                if len(data) > EVENT_LIMIT:
                    state["truncated"] += 1
                    continue
                if state["bytes"] + len(data) > SESSION_LIMIT:
                    state["dropped"] += 1
                    continue
                part = state["bytes"] // (4 * 1024 * 1024)
                with (directory / f"events-{self.process_id}-{part:04d}.jsonl").open("ab") as output:
                    output.write(data)
                state["bytes"] += len(data)
                state["written"][key] += 1
            except OSError:
                state["failed"] += 1
            finally:
                self.queue.task_done()
        if not final and monotonic() - self.last_flush < 1:
            return
        self.last_flush = monotonic()
        state = self.sessions[manifest["session_id"]]
        # Copy briefly; never hold the admission lock while writing a file.
        with self.lock:
            health = {key: dict(value) if isinstance(value, Counter) else value for key, value in state.items()}
        health.update(schema=CAPABILITY, process_instance_id=self.process_id, session_id=manifest["session_id"],
            heartbeat_at=datetime.now(UTC).isoformat(), queued=self.queue.qsize(), source_digest=self.source_digest,
            transport_support=["google-genai-2.17-httpx-public-hooks"], unsupported_transports=["aiohttp", "other_providers"],
            writer_support="bounded_sqlite_and_postgresql_helpers", writer_coverage="partial_plain_session_and_external_processes_unobserved")
        try:
            atomic_json(session_path(self.root, manifest["session_id"]) / "memory-pipeline" / f"health-{self.process_id}.json", health)
        except OSError:
            state["failed"] += 1

    def close(self):
        self.closed = True
        self.flush(final=True)
