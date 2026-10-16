"""SQLite-native bounded writer coordination shared by canonical adapters."""

from __future__ import annotations

import sqlite3
import time
import asyncio
import logging
from contextvars import copy_context
from uuid import uuid4
from app.core import work_observation as observation
from contextlib import contextmanager, nullcontext
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
from typing import TypeVar

from sqlalchemy import Connection, Engine
from sqlalchemy.exc import OperationalError, TimeoutError as PoolCheckoutTimeout
from sqlalchemy.orm import Session

from app.exceptions import (
    SqliteBusyRetryExhausted,
    SqliteConcurrencyError,
    SqliteTaskQueueFull,
)

T = TypeVar("T")
SqliteWriteObserver = Callable[[dict[str, object]], None]


class SqlitePostCommitError(RuntimeError):
    """A commit succeeded; cleanup failure must never replay its operation."""


def _notify(observer: SqliteWriteObserver | None, **facts: object) -> None:
    logging.getLogger(__name__).debug("sqlite_writer_attempt %s", facts)
    observation.emit("sqlite_attempt", **facts)
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


@observation.sqlite_observed
def run_sqlite_immediate(
    engine: Engine,
    operation: Callable[[Connection], T],
    *,
    retry_policy: SqliteRetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    observer: SqliteWriteObserver | None = None,
) -> T:
    """Run one short writer transaction with bounded SQLITE_BUSY retry.

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
        committed = False
        try:
            observation.emit("sqlite", boundary="checkout_started", attempt=attempt)
            with engine.connect() as connection:
                observation.emit("sqlite", boundary="checkout_complete", attempt=attempt)
                driver = connection.connection.driver_connection
                previous_timeout_ms = _get_busy_timeout(driver)
                remaining = max(0.001, policy.maximum_elapsed_seconds - (monotonic() - started))
                _set_busy_timeout(driver, max(1, min(50, int(remaining * 1000))))
                try:
                    observation.emit("sqlite", boundary="begin_started", attempt=attempt)
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                    acquired_at = monotonic()
                    observation.emit("sqlite", boundary="acquired", attempt=attempt)
                    try:
                        result = operation(connection)
                        observation.emit("sqlite", boundary="commit_started", attempt=attempt)
                        connection.commit()
                        committed = True
                        observation.emit("sqlite", boundary="committed", attempt=attempt)
                        _notify(observer, result="committed", attempt=attempt,
                                max_attempts=policy.max_attempts,
                                acquire_ms=round((acquired_at - attempt_started) * 1000, 3),
                                transaction_ms=round((monotonic() - acquired_at) * 1000, 3),
                                attempt_ms=round((monotonic() - attempt_started) * 1000, 3),
                                total_ms=round((monotonic() - started) * 1000, 3))
                        return result
                    except BaseException:
                        connection.rollback()
                        observation.emit("sqlite", boundary="rolled_back", attempt=attempt)
                        raise
                finally:
                    # BEGIN may fail after SQLAlchemy has opened its transaction.
                    # Keep the bounded timeout through rollback, too.
                    connection.rollback()
                    _set_busy_timeout(driver, previous_timeout_ms)
        except PoolCheckoutTimeout as exc:
            raise SqliteTaskQueueFull("sqlite_connection_checkout_deadline") from exc
        except OperationalError as exc:
            if committed:
                raise SqlitePostCommitError("sqlite_cleanup_failed_after_commit") from exc
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
            if committed:
                raise SqlitePostCommitError("sqlite_cleanup_failed_after_commit") from exc
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


@observation.sqlite_observed
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
        acquired_at: float | None = None
        session.rollback()
        committed = False
        try:
            # Pin the Connection until AFTER Session commit/rollback and timeout
            # restoration. A Session bound directly to an Engine otherwise returns
            # the DBAPI connection to the pool from commit(), before our finally.
            observation.emit("sqlite", boundary="checkout_started", attempt=attempt)
            owner = bind.connect() if isinstance(bind, Engine) else nullcontext(bind)
            with owner as connection:
                observation.emit("sqlite", boundary="checkout_complete", attempt=attempt)
                original_bind = session.bind
                driver_connection = connection.connection.driver_connection
                previous_timeout_ms = _get_busy_timeout(driver_connection)
                session.bind = connection
                try:
                    remaining = max(0.001, policy.maximum_elapsed_seconds - (monotonic() - started))
                    _set_busy_timeout(driver_connection, max(1, min(50, int(remaining * 1000))))
                    observation.emit("sqlite", boundary="begin_started", attempt=attempt)
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                    acquired_at = monotonic()
                    observation.emit("sqlite", boundary="acquired", attempt=attempt)
                    result = operation()
                    observation.emit("sqlite", boundary="commit_started", attempt=attempt)
                    session.commit()
                    committed = True
                    committed_at = monotonic()
                    observation.emit("sqlite", boundary="committed", attempt=attempt)
                finally:
                    try:
                        session.rollback()
                        if not committed and acquired_at is not None:
                            observation.emit("sqlite", boundary="rolled_back", attempt=attempt)
                    finally:
                        try:
                            _set_busy_timeout(driver_connection, previous_timeout_ms)
                        finally:
                            session.bind = original_bind
            _notify(observer, result="committed", attempt=attempt,
                    max_attempts=policy.max_attempts,
                    acquire_ms=round((acquired_at - attempt_started) * 1000, 3),
                    transaction_ms=round((committed_at - acquired_at) * 1000, 3),
                    attempt_ms=round((monotonic() - attempt_started) * 1000, 3),
                    total_ms=round((monotonic() - started) * 1000, 3))
            return result
        except PoolCheckoutTimeout as exc:
            raise SqliteTaskQueueFull("sqlite_connection_checkout_deadline") from exc
        except (OperationalError, sqlite3.OperationalError) as exc:
            if committed:
                raise SqlitePostCommitError("sqlite_cleanup_failed_after_commit") from exc
            if not _is_busy_error(exc):
                raise
            last_error = exc
            error_code, error_name = sqlite_error_identity(exc)
            _notify(observer, result="busy", attempt=attempt, sqlite_code=error_code,
                    sqlite_primary_code=error_code & 0xFF if error_code is not None else None,
                    sqlite_name=error_name, max_attempts=policy.max_attempts,
                    stage="acquire" if acquired_at is None else "transaction",
                    transaction_ms=None if acquired_at is None else round((monotonic() - acquired_at) * 1000, 3),
                    acquire_ms=round(((acquired_at or monotonic()) - attempt_started) * 1000, 3),
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
        f"SQLite session writer remained busy after {attempt} bounded attempts"
    )
    exhausted.sqlite_errorcode, exhausted.sqlite_errorname = error_code, error_name
    raise exhausted from last_error


@contextmanager
def sqlite_session_attempt(session: Session):
    """One non-replaying writer for a short fenced filesystem effect.

    An external effect cannot be rolled back by SQLite. The durable owner must
    reconcile its journal after an exception; this context NEVER retries it.
    """
    if session.in_transaction():
        raise SqliteConcurrencyError("sqlite_writer_requires_clean_session")
    bind = session.get_bind()
    if bind.dialect.name != "sqlite":
        raise SqliteConcurrencyError("SQLite writer received a non-SQLite session")
    with observation.span("sqlite_writer", database_id=observation.database_id(bind.engine.url.database), writer="sqlite_session_attempt"):
        observation.emit("sqlite", boundary="checkout_started")
        owner = bind.connect() if isinstance(bind, Engine) else nullcontext(bind)
        with owner as connection:
            observation.emit("sqlite", boundary="checkout_complete")
            original_bind = session.bind
            driver = connection.connection.driver_connection
            previous = _get_busy_timeout(driver)
            session.bind = connection
            try:
                _set_busy_timeout(driver, 50)
                observation.emit("sqlite", boundary="begin_started")
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                observation.emit("sqlite", boundary="acquired")
                yield session
                observation.emit("sqlite", boundary="commit_started")
                session.commit()
                observation.emit("sqlite", boundary="committed")
            finally:
                try:
                    was_active = session.in_transaction()
                    session.rollback()
                    if was_active:
                        observation.emit("sqlite", boundary="rolled_back")
                finally:
                    try:
                        _set_busy_timeout(driver, previous)
                    finally:
                        session.bind = original_bind
        observation.emit("sqlite", boundary="cleanup_complete")


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
        self._observation_id = uuid4().hex

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
            observation.emit("queue", boundary="rejected", queue_id=self._observation_id, reason="capacity_exhausted")
            raise SqliteTaskQueueFull("SQLite task queue capacity is exhausted")
        try:
            if observation.enabled():
                context = copy_context()
                task_id = uuid4().hex
                label = f"{getattr(operation, '__module__', 'unknown')}.{getattr(operation, '__qualname__', type(operation).__name__)}".replace("<", "").replace(">", "")
                observation.emit("queue", boundary="submit", queue_id=self._observation_id, task_id=task_id, operation=label)
                def invoke():
                    with observation.scope(queue_id=self._observation_id, task_id=task_id):
                        observation.emit("queue", boundary="start", operation=label)
                        try:
                            return operation(*args, **kwargs)
                        finally:
                            observation.emit("queue", boundary="end", operation=label)
                future = self._executor.submit(context.run, invoke)
                def cancelled(done):
                    if done.cancelled():
                        context.run(observation.emit, "queue", boundary="cancelled", queue_id=self._observation_id, task_id=task_id, operation=label)
                future.add_done_callback(cancelled)
            else:
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


def _consume_async_work(waiter):
    if not waiter.cancelled():
        waiter.exception()


class SqliteAsyncTaskQueue:
    """Own bounded synchronous work until completion, including cancellation.

    Operations must open and close their own Sessions inside the worker. No
    request Session or ORM entity may cross this execution boundary.
    """

    def __init__(self, *, capacity=2, closed_code="sqlite_async_worker_closed"):
        self._queue = SqliteBoundedTaskQueue(max_workers=1, capacity=capacity)
        self._lock = Lock()
        self._futures = set()
        self.closed = False
        self._closed_code = closed_code

    async def call(self, operation, *args, **kwargs):
        if self.closed:
            raise RuntimeError(self._closed_code)
        future = self._queue.submit(operation, *args, **kwargs)
        with self._lock:
            self._futures.add(future)
        def complete(done):
            with self._lock:
                self._futures.discard(done)
            if not done.cancelled():
                done.exception()
        future.add_done_callback(complete)
        waiter = asyncio.wrap_future(future)
        waiter.add_done_callback(_consume_async_work)
        try:
            return await asyncio.shield(waiter)
        except asyncio.CancelledError:
            future.cancel()  # Running work remains owned; queued work can stop.
            raise

    async def drain(self):
        with self._lock:
            pending = tuple(self._futures)
        waiters = [asyncio.wrap_future(future) for future in pending]
        for waiter in waiters:
            waiter.add_done_callback(_consume_async_work)
        if waiters:
            await asyncio.wait(waiters)

    def close(self):
        self.closed = True
        self._queue.close(wait=False)


def _is_busy_error(exc: BaseException) -> bool:
    """Compatibility name for existing callers; new code uses is_sqlite_busy."""
    return is_sqlite_busy(exc)


def is_sqlite_busy(exc: BaseException) -> bool:
    """Only SQLite BUSY (including SNAPSHOT), never LOCKED or generic SQL errors."""
    if isinstance(exc, SqliteBusyRetryExhausted):
        return True
    code, _ = sqlite_error_identity(exc)
    if code is not None:
        return code & 0xFF == sqlite3.SQLITE_BUSY
    original = getattr(exc, "orig", exc)
    # Only the legacy SQLite driver messages are a fallback. SQLITE_LOCKED and
    # unrelated exceptions containing these words must never trigger a retry.
    return isinstance(original, sqlite3.OperationalError) and str(original).lower().strip() in {
        "database is locked", "database is busy",
    }


def is_sqlite_contention(exc: BaseException) -> bool:
    """Retryable canonical admission; saturation stays distinct from DB BUSY."""
    return isinstance(exc, (SqliteTaskQueueFull, PoolCheckoutTimeout)) or is_sqlite_busy(exc)


__all__ = [
    "SqliteAsyncTaskQueue",
    "SqliteBoundedTaskQueue",
    "SqliteBusyRetryExhausted",
    "SqliteConcurrencyError",
    "SqliteRetryPolicy",
    "SqliteTaskQueueFull",
    "SqlitePostCommitError",
    "run_sqlite_immediate",
    "run_sqlite_session_immediate",
    "sqlite_error_identity",
    "is_sqlite_busy",
    "is_sqlite_contention",
    "sqlite_session_attempt",
]
