"""SQLite-native bounded writer coordination shared by canonical adapters."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import TypeVar

from sqlalchemy import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.exceptions import (
    SqliteBusyRetryExhausted,
    SqliteConcurrencyError,
    SqliteTaskQueueFull,
)

T = TypeVar("T")
SqliteWriteObserver = Callable[[dict[str, object]], None]


def _notify(observer: SqliteWriteObserver | None, **facts: object) -> None:
    if observer is not None:
        try:
            observer(facts)
        except Exception:
            pass  # A diagnostic sink must not change a committed write.


def sqlite_error_identity(exc: BaseException) -> tuple[int | None, str | None]:
    original = getattr(exc, "orig", exc)
    code = getattr(original, "sqlite_errorcode", None)
    name = getattr(original, "sqlite_errorname", None)
    return (code if isinstance(code, int) else None,
            name if isinstance(name, str) else None)


@dataclass(frozen=True)
class SqliteRetryPolicy:
    max_attempts: int = 4
    initial_delay_seconds: float = 0.01
    maximum_delay_seconds: float = 0.05
    maximum_elapsed_seconds: float = 0.25

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must not be negative")
        if self.maximum_delay_seconds < self.initial_delay_seconds:
            raise ValueError("maximum_delay_seconds is smaller than the initial delay")
        if self.maximum_elapsed_seconds <= 0:
            raise ValueError("maximum_elapsed_seconds must be positive")


def run_sqlite_immediate(
    engine: Engine,
    operation: Callable[[Connection], T],
    *,
    retry_policy: SqliteRetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    observer: SqliteWriteObserver | None = None,
) -> T:
    """Run one short writer transaction with bounded busy/locked retry.

    ``BEGIN IMMEDIATE`` reserves the single SQLite writer before any canonical
    state is read.  Domain adapters still use state-conditioned UPDATE clauses
    as their compare-and-swap fence; the transaction prevents read/modify/write
    interleaving while keeping the lock lifetime explicit and short.
    """

    if engine.dialect.name != "sqlite":
        raise SqliteConcurrencyError("SQLite writer received a non-SQLite engine")
    policy = retry_policy or SqliteRetryPolicy()
    started = monotonic()
    delay = policy.initial_delay_seconds
    last_error: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        attempt_started = monotonic()
        acquired_at: float | None = None
        try:
            with engine.connect() as connection:
                driver = connection.connection.driver_connection
                previous_timeout_ms = _get_busy_timeout(driver)
                remaining = max(0.001, policy.maximum_elapsed_seconds - (monotonic() - started))
                _set_busy_timeout(driver, max(1, min(50, int(remaining * 1000))))
                try:
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                    acquired_at = monotonic()
                    try:
                        result = operation(connection)
                        connection.commit()
                        _notify(observer, result="committed", attempt=attempt,
                                max_attempts=policy.max_attempts,
                                acquire_ms=round((acquired_at - attempt_started) * 1000, 3),
                                transaction_ms=round((monotonic() - acquired_at) * 1000, 3),
                                attempt_ms=round((monotonic() - attempt_started) * 1000, 3),
                                total_ms=round((monotonic() - started) * 1000, 3))
                        return result
                    except BaseException:
                        connection.rollback()
                        raise
                finally:
                    _set_busy_timeout(driver, previous_timeout_ms)
        except OperationalError as exc:
            if not _is_busy_error(exc):
                raise
            last_error = exc
            error_code, error_name = sqlite_error_identity(exc)
            _notify(observer, result="busy", attempt=attempt, sqlite_code=error_code,
                    sqlite_primary_code=error_code & 0xFF if error_code is not None else None,
                    sqlite_name=error_name, max_attempts=policy.max_attempts,
                    acquire_ms=round((monotonic() - attempt_started) * 1000, 3),
                    attempt_ms=round((monotonic() - attempt_started) * 1000, 3))
        except sqlite3.OperationalError as exc:
            if not _is_busy_error(exc):
                raise
            last_error = exc
            error_code, error_name = sqlite_error_identity(exc)
            _notify(observer, result="busy", attempt=attempt, sqlite_code=error_code,
                    sqlite_primary_code=error_code & 0xFF if error_code is not None else None,
                    sqlite_name=error_name, max_attempts=policy.max_attempts,
                    acquire_ms=round((monotonic() - attempt_started) * 1000, 3),
                    attempt_ms=round((monotonic() - attempt_started) * 1000, 3))
        elapsed = monotonic() - started
        if attempt >= policy.max_attempts or elapsed >= policy.maximum_elapsed_seconds:
            break
        remaining = policy.maximum_elapsed_seconds - elapsed
        sleep_for = min(delay, max(0.0, remaining))
        if sleep_for <= 0:
            break
        _notify(observer, result="retry_wait", attempt=attempt,
                retry_delay_ms=round(sleep_for * 1000, 3))
        sleep(sleep_for)
        delay = min(
            max(delay * 2, policy.initial_delay_seconds), policy.maximum_delay_seconds
        )
    error_code, error_name = sqlite_error_identity(last_error) if last_error else (None, None)
    _notify(observer, result="exhausted", attempt=attempt, sqlite_code=error_code,
            sqlite_primary_code=error_code & 0xFF if error_code is not None else None,
            sqlite_name=error_name, total_ms=round((monotonic() - started) * 1000, 3))
    exhausted = SqliteBusyRetryExhausted(
        f"SQLite writer remained busy after {attempt} bounded attempts"
    )
    exhausted.sqlite_errorcode, exhausted.sqlite_errorname = error_code, error_name
    raise exhausted from last_error


def run_sqlite_session_immediate(
    session: Session,
    operation: Callable[[], T],
    *,
    retry_policy: SqliteRetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    observer: SqliteWriteObserver | None = None,
    require_clean: bool = False,
) -> T:
    """Run a caller-owned ``Session`` as one bounded SQLite writer UoW.

    FastAPI owns the session lifetime, while the social application owns the
    commit boundary.  Any dependency reads are closed before ``BEGIN
    IMMEDIATE`` so validation, source rows, evidence, Inbox delivery and the
    idempotency ledger all observe one writer snapshot and commit together.

    The connection-wide busy timeout is temporarily bounded per attempt and
    restored before the connection returns to the pool.  This prevents the
    default five-second SQLite timeout from hiding the typed retry contract.
    """

    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        raise SqliteConcurrencyError("SQLite writer received a non-SQLite session")
    if require_clean and session.in_transaction():
        # A read transaction can be closed by the owner before entering here.
        # A flushed write is invisible to new/dirty/deleted, so those collections
        # are insufficient to prove that rollback is harmless.
        raise SqliteConcurrencyError("sqlite_writer_requires_clean_session")
    policy = retry_policy or SqliteRetryPolicy()
    started = monotonic()
    delay = policy.initial_delay_seconds
    last_error: BaseException | None = None
    for attempt in range(1, policy.max_attempts + 1):
        attempt_started = monotonic()
        session.rollback()
        connection = session.connection()
        driver_connection = connection.connection.driver_connection
        remaining = max(0.001, policy.maximum_elapsed_seconds - (monotonic() - started))
        timeout_ms = max(1, min(50, int(remaining * 1000)))
        previous_timeout_ms = _get_busy_timeout(driver_connection)
        _set_busy_timeout(driver_connection, timeout_ms)
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            acquired_at = monotonic()
            result = operation()
            _set_busy_timeout(driver_connection, previous_timeout_ms)
            session.commit()
            _notify(observer, result="committed", attempt=attempt,
                    max_attempts=policy.max_attempts,
                    acquire_ms=round((acquired_at - attempt_started) * 1000, 3),
                    transaction_ms=round((monotonic() - acquired_at) * 1000, 3),
                    attempt_ms=round((monotonic() - attempt_started) * 1000, 3),
                    total_ms=round((monotonic() - started) * 1000, 3))
            return result
        except OperationalError as exc:
            _set_busy_timeout(driver_connection, previous_timeout_ms)
            session.rollback()
            if not _is_busy_error(exc):
                raise
            last_error = exc
            error_code, error_name = sqlite_error_identity(exc)
            _notify(observer, result="busy", attempt=attempt, sqlite_code=error_code,
                    sqlite_primary_code=error_code & 0xFF if error_code is not None else None,
                    sqlite_name=error_name, max_attempts=policy.max_attempts,
                    acquire_ms=round((monotonic() - attempt_started) * 1000, 3),
                    attempt_ms=round((monotonic() - attempt_started) * 1000, 3))
        except sqlite3.OperationalError as exc:
            _set_busy_timeout(driver_connection, previous_timeout_ms)
            session.rollback()
            if not _is_busy_error(exc):
                raise
            last_error = exc
            error_code, error_name = sqlite_error_identity(exc)
            _notify(observer, result="busy", attempt=attempt, sqlite_code=error_code,
                    sqlite_primary_code=error_code & 0xFF if error_code is not None else None,
                    sqlite_name=error_name, max_attempts=policy.max_attempts,
                    acquire_ms=round((monotonic() - attempt_started) * 1000, 3),
                    attempt_ms=round((monotonic() - attempt_started) * 1000, 3))
        except BaseException:
            _set_busy_timeout(driver_connection, previous_timeout_ms)
            session.rollback()
            raise

        elapsed = monotonic() - started
        if attempt >= policy.max_attempts or elapsed >= policy.maximum_elapsed_seconds:
            break
        remaining = policy.maximum_elapsed_seconds - elapsed
        sleep_for = min(delay, max(0.0, remaining))
        if sleep_for <= 0:
            break
        _notify(observer, result="retry_wait", attempt=attempt,
                retry_delay_ms=round(sleep_for * 1000, 3))
        sleep(sleep_for)
        delay = min(
            max(delay * 2, policy.initial_delay_seconds), policy.maximum_delay_seconds
        )

    error_code, error_name = sqlite_error_identity(last_error) if last_error else (None, None)
    _notify(observer, result="exhausted", attempt=attempt, sqlite_code=error_code,
            sqlite_primary_code=error_code & 0xFF if error_code is not None else None,
            sqlite_name=error_name, total_ms=round((monotonic() - started) * 1000, 3))
    exhausted = SqliteBusyRetryExhausted(
        f"SQLite session writer remained busy after {attempt} bounded attempts"
    )
    exhausted.sqlite_errorcode, exhausted.sqlite_errorname = error_code, error_name
    raise exhausted from last_error


def _set_busy_timeout(driver_connection: object, timeout_ms: int) -> None:
    cursor = driver_connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout = {max(0, timeout_ms)}")
    finally:
        cursor.close()


def _get_busy_timeout(driver_connection: object) -> int:
    cursor = driver_connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout")
        return int(cursor.fetchone()[0])
    finally:
        cursor.close()


class SqliteBoundedTaskQueue:
    """One-process bounded executor used by the FastAPI runtime.

    The default is one writer thread.  Callers may reserve a small number of
    additional workers for read/CPU tasks, but database writer serialization
    continues to be enforced by ``run_sqlite_immediate``.
    """

    def __init__(self, *, max_workers: int = 1, capacity: int = 32) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        if capacity < max_workers:
            raise ValueError("capacity must be at least max_workers")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="angmoo-sqlite",
        )
        self._slots = BoundedSemaphore(capacity)
        self._closed = False

    def submit(
        self,
        operation: Callable[..., T],
        /,
        *args: object,
        **kwargs: object,
    ) -> Future[T]:
        if self._closed:
            raise RuntimeError("SQLite task queue is closed")
        if not self._slots.acquire(blocking=False):
            raise SqliteTaskQueueFull("SQLite task queue capacity is exhausted")
        try:
            future = self._executor.submit(operation, *args, **kwargs)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _future: self._slots.release())
        return future

    def close(self, *, wait: bool = True) -> None:
        self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def __enter__(self) -> SqliteBoundedTaskQueue:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def _is_busy_error(exc: BaseException) -> bool:
    code, _ = sqlite_error_identity(exc)
    if code is not None:
        return code & 0xFF == sqlite3.SQLITE_BUSY
    text = str(getattr(exc, "orig", exc)).lower()
    return "database is locked" in text or "database is busy" in text


__all__ = [
    "SqliteBoundedTaskQueue",
    "SqliteBusyRetryExhausted",
    "SqliteConcurrencyError",
    "SqliteRetryPolicy",
    "SqliteTaskQueueFull",
    "run_sqlite_immediate",
    "run_sqlite_session_immediate",
]
