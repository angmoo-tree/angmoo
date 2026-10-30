"""Retry a complete, owned read after confirmed PostgreSQL aborts only."""
from threading import Event
from time import monotonic
from sqlalchemy.exc import DBAPIError
from app.core import work_observation as observation
from app.core.postgresql_concurrency import POSTGRES_UNIT_RETRY, retryable, sqlstate
from app.core.postgresql_deadline import read_deadline


def begin_owned_read(connection):
    """Configure a fresh, effect-free snapshot, never a business transaction.

    Separate search/validation snapshots are closed before publication. They
    require repeatable reads, not a position in the writers' serial order.
    READ ONLY enforces that boundary. The caller still revalidates delivered
    source versions/current permissions at the existing publication boundary.
    SET TRANSACTION is local and fails if a query has already taken a snapshot;
    neither the pooled connection's default nor business writes are changed.
    """
    connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')


def retry_read(operation, *, deadline, cancelled=None):
    """The callback must release its snapshot before raising and have no effects.

    A failed SELECT cannot be retried inside its aborted transaction. Every
    callback invocation must acquire a new transaction and rebuild validation
    state. The caller's existing deadline includes all attempts and backoff.
    """
    signal=cancelled if cancelled is not None else Event()
    delay=POSTGRES_UNIT_RETRY.initial_delay_seconds
    for attempt in range(1,POSTGRES_UNIT_RETRY.max_attempts+1):
        if signal.is_set() or monotonic()>=deadline:
            raise TimeoutError('postgresql_read_deadline')
        try:
            return operation()
        except DBAPIError as exc:
            if not retryable(exc):raise
            if signal.is_set() or monotonic()>=deadline:
                raise TimeoutError('postgresql_read_deadline') from exc
            if attempt==POSTGRES_UNIT_RETRY.max_attempts:raise
            observation.emit('postgresql_read_retry',attempt=attempt,sqlstate=sqlstate(exc))
            signal.wait(min(delay,max(0,deadline-monotonic())))
            delay=min(delay*2,POSTGRES_UNIT_RETRY.maximum_delay_seconds)


def read_transaction(engine, operation, *, deadline, cancelled=None):
    """Materialize the result before committing and returning the connection."""
    def attempt():
        with engine.begin() as connection:
            with read_deadline(connection,deadline,cancelled=cancelled):
                begin_owned_read(connection)
                connection.exec_driver_sql("SET LOCAL lock_timeout='50ms'")
                return operation(connection)
    return retry_read(attempt,deadline=deadline,cancelled=cancelled)
