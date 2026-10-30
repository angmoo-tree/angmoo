"""Bounded PostgreSQL transactions. Only confirmed aborts may be replayed.

Serializable isolation replaces SQLite's writer snapshot without a global
writer mutex. Existing conditional updates and unique constraints remain the
business owners of leases, claims, idempotency and accounting.
"""
from contextlib import contextmanager
import logging
import time
from sqlalchemy import Engine, event
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout
from app.core import work_observation as observation
from app.core.transaction_retry_policy import SqliteRetryPolicy
from app.exceptions import (SqliteBusyRetryExhausted, SqliteConcurrencyError,
    SqliteTaskQueueFull, SqliteWriteDeadlineExceeded)

log = logging.getLogger(__name__)

# PostgreSQL accounts for the whole DB unit, unlike SQLite's writer admission
# budget. Every legacy entrypoint must select this same bounded policy unless
# its owner supplies an explicit, narrower deadline (for example a lease).
POSTGRES_UNIT_RETRY = SqliteRetryPolicy(
    max_attempts=4, maximum_elapsed_seconds=5.0,
    initial_delay_seconds=0.02, maximum_delay_seconds=0.1,
)


class PostgresRetryExhausted(SqliteBusyRetryExhausted):
    reason_code = "postgresql_retry_exhausted"


class PostgresPoolExhausted(SqliteTaskQueueFull):
    reason_code = "postgresql_pool_checkout_timeout"


class PostgresDeadlineExceeded(SqliteWriteDeadlineExceeded):
    reason_code = "postgresql_write_deadline"


class PostgresCommitOutcomeUnknown(RuntimeError):
    reason_code = "postgresql_commit_outcome_unknown"


def sqlstate(exc):
    return getattr(getattr(exc, "orig", exc), "sqlstate", None)


def retryable(exc):
    return isinstance(exc, PostgresRetryExhausted) or sqlstate(exc) in {"40001", "40P01", "55P03"}


def connection_unavailable(exc):
    """Signal a durable worker to reconcile after an outage, never replay SQL.

    A disconnect can hide a committed effect. This is deliberately separate
    from retryable(): only an owner with durable claims/receipts may resume.
    Authentication, schema and integrity errors remain terminal diagnostics.
    """
    if not isinstance(exc, DBAPIError):
        return False
    original = exc.orig
    if type(original).__module__.split(".", 1)[0] not in {"psycopg", "psycopg2"}:
        return False
    code = sqlstate(exc)
    return (exc.connection_invalidated or code in {
        "08000", "08001", "08003", "08006", "57P01", "57P02", "57P03",
    } or (code is None and exc.statement is None
          and type(original).__name__ == "OperationalError"))


def track_writes(engine):
    """Track already-flushed/Core writes as well as ORM dirty collections."""
    @event.listens_for(engine, "begin")
    def begin(connection):
        connection.info["angmoo_transaction_written"] = False

    @event.listens_for(engine, "before_cursor_execute")
    def execute(connection, cursor, statement, parameters, context, executemany):
        compiled = getattr(context, "compiled", None)
        clause = getattr(compiled, "statement", None)
        if getattr(clause, "is_select", False):
            return
        if statement.lstrip().upper().startswith(("SET LOCAL ", "SET TRANSACTION ")):
            return
        # Raw SQL is conservative, including SELECT functions with effects.
        connection.info["angmoo_transaction_written"] = True


def require_read_only(session, error_code):
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(error_code)
    if session.in_transaction() and session.connection().info.get("angmoo_transaction_written", True):
        raise RuntimeError(error_code)


def _notify(observer, **facts):
    facts['boundary']={'retryable_abort':'failed'}.get(facts.get('result'),facts.get('result'))
    observation.emit("postgresql_attempt", **facts)
    if observer:
        try:
            observer(facts)
        except Exception:
            pass


def _limits(connection, remaining):
    milliseconds = max(1, int(remaining * 1000))
    connection.exec_driver_sql(f"SET LOCAL lock_timeout = '{min(50, milliseconds)}ms'")
    connection.exec_driver_sql(f"SET LOCAL statement_timeout = '{milliseconds}ms'")


def transact(engine, operation, *, retry_policy, sleep=time.sleep,
        monotonic=time.monotonic, observer=None, deadline=None, retry_pool_checkout=False,
        isolation_level="SERIALIZABLE"):
    # A narrower snapshot policy is allowed only for reviewed operations whose
    # invariants have explicit scope locks. The default and every existing
    # multi-scope writer retain SERIALIZABLE. Never accept READ COMMITTED here.
    if isolation_level not in {"SERIALIZABLE", "REPEATABLE READ"}:
        raise ValueError("postgresql_transaction_isolation_invalid")
    started = monotonic()
    end = min(started + retry_policy.maximum_elapsed_seconds, deadline or float("inf"))
    delay = retry_policy.initial_delay_seconds
    last = None
    phase = "admission"
    def expired(code, *, attempt, cause=None):
        elapsed_ms = round((monotonic() - started) * 1000, 2)
        state = sqlstate(cause) if cause is not None else None
        _notify(observer, result="deadline_exhausted", attempt=attempt, phase=phase,
            elapsed_ms=elapsed_ms, budget_ms=round((end-started)*1000, 2), sqlstate=state)
        # Content-free facts also survive when the optional recorder is off.
        log.warning("postgresql_transaction_deferred code=%s phase=%s attempt=%s elapsed_ms=%.2f sqlstate=%s",
            code, phase, attempt, elapsed_ms, state)
        error = PostgresDeadlineExceeded(code)
        error.phase, error.elapsed_ms, error.sqlstate = phase, elapsed_ms, state
        return error
    for attempt in range(1, retry_policy.max_attempts + 1):
        if monotonic() >= end:
            raise expired("postgresql_writer_execution_deadline", attempt=attempt, cause=last) from last
        committing = committed = False
        _notify(observer,result='begin_started',attempt=attempt)
        try:
            phase = "checkout"
            with engine.connect().execution_options(isolation_level=isolation_level) as connection:
                with connection.begin():
                    if monotonic() >= end:
                        raise PostgresDeadlineExceeded("postgresql_writer_execution_deadline")
                    phase = "configure"
                    _limits(connection, end - monotonic())
                    _notify(observer, result="acquired", attempt=attempt)
                    phase = "operation"
                    result = operation(connection)
                    if monotonic() >= end:
                        raise PostgresDeadlineExceeded("postgresql_writer_execution_deadline")
                    committing = True
                    phase = "commit"
                committed = True
            _notify(observer, result="committed", attempt=attempt)
            return result
        except PostgresDeadlineExceeded as exc:
            # The transaction context above has rolled back before we expose a
            # deferrable error. Nothing that may have committed is replayed here.
            raise expired("postgresql_writer_execution_deadline", attempt=attempt, cause=exc) from exc
        except PoolTimeout as exc:
            _notify(observer, result="pool_exhausted", attempt=attempt, phase=phase,
                elapsed_ms=round((monotonic()-started)*1000, 2))
            if not retry_pool_checkout or phase != "checkout":
                raise PostgresPoolExhausted("postgresql_pool_checkout_timeout") from exc
            # No connection was acquired and no operation ran. Lease control can
            # wait within its existing deadline without replaying any effect.
            last = exc
        except DBAPIError as exc:
            code = sqlstate(exc)
            # A lost connection at COMMIT can mean a successful durable write.
            # Never blindly replay it or a successfully committed cleanup error.
            if committed or (committing and (code is None or code.startswith("08"))):
                raise PostgresCommitOutcomeUnknown("reconcile_durable_receipt_before_retry") from exc
            if code == "57014":
                raise expired("postgresql_statement_cancelled", attempt=attempt, cause=exc) from exc
            if not retryable(exc):
                raise
            last = exc
            _notify(observer, result="retryable_abort", attempt=attempt, sqlstate=code)
        if attempt == retry_policy.max_attempts or monotonic() >= end:
            break
        sleep(min(delay, max(0, end - monotonic())))
        delay = min(max(delay * 2, retry_policy.initial_delay_seconds), retry_policy.maximum_delay_seconds)
    error = PostgresRetryExhausted("PostgreSQL transaction aborted after bounded retries")
    error.phase, error.elapsed_ms, error.sqlstate = phase, round((monotonic() - started) * 1000, 2), sqlstate(last)
    _notify(observer, result="retries_exhausted", attempt=attempt, phase=phase,
        elapsed_ms=error.elapsed_ms, sqlstate=error.sqlstate)
    log.warning("postgresql_transaction_deferred code=%s phase=%s attempt=%s elapsed_ms=%.2f sqlstate=%s",
        error.reason_code, phase, attempt, error.elapsed_ms, error.sqlstate)
    raise error from last


def session_transact(session, operation, *, retry_policy, require_clean=False, **kwargs):
    bind = session.get_bind()
    if not isinstance(bind, Engine):
        raise SqliteConcurrencyError("postgresql_writer_requires_engine_owned_session")
    if require_clean and session.in_transaction():
        raise SqliteConcurrencyError("postgresql_writer_requires_clean_session")
    require_read_only(session, "postgresql_writer_has_uncommitted_changes")
    session.rollback()
    original = session.bind
    def invoke(connection):
        session.bind = connection
        try:
            # Some caller-owned sessions use expire_on_commit=False. An abort at the
            # outer COMMIT must not reuse values accepted by the joined Session
            # on the previous attempt (especially leases and JSON ledgers).
            session.expire_all()
            result = operation()
            session.flush()
            # Session.commit commits its joined transaction, not the outer
            # Connection transaction. The outer owner alone publishes effects.
            session.commit()
            return result
        except BaseException:
            session.rollback()
            raise
        finally:
            session.bind = original
    try:
        return transact(bind, invoke, retry_policy=retry_policy, **kwargs)
    finally:
        session.bind = original


@contextmanager
def session_attempt(session):
    """Never replay a filesystem effect or provider request."""
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise SqliteConcurrencyError("postgresql_writer_requires_clean_session")
    original = session.bind
    with session.get_bind().connect().execution_options(isolation_level="SERIALIZABLE") as connection:
        with connection.begin():
            _limits(connection, 5.0)
            session.bind = connection
            try:
                yield session
                session.flush()
                session.commit()
            except BaseException:
                session.rollback()
                raise
            finally:
                session.bind = original
