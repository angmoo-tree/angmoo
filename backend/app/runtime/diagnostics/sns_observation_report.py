"""Local SNS observation session control and read-only report assembly."""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from uuid import uuid4

from app.core.ids import length_prefixed_identity_key as identity_key
from app.runtime.diagnostics.sns_observation import (
    SCHEMA_VERSION, _atomic_json, active_session, deadline, observation_root,
    read_session, session_path, utc,
)


def database_path(data_root: Path, explicit: Path | None = None) -> Path:
    root = data_root.resolve(strict=True)
    canonical = (root / "canonical").resolve(strict=True)
    if explicit is None:
        marker = canonical / "current-generation.json"
        current = json.loads(marker.read_text(encoding="utf-8"))
        if current.get("schema_version") != 1:
            raise ValueError("sns_generation_marker_invalid")
        relative = current.get("relative_path") or f"generations/{current['generation']}"
        selected = canonical / relative / "angmoo.sqlite3"
    else:
        selected = explicit
    selected = selected.resolve(strict=True)
    if not selected.is_relative_to(canonical) or selected.name != "angmoo.sqlite3":
        raise ValueError("sns_database_outside_canonical_data")
    return selected


def _open_readonly(path: Path):
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA busy_timeout=3000")
    return connection


def list_worlds(data_root: Path, explicit_db: Path | None = None) -> list[dict]:
    with closing(_open_readonly(database_path(data_root, explicit_db))) as db:
        return [dict(row) for row in db.execute(
            "SELECT id, name, status FROM worlds ORDER BY name LIMIT 200")]


def _select_actors(db, world_id: str, requested: list[str] | None) -> list[str]:
    row = db.execute("SELECT id FROM worlds WHERE id=?", (world_id,)).fetchone()
    if row is None:
        raise ValueError("sns_observation_world_not_found")
    available = {row["id"] for row in db.execute(
        "SELECT id FROM world_characters WHERE world_id=? AND status='active' "
        "AND control_mode='autonomous' AND autonomous_enabled=1", (world_id,))}
    chosen = set(requested or available)
    if not chosen or not chosen <= available:
        raise ValueError("sns_observation_actor_scope_invalid")
    policies = {row["scope_key"]: row["engine"] for row in db.execute(
        "SELECT scope_key, engine FROM activity_engine_policies WHERE scope_key='global' "
        "OR scope_key=? OR scope_key IN (" + ",".join("?" for _ in chosen) + ")",
        (f"world:{world_id}", *(f"character:{item}" for item in chosen)))}
    for actor_id in chosen:
        engine = next((policies[key] for key in (f"character:{actor_id}", f"world:{world_id}", "global")
                       if key in policies), "personalized_graph_v2")
        if engine != "personalized_graph_v2":
            raise ValueError("sns_observation_actor_not_v2")
    return sorted(chosen)


def start_session(data_root: Path, *, world_id: str, actor_ids: list[str] | None = None,
                  minutes: int = 120, tail_minutes: int = 10,
                  explicit_db: Path | None = None, source_revision: str | None = None,
                  now: datetime | None = None) -> dict:
    if not 1 <= minutes <= 1440 or not 0 <= tail_minutes <= 60:
        raise ValueError("sns_observation_duration_invalid")
    now = utc(now) or datetime.now(UTC)
    data_root = data_root.resolve(strict=True)
    db_path = database_path(data_root, explicit_db)
    prior = active_session(data_root)
    if prior is not None and now < deadline(prior):
        raise ValueError("sns_observation_session_already_active")
    with closing(_open_readonly(db_path)) as db:
        chosen = _select_actors(db, world_id, actor_ids)
        world_timezone = db.execute("SELECT timezone FROM worlds WHERE id=?", (world_id,)).fetchone()[0]
        placeholders = ",".join("?" for _ in chosen)
        carry_in = [row["activity_id"] for row in db.execute(
            f"SELECT activity_id FROM activity_graph_runs WHERE world_id=? AND "
            f"world_character_id IN ({placeholders}) AND status IN ('running','waiting','interrupted') "
            "ORDER BY started_at DESC LIMIT 100", (world_id, *chosen))]
        slots = [dict(row) for row in db.execute(
            f"SELECT s.agent_id, s.status, s.next_tick_at, s.heartbeat_interval_seconds, s.locked_by_run_id "
            f"FROM agent_slots s JOIN world_characters c ON c.character_id=s.assigned_character_id "
            f"WHERE c.world_id=? AND c.id IN ({placeholders})", (world_id, *chosen))]
    session_id = "sns-" + uuid4().hex
    manifest = {"schema_version": SCHEMA_VERSION, "session_id": session_id,
                "world_id": world_id, "world_timezone": world_timezone, "actor_ids": chosen,
                "started_at": now.isoformat(), "ends_at": (now + timedelta(minutes=minutes)).isoformat(),
                "tail_ends_at": (now + timedelta(minutes=minutes + tail_minutes)).isoformat(),
                "stopped_at": None, "carry_in_ids": carry_in,
                "source_revision": source_revision or "unknown",
                "database_relative_path": db_path.relative_to(data_root).as_posix(),
                "initial_slots": slots, "event_schema_version": SCHEMA_VERSION,
                "event_limit_bytes": 8192, "session_limit_bytes": 64 * 1024 * 1024}
    directory = session_path(data_root, session_id)
    directory.mkdir(parents=True, exist_ok=False)
    probe = directory / ".write-probe"
    probe.write_bytes(b"ready")
    if probe.read_bytes() != b"ready":
        raise OSError("sns_observation_write_preflight_failed")
    probe.unlink()
    _atomic_json(directory / "manifest.json", manifest)
    _atomic_json(observation_root(data_root) / "active.json", {"session_id": session_id})
    return manifest


def stop_session(data_root: Path, session_id: str, *, now: datetime | None = None) -> dict:
    manifest = read_session(data_root, session_id)
    ended = utc(now) or datetime.now(UTC)
    if ended < utc(manifest["started_at"]):
        raise ValueError("sns_observation_stop_before_start")
    if manifest.get("stopped_at") is None:
        manifest["stopped_at"] = ended.isoformat()
        _atomic_json(session_path(data_root, session_id) / "manifest.json", manifest)
    return manifest


def session_status(data_root: Path, session_id: str, *, now: datetime | None = None) -> dict:
    manifest = read_session(data_root, session_id)
    directory = session_path(data_root, session_id)
    health = []
    for path in directory.glob("recorder-health-*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("session_id") == session_id:
                health.append(item)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    now = utc(now) or datetime.now(UTC)
    state = "stopped" if manifest.get("stopped_at") else "complete_window" if now >= deadline(manifest) else "tail" if now >= utc(manifest["ends_at"]) else "collecting"
    latest = max((utc(item.get("last_loop_at") or item.get("heartbeat_at")) for item in health
                  if item.get("last_loop_at") or item.get("heartbeat_at")), default=None)
    lifecycle = {item.get("lifecycle_state") for item in health}
    liveness = ("unknown" if latest is None else "fatal" if "fatal" in lifecycle
                else "closed" if lifecycle <= {"closed", "finalized"}
                else "fresh" if (now - latest).total_seconds() <= 150 else "stale")
    return {"session_id": session_id, "state": state, "started_at": manifest["started_at"],
            "ends_at": manifest["ends_at"], "tail_ends_at": manifest["tail_ends_at"],
            "world_id": manifest["world_id"], "actor_ids": manifest["actor_ids"],
            "recorder_health": health, "event_files": len(list(directory.glob("events-*.jsonl"))),
            "recorder_liveness": liveness, "window_elapsed": now >= utc(manifest["ends_at"]),
            "tail_elapsed": now >= utc(manifest["tail_ends_at"]),
            "stopped_early": bool(manifest.get("stopped_at")) and
                utc(manifest["stopped_at"]) < utc(manifest["tail_ends_at"]),
            "admission_cutoff_at": deadline(manifest).isoformat(),
            "data_directory": str(directory)}


def _events(directory: Path, session_id: str) -> tuple[list[dict], int]:
    events: list[dict] = []
    damaged = 0
    for path in sorted(directory.glob("events-*.jsonl")):
        with path.open("r", encoding="utf-8") as source:
            for line in source:
                try:
                    event = json.loads(line)
                    if event.get("session_id") == session_id and event.get("schema_version") in {1, 2}:
                        events.append(event)
                    else:
                        damaged += 1
                except (ValueError, TypeError):
                    damaged += 1
    events.sort(key=lambda row: (row.get("occurred_at") or "", row.get("event_id") or ""))
    return events, damaged


def _jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _canonical_rows(db, manifest: dict, included: set[str]) -> tuple[list[dict], list[dict]]:
    actors = manifest["actor_ids"]
    placeholders = ",".join("?" for _ in actors)
    runs: list[dict] = []
    effects: list[dict] = []
    for row in db.execute(f"SELECT activity_id, world_character_id, engine, status, stage, result, "
                          f"started_at, finished_at FROM activity_graph_runs WHERE world_id=? AND "
                          f"world_character_id IN ({placeholders}) ORDER BY started_at DESC LIMIT 3000",
                          (manifest["world_id"], *actors)):
        began = utc(row["started_at"])
        if began is None or row["activity_id"] not in included and not (
            utc(manifest["started_at"]) <= began < utc(manifest["ends_at"])):
            continue
        result = json.loads(row["result"]) if row["result"] else {}
        paths = result.get("paths") or {}
        runs.append({"activity_id": row["activity_id"], "actor_id": row["world_character_id"],
                     "engine": row["engine"], "status": row["status"], "stage": row["stage"],
                     "started_at": row["started_at"], "finished_at": row["finished_at"],
                     "paths": {lane: {"status": item.get("status"), "public_action_count": item.get("public_action_count", 0),
                               "recall_status": item.get("recall_status")}
                               for lane, item in paths.items() if isinstance(item, dict)},
                     "public_action_count": (result.get("publish_result") or {}).get("public_action_count")})
    actor_by_activity = {row["activity_id"]: row["actor_id"] for row in runs}
    for activity_id in sorted(actor_by_activity):
        for row in db.execute("SELECT id, run_id, scope, action_type, target_post_id, status, "
                              "failure_class, created_at, completed_at FROM agent_public_action_executions "
                              "WHERE run_id=?", (activity_id,)):
            effects.append({"kind": "public_action", "activity_id": activity_id,
                            "execution_id": row["id"], "lane": row["scope"], "action": row["action_type"],
                            "target_post_id": row["target_post_id"], "status": row["status"],
                            "failure_class": row["failure_class"], "created_at": row["created_at"],
                            "completed_at": row["completed_at"]})
        for row in db.execute("SELECT decision_key, outcome, expected_version, resulting_version, judged_at "
                              "FROM world_character_state_receipts WHERE activity_id=?", (activity_id,)):
            effects.append({"kind": "state_receipt", "activity_id": activity_id,
                            "decision_key": row["decision_key"], "status": row["outcome"],
                            "expected_version": row["expected_version"], "resulting_version": row["resulting_version"],
                            "judged_at": row["judged_at"]})
        for lane in ("inbox", "routine", "feed"):
            key = identity_key(activity_id, lane, "decision")
            for row in db.execute("SELECT a.id, a.status, a.state_version, a.created_at, a.applied_at, "
                                  "r.target_world_character_id, r.source_key FROM relationship_metric_applications a "
                                  "JOIN relationship_experience_receipts r ON r.id=a.experience_id "
                                  "WHERE a.decision_key=? AND r.world_id=? AND r.actor_world_character_id=?",
                                  (key, manifest["world_id"], actor_by_activity[activity_id])):
                effects.append({"kind": "relationship_metric", "activity_id": activity_id,
                                "lane": lane, "application_id": row["id"], "target_id": row["target_world_character_id"],
                                "source_key": row["source_key"], "status": row["status"],
                                "state_version": row["state_version"], "created_at": row["created_at"],
                                "applied_at": row["applied_at"]})
    return runs, effects


def _scheduler_rows(db, manifest: dict) -> list[dict]:
    # AgentRun has no World column; only the verified initial slot IDs are
    # eligible. ActivityGraphRun remains the canonical V2 result source.
    slot_ids = [row.get("agent_id") for row in manifest.get("initial_slots", []) if row.get("agent_id")]
    if not slot_ids:
        return []
    placeholders = ",".join("?" for _ in slot_ids)
    started, ended = utc(manifest["started_at"]), deadline(manifest)
    rows = []
    for row in db.execute(
        f"SELECT id, agent_id, status, created_at, completed_at FROM agent_runs "
        f"WHERE agent_id IN ({placeholders}) ORDER BY created_at DESC LIMIT 3000", slot_ids
    ):
        created = utc(row["created_at"])
        if created is not None and started <= created < ended:
            rows.append({"agent_run_id": row["id"], "agent_id": row["agent_id"],
                         "status": row["status"], "created_at": row["created_at"],
                         "completed_at": row["completed_at"]})
    return rows


def export_session(data_root: Path, session_id: str, *, destination: Path,
                   explicit_db: Path | None = None, now: datetime | None = None) -> dict:
    manifest = read_session(data_root, session_id)
    directory = session_path(data_root, session_id)
    destination = destination.resolve()
    if destination == directory or destination.is_relative_to(directory):
        raise ValueError("sns_observation_export_inside_source")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("sns_observation_export_destination_not_empty")
    destination.mkdir(parents=True, exist_ok=True)
    events, damaged = _events(directory, session_id)
    actor_ids = set(manifest["actor_ids"])
    allowed_end = deadline(manifest)
    control_types = {"heartbeat", "scheduler_sample", "recorder_attached", "recorder_closing",
                     "recorder_closed", "session_finalized"}
    final_types = {"recorder_closed", "session_finalized"}
    events = [item for item in events if (item.get("actor_id") in actor_ids
              or item.get("event_type") in control_types)
              and utc(item.get("occurred_at")) is not None
              and (utc(item["occurred_at"]) < allowed_end or item.get("event_type") in final_types)]
    included = {row["activity_id"] for row in events if row.get("activity_id")}
    included.update(manifest.get("carry_in_ids") or [])
    db_path = database_path(data_root, explicit_db or data_root / manifest["database_relative_path"])
    with closing(_open_readonly(db_path)) as db:
        runs, effects = _canonical_rows(db, manifest, included)
        scheduler_runs = _scheduler_rows(db, manifest)
    errors: list[dict] = []
    call_events = []
    for item in events:
        event_type = item.get("event_type") or ""
        if event_type.startswith("llm_"):
            call_events.append(item)
        if event_type not in {"node_failed", "lane_error", "activity_interrupted"}:
            continue
        if item.get("caused_by_event_id"):
            continue  # A lane/parent/activity wrapper of the original failure.
        errors.append(item)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for item in errors:
        details = item.get("details") or {}
        first = (details.get("validation") or [{}])[0]
        fingerprint = (item.get("lane"), item.get("node"), details.get("error_code") or details.get("error_type"),
                       first.get("path"), first.get("type"))
        groups[fingerprint].append(item)
    grouped_errors = []
    for key, occurrences in groups.items():
        grouped_errors.append({"lane": key[0], "node": key[1], "error": key[2], "field_path": key[3],
                               "field_type": key[4], "count": len(occurrences),
                               "activity_count": len({item.get("activity_id") for item in occurrences}),
                               "first_at": occurrences[0].get("occurred_at"),
                               "last_at": occurrences[-1].get("occurred_at")})
    grouped_errors.sort(key=lambda row: (-row["count"], row["first_at"] or ""))
    status = session_status(data_root, session_id, now=now)
    health = status["recorder_health"]
    dropped = sum(int(item.get("dropped_count") or 0) for item in health)
    lane_counts: dict[str, Counter] = {lane: Counter() for lane in ("inbox", "routine", "feed")}
    for run in runs:
        for lane, result in run["paths"].items():
            if lane in lane_counts:
                lane_counts[lane][result.get("status") or "unknown"] += 1
    unclosed = [run["activity_id"] for run in runs if run["status"] in {"running", "waiting", "interrupted"}]
    now = utc(now) or datetime.now(UTC)
    observed_end = min(now, allowed_end)
    ticks = sorted(utc(row["occurred_at"]) for row in events if row.get("event_type") == "heartbeat")
    checkpoints = [utc(manifest["started_at"]), *ticks, observed_end]
    gaps = [round((right - left).total_seconds()) for left, right in zip(checkpoints, checkpoints[1:])
            if (right - left).total_seconds() > 150]
    window_elapsed = status["window_elapsed"]
    tail_elapsed = status["tail_elapsed"]
    stopped_early = status["stopped_early"]
    finalizations = [item for item in events if item.get("event_type") == "session_finalized"]
    final = finalizations[-1] if finalizations else None
    flush_complete = ((final.get("details") or {}).get("flush_complete") is True) if final else None
    pending = (final.get("details") or {}).get("pending") if final else None
    effect_statuses = {kind: dict(Counter(row.get("status") or "unknown" for row in effects
        if row.get("kind") == kind)) for kind in ("public_action", "state_receipt", "relationship_metric")}
    coverage = {"session_id": session_id, "exported_at": now.isoformat(),
                "window_started_at": manifest["started_at"], "window_ends_at": manifest["ends_at"],
                "tail_ends_at": manifest["tail_ends_at"], "session_state": session_status(data_root, session_id)["state"],
                "events": len(events), "run_count": len(runs), "error_count": len(errors),
                "damaged_event_lines": damaged, "dropped_events": dropped,
                "lane_statuses": {key: dict(value) for key, value in lane_counts.items()},
                "effect_statuses": effect_statuses,
                 "open_activity_ids": unclosed, "heartbeat_gap_seconds": gaps,
                 "window_elapsed": window_elapsed, "tail_elapsed": tail_elapsed,
                 "stopped_early": stopped_early,
                 "admission_cutoff_at": allowed_end.isoformat(),
                 "recorder_liveness": status["recorder_liveness"],
                 "flush_complete": flush_complete, "finalization_at": final.get("occurred_at") if final else None,
                 "pending_events": pending, "control_event_count": sum(item.get("event_type") in control_types for item in events),
                 "scheduler_run_count": len(scheduler_runs),
                 "scheduler_statuses": dict(Counter(row["status"] for row in scheduler_runs)),
                 "complete_recording": manifest["schema_version"] == 2 and tail_elapsed
                     and not stopped_early and flush_complete is True and bool(ticks)
                     and not gaps and not damaged and not dropped and pending == 0,
                "observed_any_activity": bool(runs),
                "unobserved_lanes": [lane for lane, statuses in lane_counts.items() if not statuses],
                "database_extracted_at": datetime.now(UTC).isoformat(),
                "database_path": str(db_path)}
    _atomic_json(destination / "manifest.json", manifest)
    _jsonl(destination / "runs.jsonl", runs)
    _jsonl(destination / "scheduler.jsonl", scheduler_runs)
    _jsonl(destination / "errors.jsonl", errors)
    _jsonl(destination / "calls.jsonl", call_events)
    _jsonl(destination / "effects.jsonl", effects)
    _jsonl(destination / "control.jsonl", [item for item in events if item.get("event_type") in control_types])
    _atomic_json(destination / "coverage.json", coverage)
    events_dir = destination / "events"
    events_dir.mkdir(exist_ok=True)
    for path in directory.glob("events-*.jsonl"):
        shutil.copyfile(path, events_dir / path.name)
    with (destination / "errors.csv").open("w", encoding="utf-8", newline="") as output:
        columns = ("lane", "node", "error", "field_path", "field_type", "count", "activity_count", "first_at", "last_at")
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(grouped_errors)
    lines = ["# SNS V2 observation report", "", f"Session: `{session_id}`", f"World: `{manifest['world_id']}`",
             f"Window: {manifest['started_at']} – {manifest['ends_at']}",
             f"Canonical runs: {len(runs)}; scheduler attempts: {len(scheduler_runs)}; "
             f"recorded errors: {len(errors)}; diagnostic events: {len(events)}.",
             f"Recording complete: {'yes' if coverage['complete_recording'] else 'no/unknown'}; "
             f"dropped: {dropped}; damaged lines: {damaged}.", "", "## Lane outcomes", ""]
    for lane, statuses in lane_counts.items():
        lines.append(f"- {lane}: {dict(statuses) if statuses else 'NOT_OBSERVED'}")
    lines.extend(["", "## Scheduler attempts", "",
                  f"- {coverage['scheduler_statuses'] if scheduler_runs else 'NOT_OBSERVED'}",
                  "", "## Confirmed effects", "", f"- {effect_statuses}",
                  "", "## Repeated errors", ""])
    for row in grouped_errors:
        lines.append(f"- {row['lane'] or 'parent'} / {row['node'] or 'unknown'} / {row['error']}: "
                     f"{row['count']} events, {row['activity_count']} activities; field `{row['field_path'] or '-'}`")
    if not grouped_errors:
        lines.append("- No recorded errors. Check lane coverage and recorder health before calling this a pass.")
    if unclosed:
        lines.extend(["", f"Open activities at extraction: {len(unclosed)}. See coverage.json for IDs."])
    lines.extend(["", "This report records execution evidence; output naturalness and memory causality need separate review."])
    (destination / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return coverage
