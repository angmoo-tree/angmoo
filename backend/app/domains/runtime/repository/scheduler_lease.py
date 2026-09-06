"""Original lease queries, database clock and PostgreSQL transaction lock."""

from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from app.domains.runtime.constants import SCHEDULER_SINGLETON_KEY
from app.domains.runtime.exceptions import SchedulerLeaseLostError
from app.domains.runtime.models import RuntimeSchedulerLease
from app.domains.runtime.policies.lease import aware_utc


def _database_now(db: Session) -> datetime:
    value: Any = db.scalar(select(func.current_timestamp()))
    if not isinstance(value, datetime):
        raise SchedulerLeaseLostError("database clock is unavailable")
    return aware_utc(value)


def _advisory_xact_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": "angmoo:runtime-scheduler-lease"},
        )


def locked_row(db: Session) -> RuntimeSchedulerLease | None:
    return db.scalar(
        select(RuntimeSchedulerLease)
        .where(RuntimeSchedulerLease.singleton_key == SCHEDULER_SINGLETON_KEY)
        .with_for_update()
    )


def fence_row(db: Session) -> RuntimeSchedulerLease | None:
    return db.scalar(
        select(RuntimeSchedulerLease).where(
            RuntimeSchedulerLease.singleton_key == SCHEDULER_SINGLETON_KEY
        )
    )


def read_row(db: Session) -> RuntimeSchedulerLease | None:
    return db.get(RuntimeSchedulerLease, SCHEDULER_SINGLETON_KEY)
