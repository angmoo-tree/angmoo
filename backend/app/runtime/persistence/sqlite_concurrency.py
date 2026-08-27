"""SQLite-native bounded writer coordination for the canonical runtime."""

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

T = TypeVar("T")


class SqliteConcurrencyError(RuntimeError):
    reason_code = "sqlite_concurrency_error"


class SqliteBusyRetryExhausted(SqliteConcurrencyError):
    reason_code = "sqlite_busy_retry_exhausted"


class SqliteTaskQueueFull(SqliteConcurrencyError):
    reason_code = "sqlite_task_queue_full"


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
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    result = operation(connection)
                    connection.commit()
                    return result
                except BaseException:
                    connection.rollback()
                    raise
        except OperationalError as exc:
            if not _is_busy_error(exc):
                raise
            last_error = exc
        except sqlite3.OperationalError as exc:
            if not _is_busy_error(exc):
                raise
            last_error = exc
        elapsed = monotonic() - started
        if attempt >= policy.max_attempts or elapsed >= policy.maximum_elapsed_seconds:
            break
        remaining = policy.maximum_elapsed_seconds - elapsed
        sleep_for = min(delay, max(0.0, remaining))
        if sleep_for <= 0:
            break
        sleep(sleep_for)
        delay = min(
            max(delay * 2, policy.initial_delay_seconds), policy.maximum_delay_seconds
        )
    raise SqliteBusyRetryExhausted(
        f"SQLite writer remained busy after {policy.max_attempts} bounded attempts"
    ) from last_error


def run_sqlite_session_immediate(
    session: Session,
    operation: Callable[[], T],
    *,
    retry_policy: SqliteRetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
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
    policy = retry_policy or SqliteRetryPolicy()
    started = monotonic()
    delay = policy.initial_delay_seconds
    last_error: BaseException | None = None
    timeout_ms = max(1, int(policy.maximum_elapsed_seconds * 1000))

    for attempt in range(1, policy.max_attempts + 1):
        session.rollback()
        connection = session.connection()
        driver_connection = connection.connection.driver_connection
        cursor = driver_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout")
            previous_timeout_ms = int(cursor.fetchone()[0])
            cursor.execute(f"PRAGMA busy_timeout = {timeout_ms}")
        finally:
            cursor.close()
        try:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            result = operation()
            session.commit()
            return result
        except OperationalError as exc:
            session.rollback()
            if not _is_busy_error(exc):
                raise
            last_error = exc
        except sqlite3.OperationalError as exc:
            session.rollback()
            if not _is_busy_error(exc):
                raise
            last_error = exc
        except BaseException:
            session.rollback()
            raise
        finally:
            _set_busy_timeout(driver_connection, previous_timeout_ms)

        elapsed = monotonic() - started
        if attempt >= policy.max_attempts or elapsed >= policy.maximum_elapsed_seconds:
            break
        remaining = policy.maximum_elapsed_seconds - elapsed
        sleep_for = min(delay, max(0.0, remaining))
        if sleep_for <= 0:
            break
        sleep(sleep_for)
        delay = min(
            max(delay * 2, policy.initial_delay_seconds), policy.maximum_delay_seconds
        )

    raise SqliteBusyRetryExhausted(
        f"SQLite session writer remained busy after {policy.max_attempts} bounded attempts"
    ) from last_error


def _set_busy_timeout(driver_connection: object, timeout_ms: int) -> None:
    cursor = driver_connection.cursor()
    try:
        cursor.execute(f"PRAGMA busy_timeout = {max(0, timeout_ms)}")
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
