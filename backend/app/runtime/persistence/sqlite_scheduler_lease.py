"""Bind the SQLite lease service to the existing engine and transaction executor."""

from __future__ import annotations
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
import logging
from sqlalchemy import Engine, select
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.runtime.service.sqlite_lease import SqliteSchedulerLeaseService
from app.domains.runtime.policies.lease import aware_utc
from app.core.sqlite_concurrency import SqliteRetryPolicy, run_sqlite_immediate, _get_busy_timeout, _set_busy_timeout
from app.runtime.persistence.lease_operation import current_lease_operation

logger = logging.getLogger(__name__)


Clock = Callable[[], datetime]


def read_installation_id(connection: Any):
    return connection.execute(
        select(InstallationIdentity.__table__.c.installation_id).where(
            InstallationIdentity.__table__.c.singleton_key == LOCAL_INSTALLATION_KEY
        )
    ).scalar_one_or_none()


class SqliteSchedulerLeaseRepository(SqliteSchedulerLeaseService):
    """Bind SQLite engine, bounded immediate transaction retry and clock to the lease workflow."""

    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        retry_policy: SqliteRetryPolicy | None = None,
    ) -> None:
        if engine.dialect.name != "sqlite":
            raise ValueError("SqliteSchedulerLeaseRepository requires SQLite")
        self._engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))
        self._retry_policy = retry_policy
        super().__init__(
            write=self._write,
            now=self._now,
            installation_reader=read_installation_id,
            reader=self._read_connection,
        )

    def _write(self, operation: Callable[[Any], Any]) -> Any:
        name = operation.__qualname__.split(".")[-3]
        context = current_lease_operation()

        def observe(facts: dict[str, Any]) -> None:
            if context is not None:
                context.record(facts)
            logger.info("scheduler_lease_transaction operation=%s operation_id=%s facts=%s",
                        name, context.operation_id if context else None, facts)

        return run_sqlite_immediate(
            self._engine, operation, retry_policy=self._retry_policy,
            deadline=context.deadline if context else None, observer=observe,
        )

    def _now(self) -> datetime:
        return aware_utc(self._clock())

    def _read_connection(self, operation: Callable[[Any], Any]) -> Any:
        with self._engine.connect() as connection:
            driver = connection.connection.driver_connection
            previous = _get_busy_timeout(driver)
            try:
                _set_busy_timeout(driver, 50)
                return operation(connection)
            finally:
                _set_busy_timeout(driver, previous)


__all__ = ["Clock", "SqliteSchedulerLeaseRepository"]
