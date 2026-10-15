"""Actual WAL transactions, commit ownership and non-poison busy admission."""
import sqlite3
from threading import Event
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.core.sqlite_concurrency import (
    is_sqlite_busy, is_sqlite_contention, run_sqlite_session_immediate,
    SqliteRetryPolicy, SqliteBusyRetryExhausted, SqliteTaskQueueFull,
)


@pytest.mark.parametrize("mode", ["session", "connection"])
def test_cleanup_busy_after_commit_never_replays_committed_operation(wal_engine, monkeypatch, mode):
    from app.core import sqlite_concurrency as concurrency
    original = concurrency._set_busy_timeout
    calls = []
    def restore(driver, timeout):
        original(driver, timeout)
        if timeout == 5000:
            error = sqlite3.OperationalError("synthetic postcommit busy")
            error.sqlite_errorcode = sqlite3.SQLITE_BUSY
            raise error
    monkeypatch.setattr(concurrency, "_set_busy_timeout", restore)
    def write(connection):
        calls.append(1)
        connection.execute(text("INSERT INTO effects VALUES(1,'committed')"))
    with pytest.raises(concurrency.SqlitePostCommitError) as caught:
        if mode == "session":
            with Session(wal_engine) as db:
                concurrency.run_sqlite_session_immediate(db, lambda: write(db))
        else:
            concurrency.run_sqlite_immediate(wal_engine, write)
    assert calls == [1] and not is_sqlite_contention(caught.value)
    with wal_engine.connect() as db:
        assert db.exec_driver_sql("SELECT count(*) FROM effects").scalar_one() == 1


@pytest.fixture
def wal_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'writers.sqlite'}", pool_timeout=0.05)
    @event.listens_for(engine, "connect")
    def configure(driver, _):
        driver.execute("PRAGMA journal_mode=WAL").close()
        driver.execute("PRAGMA busy_timeout=5000").close()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE effects(id INTEGER PRIMARY KEY, value TEXT)")
    yield engine
    engine.dispose()


@pytest.mark.parametrize("code,expected", [(5, True), (261, True), (517, True), (6, False), (10, False), (1, False)])
def test_sqlite_extended_codes_are_not_message_classification(code, expected):
    error = sqlite3.OperationalError("database is locked")
    error.sqlite_errorcode = code
    assert is_sqlite_busy(error) is expected
    assert not is_sqlite_busy(RuntimeError("database is locked"))
    assert not is_sqlite_busy(SqliteTaskQueueFull())
    assert is_sqlite_contention(SqliteTaskQueueFull())


@pytest.mark.parametrize("fail", [False, True])
def test_timeout_stays_bounded_through_commit_or_rollback_and_restores_before_checkin(wal_engine, fail):
    observed, checkins = [], []
    def observe(connection):
        cursor = connection.connection.driver_connection.execute("PRAGMA busy_timeout")
        observed.append(cursor.fetchone()[0])
        cursor.close()
    event.listen(wal_engine, "commit", observe)
    event.listen(wal_engine, "rollback", observe)
    @event.listens_for(wal_engine, "checkin")
    def checked_in(driver, _):
        cursor = driver.execute("PRAGMA busy_timeout")
        checkins.append(cursor.fetchone()[0])
        cursor.close()
    def write(db):
        db.execute(text("INSERT INTO effects VALUES (1, 'atomic')"))
        if fail:
            raise ValueError("synthetic_invalid_data")
        return "written"
    with Session(wal_engine) as db:
        if fail:
            with pytest.raises(ValueError, match="synthetic_invalid_data"):
                run_sqlite_session_immediate(db, lambda: write(db), require_clean=True)
        else:
            assert run_sqlite_session_immediate(db, lambda: write(db), require_clean=True) == "written"
        assert db.bind is wal_engine and not db.in_transaction()
    assert observed and all(0 < timeout <= 50 for timeout in observed)
    assert checkins and all(timeout == 5000 for timeout in checkins)
    with wal_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM effects").scalar_one() == (0 if fail else 1)


def test_real_busy_exhaustion_keeps_work_and_fresh_retry_after_release(wal_engine):
    entered, release = Event(), Event()
    def holder():
        with wal_engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            entered.set()
            assert release.wait(5)
            connection.rollback()
    facts = []
    with ThreadPoolExecutor(max_workers=1) as worker:
        held = worker.submit(holder)
        assert entered.wait(5)
        try:
            with Session(wal_engine) as db:
                with pytest.raises(SqliteBusyRetryExhausted) as caught:
                    run_sqlite_session_immediate(db, lambda: db.execute(text("INSERT INTO effects VALUES (1,'once')")),
                        retry_policy=SqliteRetryPolicy(max_attempts=2), observer=facts.append)
                assert is_sqlite_busy(caught.value)
                assert not db.in_transaction()
                assert not any(fact["result"] == "committed" for fact in facts)
        finally:
            release.set()
        held.result(5)
    with Session(wal_engine) as db:
        run_sqlite_session_immediate(db, lambda: db.execute(text("INSERT INTO effects VALUES (1,'once')")))
    with wal_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM effects").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
