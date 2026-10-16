"""Real temporary writers and queue barriers, no product database or AI."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core import work_observation as observation
from app.core.sqlite_concurrency import (run_sqlite_immediate, run_sqlite_session_immediate,
    sqlite_session_attempt, SqliteBoundedTaskQueue, SqliteRetryPolicy, SqliteBusyRetryExhausted)
from app.runtime.diagnostics.memory_pipeline_report import timing


@pytest.fixture
def events():
    rows=[];remove=observation.install(lambda value: rows.append({**value,"process_instance_id":"test"}))
    try: yield rows
    finally: remove()


def test_writer_boundaries_rollback_busy_and_timeout_restore(tmp_path,events):
    engine=create_engine(f"sqlite:///{tmp_path/'test.sqlite3'}")
    run_sqlite_immediate(engine,lambda db:db.exec_driver_sql("CREATE TABLE values_table(id INTEGER)"))
    with engine.connect() as holder:
        holder.exec_driver_sql("BEGIN IMMEDIATE")
        with pytest.raises(SqliteBusyRetryExhausted):
            run_sqlite_immediate(engine,lambda db:db.exec_driver_sql("INSERT INTO values_table VALUES (1)"),retry_policy=SqliteRetryPolicy(max_attempts=1))
        holder.rollback()
    with Session(engine) as db:
        with pytest.raises(ValueError):
            with sqlite_session_attempt(db):
                db.connection().exec_driver_sql("INSERT INTO values_table VALUES (2)")
                raise ValueError("do not commit")
        run_sqlite_session_immediate(db,lambda:db.connection().exec_driver_sql("INSERT INTO values_table VALUES (3)"))
    with engine.connect() as db:
        assert db.exec_driver_sql("SELECT id FROM values_table").all()==[(3,)]
        assert db.exec_driver_sql("PRAGMA busy_timeout").scalar()==5000
    spans,summary=timing(events)
    assert summary["open_spans"]==0
    assert any(a["terminal"]=="rolled_back" and a["writer_hold_ms"] is not None for s in spans for a in s["attempts"])
    assert any(a["terminal"]=="incomplete" and a["writer_hold_ms"] is None for s in spans for a in s["attempts"])
    assert any(e.get("result")=="exhausted" for e in events)
    engine.dispose()


def test_queue_wait_context_cancellation_and_nested_database_timings(tmp_path,events):
    entered,release=Event(),Event()
    first=create_engine(f"sqlite:///{tmp_path/'first.db'}");second=create_engine(f"sqlite:///{tmp_path/'second.db'}")
    with SqliteBoundedTaskQueue(capacity=3) as queue:
        future=queue.submit(lambda:(entered.set(),release.wait(5)))
        assert entered.wait(5)
        with observation.scope(world_id="w",actor_id="a",run_id="r"):
            task=queue.submit(run_sqlite_immediate,first,lambda db:run_sqlite_immediate(second,lambda inner:inner.exec_driver_sql("CREATE TABLE example(id INTEGER)")))
            cancelled=queue.submit(lambda:pytest.fail("cancelled work executed"))
        assert cancelled.cancel()
        assert not task.done()
        release.set();future.result(5);task.result(5)
    spans,summary=timing(events)
    writers=[s for s in spans if s["operation"]=="sqlite_writer"]
    assert len(writers)==2 and len({s["database_id"] for s in writers})==2
    assert all(s["actor_id"]=="a" and s["run_id"]=="r" for s in writers)
    assert any(s["parent_span_id"] in {w["span_id"] for w in writers} for s in writers)
    assert any(row["terminal"]=="cancelled" for row in summary["queues"])
    assert any(row["wait_ms"] is not None and row["wait_ms"]>0 for row in summary["queues"])
    assert summary["nested_spans_additive"] is False
    first.dispose();second.dispose()
