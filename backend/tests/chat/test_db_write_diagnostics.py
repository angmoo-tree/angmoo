"""Known writer boundaries and unknown Session acquisition stay distinct."""
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session

from app.core import work_observation as observation
from app.core.session_write_observation import observe_session, finish_session, session_child
from app.core.sqlite_concurrency import run_sqlite_immediate, SqliteRetryPolicy
from app.domains.chat.contracts.db_write_diagnostics import DbWriteCollector


def feed(collector, boundary, ms, *, span="s", event="sqlite", **extra):
    collector.observe(dict(event=event, boundary=boundary, monotonic_ns=int(ms * 1_000_000),
        span_id=span, attempt=1, database_id="a" * 64, chat_stage="response_finalize", **extra))


def test_fake_boundaries_separate_checkout_acquisition_hold_and_commit():
    collector = DbWriteCollector()
    for boundary, ms in [("checkout_started", 0), ("checkout_complete", 2), ("begin_started", 3),
        ("acquired", 7), ("commit_started", 10), ("committed", 12)]:
        feed(collector, boundary, ms)
    result = collector.payload()
    row = result["attempts"][0]
    assert (row["checkout_ms"], row["acquire_ms"], row["hold_ms"], row["commit_ms"]) == (2, 4, 5, 2)
    assert result["longest_hold_ms"] == result["total_hold_ms"] == 5
    assert row["write_span_ms"] is None
    assert result["coverage"] == "complete"


def test_session_partial_retry_and_overflow_keep_honest_totals():
    collector = DbWriteCollector()
    feed(collector, "write_started", 0, event="session_write")
    feed(collector, "commit_started", 5, event="session_write")
    feed(collector, "committed", 6, event="session_write")
    row = collector.payload()["attempts"][0]
    assert row["hold_ms"] is None and row["acquire_ms"] is None and row["write_span_ms"] == 6
    feed(collector, "retry_wait_started", 10, span="retry")
    feed(collector, "retry_wait_complete", 13, span="retry")
    for index in range(80):
        feed(collector, "begin_started", 100, span=str(index))
        feed(collector, "acquired", 105, span=str(index))
        feed(collector, "committed", 106 + index, span=str(index))
    result = collector.payload()
    assert len(result["attempts"]) == 64 and result["omitted_attempts"] == 17
    assert result["longest_hold_ms"] == 80 and result["total_hold_ms"] == sum(range(1, 81))
    assert result["retry_count"] == 1 and result["retry_wait_ms"] == 3
    assert result["coverage"] == "partial"
    assert len(json.dumps(result)) < 32 * 1024


def test_session_savepoint_and_final_return_without_additional_sql(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "private-name.sqlite"))
    with engine.begin() as connection: connection.exec_driver_sql("CREATE TABLE t (n INTEGER)")
    sql, collector = [], DbWriteCollector()
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, statement, params, context, many: sql.append(statement))
    with Session(engine) as session, observation.local_observer(collector.observe, lambda: True), observe_session(session):
        session.execute(text("INSERT INTO t VALUES (1)"))
        with session_child(session), session.begin_nested():
            session.execute(text("UPDATE t SET n=2"))
        assert collector.payload()["completed_attempts"] == 0
        finish_session(session)
        result = collector.payload()
        assert result["completed_attempts"] == 1
        row = result["attempts"][0]
        assert row["hold_ms"] is None and row["write_span_ms"] is not None
        assert row["diagnostic_persist_ms"] is not None
        assert row["commit_ms"] <= row["write_span_ms"]
        statements = list(sql)
        assert collector.payload() == result and sql == statements
        session.execute(text("SELECT * FROM t")); finish_session(session, rollback=True)
        assert collector.payload()["completed_attempts"] == 1
    exported = json.dumps(result)
    assert "private-name" not in exported and "INSERT" not in exported and "SAVEPOINT" not in exported
    engine.dispose()


def test_off_has_no_timestamps_and_local_failure_does_not_replace_existing_sink(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "off.sqlite"))
    with engine.begin() as c: c.exec_driver_sql("CREATE TABLE t (n INTEGER)")
    def forbidden(): raise AssertionError("OFF clock called")
    monkeypatch.setattr(observation, "monotonic_ns", forbidden)
    with Session(engine) as session, observe_session(session):
        session.execute(text("INSERT INTO t VALUES (1)")); finish_session(session)
    monkeypatch.undo()
    global_events = []
    remove = observation.install(global_events.append)
    def broken(_): raise RuntimeError("collector failed")
    try:
        with observation.local_observer(broken, lambda: True):
            assert run_sqlite_immediate(engine, lambda c: c.exec_driver_sql("UPDATE t SET n=2").rowcount) == 1
        assert any(row.get("boundary") == "committed" for row in global_events)
    finally:
        remove(); engine.dispose()


def test_two_connections_release_writer_before_next_commit(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "writers.sqlite"), connect_args={"check_same_thread": False})
    with engine.begin() as c: c.exec_driver_sql("CREATE TABLE t (n INTEGER)")
    acquired, attempting, release = Event(), Event(), Event()
    collector = DbWriteCollector()
    def holder():
        with engine.connect() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE"); acquired.set()
            assert release.wait(5)
            c.commit()
    def sink(row):
        collector.observe(row)
        if row.get("boundary") == "begin_started": attempting.set()
    def contender():
        with observation.local_observer(sink, lambda: True):
            return run_sqlite_immediate(engine, lambda c: c.exec_driver_sql("INSERT INTO t VALUES (2)").rowcount,
                retry_policy=SqliteRetryPolicy(maximum_elapsed_seconds=2))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(holder); assert acquired.wait(5)
            second = pool.submit(contender); assert attempting.wait(5)
            release.set(); first.result(5); assert second.result(5) == 1
        result = collector.payload()
        assert result["completed_attempts"] == 1 and result["longest_hold_ms"] is not None
        assert any(row["acquire_ms"] is not None for row in result["attempts"])
    finally:
        release.set(); engine.dispose()


def test_broken_boundaries_remain_partial_and_unknown_instead_of_zero():
    collector = DbWriteCollector()
    feed(collector,"begin_started",10)
    feed(collector,"acquired",8)
    feed(collector,"committed",7)
    row=collector.payload()["attempts"][0]
    assert row["hold_ms"] is None and row["acquire_ms"] is None
    assert collector.payload()["coverage"] == "partial"
    collector.observe({"event":"sqlite","span_id":"broken","attempt":{},"monotonic_ns":5})
    collector.observe({"event":"sqlite","span_id":"broken","monotonic_ns":None})
    assert collector.payload()["longest_hold_ms"] is None


def test_two_requests_databases_and_global_observer_stay_independent(tmp_path):
    from contextlib import ExitStack
    engines=[create_engine("sqlite:///"+str(tmp_path/f"owner-{n}.sqlite"),connect_args={"check_same_thread":False}) for n in range(2)]
    collectors=[DbWriteCollector(),DbWriteCollector()]
    for n,(engine,collector) in enumerate(zip(engines,collectors)):
        with engine.begin() as c:c.exec_driver_sql("CREATE TABLE t(n INTEGER)")
        collector.bind(f"request-{n}",n+1)
    from threading import Barrier
    barrier=Barrier(2);global_events=[]
    remove=observation.install(global_events.append)
    def worker(n):
        with observation.local_observer(collectors[n].observe,lambda:True),observation.scope(chat_stage="admission"):
            def write(c):
                barrier.wait(timeout=5)
                return c.exec_driver_sql("INSERT INTO t VALUES (1)").rowcount
            return run_sqlite_immediate(engines[n],write)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool: assert list(pool.map(worker,range(2))) == [1,1]
        results=[collector.payload() for collector in collectors]
        assert [result["request_id"] for result in results]==["request-0","request-1"]
        assert all(result["completed_attempts"]==1 for result in results)
        assert results[0]["attempts"][0]["database_id"]!=results[1]["attempts"][0]["database_id"]
        assert len([e for e in global_events if e.get("boundary")=="committed"])==2
        assert "owner-" not in json.dumps(results)
    finally:
        remove()
        for engine in engines:engine.dispose()


def test_rollback_return_is_observed_without_an_extra_transaction(tmp_path):
    engine=create_engine("sqlite:///"+str(tmp_path/"rollback.sqlite"))
    with engine.begin() as c:c.exec_driver_sql("CREATE TABLE t(n INTEGER)")
    collector=DbWriteCollector()
    with Session(engine) as session,observation.local_observer(collector.observe,lambda:True),observation.scope(chat_stage="cancel_or_failure"),observe_session(session):
        session.execute(text("INSERT INTO t VALUES (1)"))
        finish_session(session,rollback=True)
        row=collector.payload()["attempts"][0]
        assert row["stage"]=="cancel_or_failure" and row["outcome"]=="rolled_back"
        assert row["rollback_ms"] is not None and row["hold_ms"] is None
        assert session.scalar(text("SELECT count(*) FROM t"))==0
    engine.dispose()


def test_nested_diagnostic_clock_failure_preserves_the_existing_commit(monkeypatch):
    from app.core import session_write_observation as session_observation
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE t(n INTEGER)")
    def broken_clock():
        raise RuntimeError("synthetic clock failure")
    monkeypatch.setattr(session_observation, "monotonic_ns", broken_clock)
    collector = DbWriteCollector()
    with Session(engine) as session, observation.local_observer(collector.observe, lambda: True), observe_session(session):
        with session_observation.session_child(session):
            session.execute(text("INSERT INTO t VALUES (1)"))
        finish_session(session)
        assert session.scalar(text("SELECT count(*) FROM t")) == 1
        assert collector.payload()["completed_attempts"] == 1
    engine.dispose()
