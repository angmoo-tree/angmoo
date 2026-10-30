"""Bounded, replayable database work; provider and filesystem I/O stay outside."""
from functools import wraps
from inspect import signature
from sqlalchemy import Engine
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.core.postgresql_concurrency import POSTGRES_UNIT_RETRY


# One budget covers checkout, SQL and all retries. PRoot's query/validation cost
# needs more headroom than SQLite's 250 ms writer admission, without more workers
# or connections. A failed unit returns to its durable worker/lease for recovery.
def database_write(db, operation, *, postgres_isolation="SERIALIZABLE", **kwargs):
    """Re-read guards on every attempt; replay only a confirmed DB abort."""
    if db.get_bind().dialect.name == "postgresql":
        kwargs.setdefault("retry_policy", POSTGRES_UNIT_RETRY)
        if postgres_isolation != "SERIALIZABLE":
            from app.core.postgresql_concurrency import session_transact
            kwargs["retry_policy"] = kwargs["retry_policy"] or POSTGRES_UNIT_RETRY
            return session_transact(db, operation, isolation_level=postgres_isolation, **kwargs)
    return run_sqlite_session_immediate(db, operation, **kwargs)


def postgres_db_unit(operation):
    """One short DB-only decision, including its final DTO, before publication.

    Internal Session commits join the outer owner. Confirmed PostgreSQL aborts
    re-read every guard; uncertain commit and external I/O are never replayed.
    Apply only to synchronous DB-only entrypoints with a named db argument,
    or a service whose explicitly owned Session is self.db.
    """
    arguments = signature(operation)
    @wraps(operation)
    def run(*args, **kwargs):
        bound = arguments.bind(*args, **kwargs).arguments
        db = bound['db'] if 'db' in bound else bound['self'].db
        bind = db.get_bind()
        if bind.dialect.name != 'postgresql' or not isinstance(bind, Engine):
            return operation(*args, **kwargs)
        return database_write(db, lambda: operation(*args, **kwargs))
    return run
