"""Manual memory observation uses the existing recorder without starting work."""
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import create_engine

from app.core import work_observation as observation
from app.core.sqlite_concurrency import run_sqlite_immediate
from app.providers.contracts import EmbeddingBatchRequest
from app.providers.gemini import GeminiAdapter
from app.runtime.diagnostics.memory_pipeline_report import read_events, timing
from app.runtime.diagnostics.sns_observation import SNSObserver
from app.runtime.diagnostics.sns_observation_report import session_status, start_session, stop_session
from tests.memory.test_embedding_batch_transport import transport
from tests.runtime.test_observation_session_lifecycle import finalized, wait_until, wake
from tests.runtime.test_sns_observation import data_root


@pytest.fixture
def manual_root(data_root):
    database = data_root / "canonical/generations/test/angmoo.sqlite3"
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE memory_scope_settings (
                world_id TEXT, subject_world_character_id TEXT, enabled INTEGER);
            INSERT INTO memory_scope_settings VALUES ('world-1','actor-1',1);
            UPDATE world_characters SET autonomous_enabled=0;
            CREATE TABLE observation_probe (value INTEGER);
        """)
    return data_root


def test_manual_cli_admits_disabled_autonomy_without_canonical_writes(manual_root):
    database = manual_root / "canonical/generations/test/angmoo.sqlite3"
    before = sha256(database.read_bytes()).hexdigest()
    cli = Path(__file__).resolve().parents[2] / "scripts/sns_observation.py"
    result = subprocess.run([sys.executable, str(cli), "--data-root", str(manual_root),
        "start", "--mode", "memory", "--world", "world-1", "--actor", "actor-1",
        "--minutes", "1", "--tail-minutes", "0"],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["observation_mode"] == "memory"
    assert manifest["actor_ids"] == ["actor-1"]
    assert sha256(database.read_bytes()).hexdigest() == before
    assert session_status(manual_root, manifest["session_id"])["observation_mode"] == "memory"


@pytest.mark.parametrize("case", ["no_actor", "foreign_actor", "inactive", "memory_disabled", "invalid_mode", "default_sns"])
def test_admission_keeps_scope_and_default_sns_guards(manual_root, case):
    database = manual_root / "canonical/generations/test/angmoo.sqlite3"
    with sqlite3.connect(database) as db:
        if case == "inactive":
            db.execute("UPDATE world_characters SET status='removed'")
        if case == "memory_disabled":
            db.execute("UPDATE memory_scope_settings SET enabled=0")
    args = {"world_id": "world-1", "actor_ids": ["actor-1"], "mode": "memory"}
    if case == "no_actor":
        args["actor_ids"] = None
    if case == "foreign_actor":
        args["actor_ids"] = ["other-world-actor"]
    if case == "invalid_mode":
        args["mode"] = "unknown"
    if case == "default_sns":
        args.pop("mode")
    with pytest.raises(ValueError, match="sns_observation_"):
        start_session(manual_root, **args)
    assert not (manual_root / "diagnostics/sns/active.json").exists()


def test_manual_session_collects_transport_writer_and_stops(manual_root, transport):
    manifest = start_session(manual_root, world_id="world-1", actor_ids=["actor-1"],
        mode="memory", minutes=1, tail_minutes=0)
    session_id = manifest["session_id"]
    directory = manual_root / "diagnostics/sns" / session_id
    database = manual_root / "canonical/generations/test/angmoo.sqlite3"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    observer = SNSObserver(manual_root, heartbeat_seconds=0.02)
    try:
        wait_until(lambda: session_status(manual_root, session_id)["memory_pipeline"]["runtime_fresh"])
        assert observation.enabled()
        with observation.scope(world_id="world-1", actor_id="actor-1", run_id="manual-fixture", batch_id="batch"):
            asyncio.run(GeminiAdapter().embed_batch_measured(EmbeddingBatchRequest(
                "SECRET-KEY", "gemini-embedding-2", ("PRIVATE-one", "PRIVATE-two"), 768), timeout_seconds=30))
            run_sqlite_immediate(engine, lambda db: db.exec_driver_sql("INSERT INTO observation_probe VALUES (1)"))
        stop_session(manual_root, session_id)
        wake(observer)
        wait_until(lambda: finalized(manual_root, session_id))
        assert not observation.enabled()
    finally:
        observer.close()
        engine.dispose()
    events, damaged = read_events(directory)
    assert not damaged
    attempts = [e for e in events if e.get("event") == "embedding_http" and e.get("boundary") == "attempt_start"]
    assert len(attempts) == len(transport[0]) == 1
    assert attempts[0]["input_count"] == 2
    spans, _ = timing(events)
    writers = [s for s in spans if s["operation"] == "sqlite_writer"]
    assert len(writers) == 1
    assert writers[0]["attempts"][0]["begin_wait_ms"] >= 0
    assert writers[0]["attempts"][0]["writer_hold_ms"] >= 0
    assert "PRIVATE" not in json.dumps(events) and "SECRET" not in json.dumps(events)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT autonomous_enabled FROM world_characters").fetchone()[0] == 0
