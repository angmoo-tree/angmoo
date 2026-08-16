from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    event,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.core.db import Base
from app.domains.identity.public import InstallationIdentity, LOCAL_INSTALLATION_KEY
from app.domains.runtime.domain.scheduler_lease import (
    SCHEDULER_SINGLETON_KEY,
    SchedulerFenceRejectedError,
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
    SchedulerLeaseSnapshot,
    SchedulerLeaseState,
    SchedulerTickPermit,
    SchedulerTickResult,
    aware_utc,
    decide_tick_window,
)


class RuntimeSchedulerLease(Base):
    __tablename__ = "runtime_scheduler_leases"
    __table_args__ = (
        CheckConstraint(
            "singleton_key = 'resident-tick-scheduler'",
            name="ck_runtime_scheduler_leases_singleton",
        ),
        CheckConstraint(
            "state IN ('starting','active','draining','stopped','failed')",
            name="ck_runtime_scheduler_leases_state",
        ),
        CheckConstraint(
            "fencing_epoch >= 0",
            name="ck_runtime_scheduler_leases_fencing_epoch",
        ),
        CheckConstraint(
            "last_tick_result IS NULL OR last_tick_result IN "
            "('success','no_action','partial','failed','skipped')",
            name="ck_runtime_scheduler_leases_tick_result",
        ),
    )

    singleton_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    installation_id: Mapped[str] = mapped_column(
        ForeignKey("installation_identities.installation_id"),
        nullable=False,
        unique=True,
    )
    lease_owner_id: Mapped[str | None] = mapped_column(String(128))
    fencing_epoch: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stopped", server_default="stopped"
    )
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sleep_gap_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_tick_window_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tick_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tick_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tick_result: Mapped[str | None] = mapped_column(String(20))
    next_tick_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    shutdown_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


_SchedulerFence = tuple[str, int]
_scheduler_fence: ContextVar[_SchedulerFence | None] = ContextVar(
    "angmoo_scheduler_fence",
    default=None,
)


@contextmanager
def scheduler_fence(*, owner_id: str, fencing_epoch: int) -> Iterator[None]:
    token = _scheduler_fence.set((owner_id, fencing_epoch))
    try:
        yield
    finally:
        _scheduler_fence.reset(token)


@event.listens_for(Session, "before_commit")
def _verify_scheduler_fence_before_commit(db: Session) -> None:
    expected = _scheduler_fence.get()
    if expected is None:
        return
    owner_id, fencing_epoch = expected
    row = db.scalar(
        select(RuntimeSchedulerLease).where(
            RuntimeSchedulerLease.singleton_key == SCHEDULER_SINGLETON_KEY
        )
    )
    now = _database_now(db)
    if not _lease_matches(row, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now):
        raise SchedulerFenceRejectedError("scheduler lease fence rejected commit")


class SqlAlchemySchedulerLeaseRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def acquire(self, *, owner_id: str, ttl_seconds: int) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            _advisory_xact_lock(db)
            now = _database_now(db)
            installation = db.scalar(
                select(InstallationIdentity)
                .where(InstallationIdentity.singleton_key == LOCAL_INSTALLATION_KEY)
                .with_for_update()
            )
            if installation is None:
                db.rollback()
                raise SchedulerLeaseLostError("local installation identity is missing")
            row = db.scalar(
                select(RuntimeSchedulerLease)
                .where(RuntimeSchedulerLease.singleton_key == SCHEDULER_SINGLETON_KEY)
                .with_for_update()
            )
            if row is None:
                row = RuntimeSchedulerLease(
                    singleton_key=SCHEDULER_SINGLETON_KEY,
                    installation_id=installation.installation_id,
                    fencing_epoch=1,
                )
                db.add(row)
            elif (
                row.lease_owner_id not in {None, owner_id}
                and row.lease_expires_at is not None
                and aware_utc(row.lease_expires_at) > now
            ):
                db.rollback()
                raise SchedulerLeaseHeldError("scheduler lease is already held")
            elif row.lease_owner_id != owner_id:
                row.fencing_epoch += 1
            row.lease_owner_id = owner_id
            row.state = SchedulerLeaseState.ACTIVE.value
            row.acquired_at = now
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=ttl_seconds)
            row.last_observed_at = now
            row.next_tick_at = now
            row.last_error_code = None
            row.shutdown_requested_at = None
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def heartbeat(
        self, *, owner_id: str, fencing_epoch: int, ttl_seconds: int
    ) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            row, now = _locked_current_lease(
                db,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
            )
            previous_observed_at = row.last_observed_at
            row.last_sleep_gap_seconds = (
                max(
                    0,
                    int((now - aware_utc(previous_observed_at)).total_seconds()),
                )
                if previous_observed_at is not None
                else 0
            )
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=ttl_seconds)
            row.last_observed_at = now
            row.state = SchedulerLeaseState.ACTIVE.value
            row.last_error_code = None
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def begin_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        ttl_seconds: int,
        interval_seconds: int,
    ) -> SchedulerTickPermit:
        with self._session_factory() as db:
            row, now = _locked_current_lease(
                db,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
            )
            permit = decide_tick_window(
                now=now,
                interval_seconds=interval_seconds,
                last_tick_window_at=row.last_tick_window_at,
                last_observed_at=row.last_observed_at,
            )
            row.heartbeat_at = now
            row.lease_expires_at = now + timedelta(seconds=ttl_seconds)
            row.last_observed_at = now
            row.next_tick_at = permit.next_tick_at
            if permit.should_run:
                row.last_tick_window_at = permit.logical_window_at
                row.last_tick_started_at = now
                row.last_tick_finished_at = None
                row.last_tick_result = None
                row.last_error_code = None
            db.commit()
            return permit

    def finish_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        result: SchedulerTickResult,
        error_code: str | None = None,
    ) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            row, now = _locked_current_lease(
                db,
                owner_id=owner_id,
                fencing_epoch=fencing_epoch,
            )
            row.last_tick_finished_at = now
            row.last_tick_result = result.value
            row.last_error_code = error_code
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def release(
        self, *, owner_id: str, fencing_epoch: int
    ) -> SchedulerLeaseSnapshot:
        with self._session_factory() as db:
            _advisory_xact_lock(db)
            row = db.scalar(
                select(RuntimeSchedulerLease)
                .where(RuntimeSchedulerLease.singleton_key == SCHEDULER_SINGLETON_KEY)
                .with_for_update()
            )
            now = _database_now(db)
            if row is None or row.lease_owner_id != owner_id or row.fencing_epoch != fencing_epoch:
                db.rollback()
                raise SchedulerLeaseLostError("scheduler lease cannot be released")
            row.state = SchedulerLeaseState.STOPPED.value
            row.shutdown_requested_at = now
            row.heartbeat_at = now
            row.lease_expires_at = now
            row.lease_owner_id = None
            row.next_tick_at = None
            db.commit()
            db.refresh(row)
            return _snapshot(row)

    def read(self) -> SchedulerLeaseSnapshot | None:
        with self._session_factory() as db:
            row = db.get(RuntimeSchedulerLease, SCHEDULER_SINGLETON_KEY)
            return _snapshot(row) if row is not None else None


def _locked_current_lease(
    db: Session,
    *,
    owner_id: str,
    fencing_epoch: int,
) -> tuple[RuntimeSchedulerLease, datetime]:
    _advisory_xact_lock(db)
    row = db.scalar(
        select(RuntimeSchedulerLease)
        .where(RuntimeSchedulerLease.singleton_key == SCHEDULER_SINGLETON_KEY)
        .with_for_update()
    )
    now = _database_now(db)
    if not _lease_matches(row, owner_id=owner_id, fencing_epoch=fencing_epoch, now=now):
        db.rollback()
        raise SchedulerLeaseLostError("scheduler lease is no longer current")
    return row, now


def _lease_matches(
    row: RuntimeSchedulerLease | None,
    *,
    owner_id: str,
    fencing_epoch: int,
    now: datetime,
) -> bool:
    return bool(
        row is not None
        and row.lease_owner_id == owner_id
        and row.fencing_epoch == fencing_epoch
        and row.state == SchedulerLeaseState.ACTIVE.value
        and row.lease_expires_at is not None
        and aware_utc(row.lease_expires_at) > now
    )


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


def _snapshot(row: RuntimeSchedulerLease) -> SchedulerLeaseSnapshot:
    return SchedulerLeaseSnapshot(
        installation_id=row.installation_id,
        lease_owner_id=row.lease_owner_id,
        fencing_epoch=row.fencing_epoch,
        state=SchedulerLeaseState(row.state),
        acquired_at=row.acquired_at,
        heartbeat_at=row.heartbeat_at,
        lease_expires_at=row.lease_expires_at,
        last_tick_window_at=row.last_tick_window_at,
        last_tick_started_at=row.last_tick_started_at,
        last_tick_finished_at=row.last_tick_finished_at,
        last_tick_result=(
            SchedulerTickResult(row.last_tick_result) if row.last_tick_result else None
        ),
        next_tick_at=row.next_tick_at,
        last_error_code=row.last_error_code,
    )
