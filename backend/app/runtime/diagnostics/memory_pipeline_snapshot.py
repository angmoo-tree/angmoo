"""Bounded read-only canonical/projection snapshots. Never opens a runtime."""
from contextlib import closing
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sqlite3
from time import monotonic


def _open(path, until):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.25)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.set_progress_handler(lambda: int(monotonic() > until), 1000)
    return connection


def snapshot(database, manifest, *, data_root=None):
    started = datetime.now(UTC).isoformat()
    result = {"schema": "memory-pipeline-snapshot.v1", "started_at": started, "status": "ok", "atomic_across_databases": False,
              "items": [], "receipts": [], "runs": [], "work": [], "maintenance": [], "changes": [], "brief": [], "projection": [], "truncated": False}
    actors = manifest["actor_ids"]
    if not actors or len(actors) > 100:
        raise ValueError("memory_snapshot_scope_invalid")
    until = monotonic() + 2
    params = (manifest["world_id"], *actors)
    placeholders = ",".join("?" for _ in actors)
    scope = f"s.world_id=? AND s.subject_world_character_id IN ({placeholders})"
    try:
        with closing(_open(database, until)) as db:
            before = db.execute("PRAGMA data_version").fetchone()[0]
            result["schema_version"] = db.execute("PRAGMA schema_version").fetchone()[0]
            inventory = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "memory_items" not in inventory:
                result["status"] = "unsupported_schema"
                return result
            queries = {
                "items": ("memory_items", f"SELECT id,version,world_id,subject_world_character_id,created_at,updated_at,status,deleted_at FROM memory_items s WHERE {scope} ORDER BY updated_at DESC LIMIT 1001"),
                "work": ("memory_vector_work", f"SELECT w.generation,w.item_id,w.desired_revision,w.applied_revision,w.last_change,w.state,w.due_at,w.last_code FROM memory_vector_work w JOIN memory_items s ON s.id=w.item_id WHERE {scope} ORDER BY w.item_id LIMIT 1001"),
                "receipts": ("memory_situation_receipts", f"SELECT r.sequence,r.run_id,r.applied_item_id,r.state,r.state_version,r.captured_at,r.applied_at FROM memory_situation_receipts r JOIN memory_scope_settings s ON s.id=r.scope_setting_id WHERE {scope} ORDER BY r.sequence DESC LIMIT 1001"),
                "runs": ("memory_situation_runs", f"SELECT r.id,r.state,r.cursor,r.cutoff_sequence,r.created_at,r.work_kind FROM memory_situation_runs r JOIN memory_scope_settings s ON s.id=r.scope_setting_id WHERE {scope} ORDER BY r.created_at DESC LIMIT 1001"),
                "brief": ("memory_situation_settings", f"SELECT c.scope_setting_id,c.brief_dirty FROM memory_situation_settings c JOIN memory_scope_settings s ON s.id=c.scope_setting_id WHERE {scope} LIMIT 1001"),
                "changes": ("memory_vector_changes", f"SELECT c.sequence,c.root_sequence,c.state,c.cursor FROM memory_vector_changes c JOIN memory_items s ON c.source_kind='memory' AND c.source_key=s.id WHERE {scope} ORDER BY c.sequence LIMIT 1001"),
            }
            for key, (table, query) in queries.items():
                if table not in inventory:
                    result.setdefault("unsupported", []).append(key)
                    continue
                rows = db.execute(query, params).fetchall()
                result["truncated"] |= len(rows) > 1000
                result[key] = [dict(row) for row in rows[:1000]]
            if "memory_vector_maintenance" in inventory:
                result["maintenance"] = [dict(row) for row in db.execute("SELECT generation,phase,cursor,upper_bound,cutoff,due_at FROM memory_vector_maintenance LIMIT 16")]
            if "memory_vector_eligibility" in inventory:
                result["eligibility"] = [dict(row) for row in db.execute(f"SELECT e.memory_item_id,e.content_hash,e.item_version,e.registered_at FROM memory_vector_eligibility e JOIN memory_items s ON s.id=e.memory_item_id WHERE {scope} LIMIT 1001", params)]
                result["truncated"] |= len(result["eligibility"]) > 1000
                result["eligibility"] = result["eligibility"][:1000]
            result["changed_during_snapshot"] = before != db.execute("PRAGMA data_version").fetchone()[0]
        if data_root is not None:
            _projection(Path(data_root), result, until)
            _fts(Path(data_root), manifest, result, until)
    except (sqlite3.Error, OSError, ValueError, RuntimeError):
        result["status"] = "partial_read_failed"
    finally:
        result["finished_at"] = datetime.now(UTC).isoformat()
    return result


def _projection(root, result, until):
    marker = root / "search/memory-vectors/current.json"
    if not marker.is_file():
        result["projection_status"] = "not_available"
        return
    before = marker.read_bytes()
    value = json.loads(before)
    generation = value.get("staging") or value.get("active")
    if value.get("version") != 1 or not isinstance(generation, str) or not re.fullmatch(r"v1|g-[a-f0-9]{32}", generation):
        raise ValueError("memory_generation_invalid")
    path = marker.parent / "generations" / generation / "vectors.sqlite3"
    from app.runtime.memory.vector_resources import bundled_vector_index
    index = bundled_vector_index(path, generation=generation)  # verifies bundle; no open/repair
    with index._connect(read_only=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.set_progress_handler(lambda: int(monotonic() > until), 1000)
        version = db.execute("PRAGMA data_version").fetchone()[0]
        for item in result["items"]:
            if monotonic() > until:
                raise TimeoutError("memory_snapshot_deadline")
            row = db.execute("SELECT d.version,d.content_hash,v.profile FROM documents d JOIN vectors v ON v.rowid=d.rowid WHERE d.memory_item_id=?", (item["id"],)).fetchone()
            if row:
                result["projection"].append({"item_id": item["id"], "version": row[0], "content_hash": row[1], "profile": row[2], "generation": generation})
        result["changed_during_snapshot"] |= version != db.execute("PRAGMA data_version").fetchone()[0]
    result["changed_during_snapshot"] |= before != marker.read_bytes()
    result["projection_status"] = "ok"


def _fts(root, manifest, result, until):
    from app.config import settings
    from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings, SqliteMemoryRecallIndex
    from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath

    # Construction only resolves paths. Never open or rebuild the index here.
    index = SqliteMemoryRecallIndex(
        StaticRuntimeDataPath(root),
        settings=MemoryRecallIndexSettings.for_representation(settings.MEMORY_RECALL_REPRESENTATION),
    )
    path = index.database_path
    result["fts_generation"] = index.settings.generation
    if not path.is_file():
        result["fts_status"] = "not_available"
        return
    with closing(_open(path, until)) as db:
        before = db.execute("PRAGMA data_version").fetchone()[0]
        placeholders = ",".join("?" for _ in manifest["actor_ids"])
        rows = db.execute(f"SELECT memory_item_id,kind,searchable,tombstoned_at FROM memory_recall_documents WHERE world_id=? AND subject_world_character_id IN ({placeholders}) LIMIT 1001", (manifest["world_id"], *manifest["actor_ids"])).fetchall()
        result["fts"] = [dict(row) for row in rows[:1000]]
        result["truncated"] |= len(rows) > 1000
        result["changed_during_snapshot"] |= before != db.execute("PRAGMA data_version").fetchone()[0]
        result["fts_status"] = "ok"
