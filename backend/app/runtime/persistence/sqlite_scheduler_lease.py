"""Bind the SQLite lease service to the existing engine and transaction executor."""

from __future__ import annotations
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import Engine, select
from app.domains.identity.public import InstallationIdentity, LOCAL_INSTALLATION_KEY
from app.domains.runtime.service.sqlite_lease import SqliteSchedulerLeaseService
from app.domains.runtime.policies.lease import aware_utc
from app.core.sqlite_concurrency import SqliteRetryPolicy, run_sqlite_immediate


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
        return run_sqlite_immediate(
            self._engine, operation, retry_policy=self._retry_policy
        )

    def _now(self) -> datetime:
        return aware_utc(self._clock())

    def _read_connection(self, operation: Callable[[Any], Any]) -> Any:
        with self._engine.connect() as connection:
            return operation(connection)


__all__ = ["Clock", "SqliteSchedulerLeaseRepository"]
