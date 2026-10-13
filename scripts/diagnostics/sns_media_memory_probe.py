"""Bounded read-only supplements for an existing opt-in SNS session.

No provider, settings mutation, startup, graph resume or arbitrary target scan.
Run locally with backend on PYTHONPATH, or pipe to a running container's Python.
"""
from contextlib import closing
from datetime import UTC, datetime
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sqlite3
import sys

if "__file__" in globals() and Path(__file__).name != "<stdin>":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.core.calendar import utc_instant
from app.runtime.persistence.sqlite_codecs import encode_utc_timestamp
from app.runtime.diagnostics.sns_observation_report import database_path
from app.runtime.diagnostics.sns_observation import read_session


def instant(value):
    if not isinstance(value, str):
        raise ValueError("collector_time_string_required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("collector_time_offset_required")
    return result.astimezone(UTC)


def db_instant(value):
    # Official legacy naive-UTC interpretation, then official export codec.
    return encode_utc_timestamp(utc_instant(datetime.fromisoformat(value.replace("Z", "+00:00")))) if value else None


def collect(path, manifest):
    start, end, tail = (instant(manifest[key]) for key in ("started_at", "ends_at", "tail_ends_at"))
    actors = manifest["actor_ids"]
    if not actors or len(actors) > 100 or not all(isinstance(actor, str) and len(actor) <= 64 for actor in actors):
        raise ValueError("collector_actor_scope_invalid")
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        columns = {row["name"] for row in db.execute("PRAGMA table_info(posts)")}
        if not {"id", "world_id", "reply_to_post_id", "title", "body"} <= columns:
            raise ValueError("collector_posts_schema_incompatible")
        inventory = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        runs = list(db.execute("SELECT activity_id,started_at,status FROM activity_graph_runs WHERE world_id=? "
            "AND world_character_id IN (" + ",".join("?" for _ in actors) + ") ORDER BY started_at DESC LIMIT 1000",
            (manifest["world_id"], *actors)))
        selected = [row for row in runs if row["activity_id"] in manifest.get("carry_in_ids", [])
            or start <= instant(db_instant(row["started_at"])) < end]
        posts, receipts, application, effect_ids = {}, [], [], set()
        for run in selected:
            for row in db.execute("SELECT id,result,status FROM agent_public_action_executions WHERE run_id=? AND status='succeeded' LIMIT 100",
                (run["activity_id"],)):
                effect_ids.add(row["id"])
                result = json.loads(row["result"] or "{}")
                if isinstance(result, dict) and isinstance(result.get("post_id"), str):
                    posts[result["post_id"]] = None
            if "memory_situation_receipts" in inventory:
                for row in db.execute("SELECT r.sequence,r.lane,r.state,r.description_status,r.error_code,r.captured_at,r.result "
                    "FROM memory_situation_receipts r JOIN memory_scope_settings s ON s.id=r.scope_setting_id "
                    "WHERE r.logical_activity_id=? AND s.world_id=? AND s.subject_world_character_id IN (" +
                    ",".join("?" for _ in actors) + ") ORDER BY r.sequence LIMIT 1000", (run["activity_id"], manifest["world_id"], *actors)):
                    if instant(db_instant(row["captured_at"])) >= tail:
                        continue
                    result = json.loads(row["result"] or "{}")
                    for effect in result.get("effects", []):
                        if effect.get("status") == "succeeded" and effect.get("source_type") in {"POST", "REPLY"}:
                            posts[effect["source_id"]] = None
                    receipts.append({key: row[key] for key in ("sequence", "lane", "state", "description_status", "error_code")})
        prepared = []
        for identifier in list(posts):
            row = db.execute("SELECT id,reply_to_post_id,title,body FROM posts WHERE id=? AND world_id=?",
                (identifier, manifest["world_id"])).fetchone()
            if row is None:
                continue
            entry = {"post_id": row["id"], "reply_to_post_id": row["reply_to_post_id"],
                "title_digest": sha256(row["title"].encode()).hexdigest(), "body_digest": sha256(row["body"].encode()).hexdigest()}
            if row["reply_to_post_id"]:
                parent = db.execute("SELECT id,body FROM posts WHERE id=? AND world_id=?",
                    (row["reply_to_post_id"], manifest["world_id"])).fetchone()
                entry["parent_exists"] = parent is not None
                if parent:
                    entry["parent_body_digest"] = sha256(parent["body"].encode()).hexdigest()
            if "post_image_generation_jobs" in inventory:
                entry["image_jobs"] = [dict(item) for item in db.execute(
                    "SELECT id,status FROM post_image_generation_jobs WHERE post_id=? LIMIT 16", (identifier,))]
            prepared.append(entry)
        if "memory_situation_runs" in inventory:
            application = [dict(row) for row in db.execute("SELECT r.id,r.state,r.work_kind,r.cutoff_sequence,r.applied_count,r.blocked_count,r.error_code "
                "FROM memory_situation_runs r JOIN memory_scope_settings s ON s.id=r.scope_setting_id WHERE s.world_id=? "
                "AND s.subject_world_character_id IN (" + ",".join("?" for _ in actors) + ") ORDER BY r.created_at DESC LIMIT 100",
                (manifest["world_id"], *actors))]
        return {"schema": "sns-media-memory-supplement.v1", "status": "ok", "started_utc": encode_utc_timestamp(start),
            "ends_utc": encode_utc_timestamp(end), "tail_ends_utc": encode_utc_timestamp(tail),
            "activity_count": len(selected), "effect_count": len(effect_ids), "posts": prepared, "receipts": receipts,
            "admission_blocked": sum(row["state"] == "blocked" for row in receipts),
            "description_missing": sum(row["description_status"] == "missing" for row in receipts),
            "application_runs_separate_from_admission": application, "inventory_truncated": len(runs) == 1000}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        manifest = read_session(args.data_root, args.session)
        print(json.dumps(collect(database_path(args.data_root), manifest), ensure_ascii=False))
    except (OSError, ValueError, KeyError, sqlite3.Error):
        print(json.dumps({"status": "error", "code": "collector_probe_failed"}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
