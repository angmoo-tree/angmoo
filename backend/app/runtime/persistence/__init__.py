"""Current and OFF-by-default embedded canonical persistence adapters."""

from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.core.sqlite_concurrency import (
    SqliteBoundedTaskQueue,
    SqliteRetryPolicy,
    run_sqlite_immediate,
)
from app.exceptions import (
    SqliteBusyRetryExhausted,
    SqliteConcurrencyError,
    SqliteTaskQueueFull,
)
from app.runtime.persistence.sqlite_database import (
    LocalAppDataRuntimeDataPath,
    SqliteCanonicalDatabase,
    SqliteCanonicalDoctor,
    SqliteCanonicalError,
    SqliteCanonicalSettings,
    SqliteSchemaMismatchError,
)
from app.runtime.persistence.sqlite_unit_of_work import SqliteUnitOfWork
from app.runtime.persistence.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


def __getattr__(name):
    # Reflection helpers are also imported in cold, historical migrations.
    # Resolve this ORM-backed adapter only when its public export is requested.
    if name == "SqliteSchedulerLeaseRepository":
        from app.runtime.persistence.sqlite_scheduler_lease import SqliteSchedulerLeaseRepository
        return SqliteSchedulerLeaseRepository
    raise AttributeError(name)

__all__ = [
    "LocalAppDataRuntimeDataPath",
    "SqlAlchemyUnitOfWork",
    "SqliteBoundedTaskQueue",
    "SqliteBusyRetryExhausted",
    "SqliteCanonicalDatabase",
    "SqliteCanonicalDoctor",
    "SqliteCanonicalError",
    "SqliteCanonicalSettings",
    "SqliteConcurrencyError",
    "SqliteRetryPolicy",
    "SqliteSchemaMismatchError",
    "SqliteSchedulerLeaseRepository",
    "SqliteTaskQueueFull",
    "SqliteUnitOfWork",
    "StaticRuntimeDataPath",
    "run_sqlite_immediate",
]
