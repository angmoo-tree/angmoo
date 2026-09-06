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
