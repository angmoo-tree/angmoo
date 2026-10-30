"""Bind the scheduler workflow to the original Session factory and Identity row lock."""

from __future__ import annotations
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from app.domains.identity.models import InstallationIdentity
from app.domains.identity.constants import LOCAL_INSTALLATION_KEY
from app.domains.runtime.service.scheduler_lease import SchedulerLeaseService


def read_installation_identity(db: Session) -> Any:
    return db.scalar(
        select(InstallationIdentity)
        .where(InstallationIdentity.singleton_key == LOCAL_INSTALLATION_KEY)
        .with_for_update()
    )


class SqlAlchemySchedulerLeaseRepository(SchedulerLeaseService):
    """SQLAlchemy binding; lease decisions and state writes belong to the service."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__(
            session_factory, installation_reader=read_installation_identity
        )

    def _write(self, operation):
        with self._session_factory() as db:
            if db.get_bind().dialect.name != "postgresql":
                return super()._write(operation)
            from app.core.postgresql_concurrency import session_transact
            from app.core.sqlite_concurrency import SqliteRetryPolicy
            from app.runtime.persistence.lease_operation import current_lease_operation, LeaseOperation
            context = current_lease_operation() or LeaseOperation("direct", None)
            return session_transact(db, lambda: operation(db), require_clean=True,
                retry_policy=context.retry_policy or SqliteRetryPolicy(
                    max_attempts=12, maximum_elapsed_seconds=2.0,
                    initial_delay_seconds=.05, maximum_delay_seconds=.2),
                deadline=context.deadline, observer=context.record,
                retry_pool_checkout=True)
