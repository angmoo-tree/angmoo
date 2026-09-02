"""Leased, same-scope serialized Memory maintenance queue."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.memory.domain.errors import MemoryConflictError, MemoryNotFoundError
from app.domains.memory.domain.lifecycle import as_utc
from app.domains.memory.domain.provenance import MemoryJobStatus
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryMaintenanceJob,
    MemoryScopeSettingModel,
)
from app.domains.memory.ports.maintenance_queue import MemoryMaintenanceWorkItem


class SqlAlchemyMemoryMaintenanceQueue:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        *,
        scope_setting_id: str,
        reason: str,
        idempotency_key: str,
    ) -> str:
        normalized_reason = _bounded(reason, "memory_job_reason_invalid")
        normalized_key = _bounded(
            idempotency_key,
            "memory_job_idempotency_invalid",
            maximum=160,
        )
        scope = self._session.scalar(
            select(MemoryScopeSettingModel)
            .where(MemoryScopeSettingModel.id == scope_setting_id)
            .with_for_update()
        )
        if scope is None:
            raise MemoryNotFoundError("memory_scope_not_found")
        existing = self._session.scalar(
            select(MemoryMaintenanceJob).where(
                MemoryMaintenanceJob.scope_setting_id == scope_setting_id,
                MemoryMaintenanceJob.idempotency_key == normalized_key,
            )
        )
        if existing is not None:
            if existing.reason != normalized_reason:
                raise MemoryConflictError("memory_job_replay_conflict")
            return existing.id
        row = MemoryMaintenanceJob(
            id=str(uuid4()),
            scope_setting_id=scope_setting_id,
            reason=normalized_reason,
            idempotency_key=normalized_key,
            status=MemoryJobStatus.PENDING.value,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            existing = self._session.scalar(
                select(MemoryMaintenanceJob).where(
                    MemoryMaintenanceJob.scope_setting_id == scope_setting_id,
                    MemoryMaintenanceJob.idempotency_key == normalized_key,
                )
            )
            if existing is None:
                raise MemoryConflictError("memory_job_enqueue_conflict") from None
            if existing.reason != normalized_reason:
                raise MemoryConflictError("memory_job_replay_conflict") from None
            return existing.id
        return row.id

    def claim(
        self,
        *,
        lease_token: str,
        now: datetime,
        lease_for: timedelta,
    ) -> MemoryMaintenanceWorkItem | None:
        token = _bounded(lease_token, "memory_job_lease_invalid", maximum=64)
        if lease_for <= timedelta(0) or lease_for > timedelta(minutes=30):
            raise MemoryConflictError("memory_job_lease_duration_invalid")
        candidates = list(
            self._session.execute(
                select(
                    MemoryMaintenanceJob.id,
                    MemoryMaintenanceJob.scope_setting_id,
                )
                .where(
                    or_(
                        MemoryMaintenanceJob.status == MemoryJobStatus.PENDING.value,
                        (
                            MemoryMaintenanceJob.status == MemoryJobStatus.RUNNING.value
                        )
                        & (MemoryMaintenanceJob.lease_expires_at <= now),
                    )
                )
                .order_by(MemoryMaintenanceJob.created_at, MemoryMaintenanceJob.id)
                .limit(50)
            )
        )
        for job_id, scope_setting_id in candidates:
            scope = self._session.scalar(
                select(MemoryScopeSettingModel)
                .where(MemoryScopeSettingModel.id == scope_setting_id)
                .with_for_update()
            )
            if scope is None:
                continue
            row = self._session.scalar(
                select(MemoryMaintenanceJob)
                .where(MemoryMaintenanceJob.id == job_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if row is None or not _claimable(row, now=now):
                continue
            another_running = self._session.scalar(
                select(MemoryMaintenanceJob.id).where(
                    MemoryMaintenanceJob.scope_setting_id == row.scope_setting_id,
                    MemoryMaintenanceJob.status == MemoryJobStatus.RUNNING.value,
                    MemoryMaintenanceJob.lease_expires_at > now,
                    MemoryMaintenanceJob.id != row.id,
                )
            )
            if another_running is not None:
                continue
            row.status = MemoryJobStatus.RUNNING.value
            row.lease_token = token
            row.lease_expires_at = now + lease_for
            row.attempt_count += 1
            row.started_at = row.started_at or now
            row.completed_at = None
            self._session.flush()
            return MemoryMaintenanceWorkItem(
                job_id=row.id,
                scope_setting_id=row.scope_setting_id,
                reason=row.reason,
                attempt_count=row.attempt_count,
            )
        return None

    def complete(
        self,
        *,
        job_id: str,
        lease_token: str,
        now: datetime,
    ) -> None:
        row = self._leased_job(
            job_id=job_id,
            lease_token=lease_token,
            now=now,
        )
        row.status = MemoryJobStatus.SUCCEEDED.value
        row.lease_token = None
        row.lease_expires_at = None
        row.last_error_code = None
        row.completed_at = now
        self._session.flush()

    def renew(
        self,
        *,
        job_id: str,
        lease_token: str,
        now: datetime,
        lease_for: timedelta,
    ) -> None:
        if lease_for <= timedelta(0) or lease_for > timedelta(minutes=30):
            raise MemoryConflictError("memory_job_lease_duration_invalid")
        row = self._leased_job(
            job_id=job_id,
            lease_token=lease_token,
            now=now,
        )
        row.lease_expires_at = now + lease_for
        self._session.flush()

    def fail(
        self,
        *,
        job_id: str,
        lease_token: str,
        error_code: str,
        retryable: bool,
        now: datetime,
    ) -> None:
        row = self._leased_job(
            job_id=job_id,
            lease_token=lease_token,
            now=now,
        )
        row.last_error_code = _bounded(error_code, "memory_job_error_invalid")
        row.lease_token = None
        row.lease_expires_at = None
        if retryable:
            row.status = MemoryJobStatus.PENDING.value
            row.started_at = None
            row.completed_at = None
        else:
            row.status = MemoryJobStatus.FAILED.value
            row.completed_at = now
        self._session.flush()

    def _leased_job(
        self,
        *,
        job_id: str,
        lease_token: str,
        now: datetime,
    ) -> MemoryMaintenanceJob:
        row = self._session.scalar(
            select(MemoryMaintenanceJob)
            .where(MemoryMaintenanceJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            row is None
            or row.status != MemoryJobStatus.RUNNING.value
            or row.lease_token != lease_token
            or row.lease_expires_at is None
            or as_utc(row.lease_expires_at) <= as_utc(now)
        ):
            raise MemoryConflictError("memory_job_lease_conflict")
        return row


def _claimable(row: MemoryMaintenanceJob, *, now: datetime) -> bool:
    if row.status == MemoryJobStatus.PENDING.value:
        return True
    return (
        row.status == MemoryJobStatus.RUNNING.value
        and row.lease_expires_at is not None
        and as_utc(row.lease_expires_at) <= as_utc(now)
    )


def _bounded(value: str, code: str, *, maximum: int = 80) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise MemoryConflictError(code)
    return normalized


__all__ = ["SqlAlchemyMemoryMaintenanceQueue"]
