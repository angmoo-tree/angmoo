"""Actual SDK SQLite rows and the durable late-writer boundary."""
import sqlite3
import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from app.runtime.autonomous_activity.checkpoints import erase_activity_checkpoint


def test_exact_sdk_checkpoint_erasure_removes_thought_and_fences_late_rows(tmp_path):
    path = tmp_path / "runtime/activity/activity-checkpoints.sqlite"
    path.parent.mkdir(parents=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        saver.setup()
        with saver.cursor() as cursor:
            for world in ("a", "b"):
                cursor.execute("INSERT INTO checkpoints(thread_id,checkpoint_id,type,checkpoint,metadata) VALUES(?,?,'json',?,?)",
                    ("activity:" + world, "first", b'{"private_thought":"fixture"}', b'{"source":"fixture"}'))
                cursor.execute("INSERT INTO writes(thread_id,checkpoint_id,task_id,idx,channel,type,value) VALUES(?,?,'task',0,'result','json',?)",
                    ("activity:" + world, "first", b'{"unfinished":"private fixture"}'))
    erase_activity_checkpoint(tmp_path, "a")
    erase_activity_checkpoint(tmp_path, "a")
    with sqlite3.connect(path) as db:
        for table in ("checkpoints", "writes"):
            assert db.execute(f"SELECT thread_id FROM {table}").fetchall() == [("activity:b",)]
        assert db.execute("SELECT thread_id FROM angmoo_erased_checkpoint_threads").fetchall() == [("activity:a",)]
        with pytest.raises(sqlite3.IntegrityError, match="world_deleting"):
            db.execute("INSERT INTO checkpoints(thread_id,checkpoint_id) VALUES('activity:a','late')")
        with pytest.raises(sqlite3.IntegrityError, match="world_deleting"):
            db.execute("UPDATE writes SET thread_id='activity:a'")
