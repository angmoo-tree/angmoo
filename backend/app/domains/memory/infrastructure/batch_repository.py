"""SQLite-backed v2 lane on Memory's existing leased maintenance queue."""

from datetime import UTC, date, datetime
import hashlib
import json
from uuid import uuid4

from sqlalchemy import case, exists, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.db import Base
from app.domains.memory.domain.batch_policy import (
    MEMORY_CONSENT_VERSION,
    MAX_BATCH_ATTEMPTS,
    next_daily_slot,
    retry_delay,
    schedule_time,
    schedule_timezone,
)
from app.domains.memory.domain.consolidation import MAINTENANCE_LEASE_DURATION
from app.domains.memory.domain.errors import (
    MemoryConflictError,
    MemoryDomainError,
    MemoryValidationError,
)
from app.domains.memory.domain.lifecycle import as_utc, normalize_memory_idempotency_key
from app.domains.memory.domain.scope import MemoryScope
from app.domains.memory.infrastructure.batch_models import (
    MemoryBatchProfile,
    MemoryBatchSetting,
    MemoryBatchRun,
    MemorySelectionDecisionModel,
    MemorySourceDelivery,
)
from app.domains.memory.infrastructure.maintenance_queue import (
    SqlAlchemyMemoryMaintenanceQueue,
)
from app.domains.memory.infrastructure.repository import SqlAlchemyMemoryRepository
from app.domains.memory.infrastructure.sqlalchemy_models import (
    MemoryCandidate,
    MemoryMaintenanceJob,
    MemoryScopeSettingModel,
)
from app.domains.memory.ports.batch import MemoryBatchSettings, MemorySelectionBatch


class SqlAlchemyMemoryBatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.memory = SqlAlchemyMemoryRepository(session)
        self.queue = SqlAlchemyMemoryMaintenanceQueue(session)

    def timezone(self, scope: MemoryScope) -> str:
        self.memory.validate_scope(scope)
        worlds = Base.metadata.tables["worlds"]
        zone = self.session.scalar(
            select(worlds.c.timezone).where(worlds.c.id == scope.world_id)
        )
        schedule_timezone(zone)
        return zone

    def settings(self, scope: MemoryScope) -> MemoryBatchSettings:
        zone = self.timezone(scope)
        setting = self.memory.get_scope_setting(scope)
        profile = self.session.get(MemoryBatchProfile, scope.owner_id)
        config = (
            None
            if setting is None
            else self.session.get(MemoryBatchSetting, setting.id)
        )
        enabled = setting is not None and setting.enabled
        pending = (
            0
            if setting is None
            else int(
                self.session.scalar(
                    select(func.count())
                    .select_from(MemoryCandidate)
                    .where(
                        MemoryCandidate.scope_setting_id == setting.id,
                        MemoryCandidate.status == "pending",
                    )
                )
                or 0
            )
        )
        state, last_code = "disabled", None
        last_completed_at = (
            None
            if setting is None
            else self.session.scalar(
                select(func.max(MemoryMaintenanceJob.completed_at))
                .join(MemoryBatchRun, MemoryBatchRun.job_id == MemoryMaintenanceJob.id)
                .where(
                    MemoryBatchRun.scope_setting_id == setting.id,
                    MemoryMaintenanceJob.status == "succeeded",
                )
            )
        )
        if config is not None and config.ai_enabled:
            state = "paused" if not enabled else "waiting"
            assigned = exists(
                select(MemorySourceDelivery.sequence).where(
                    MemorySourceDelivery.batch_job_id == MemoryBatchRun.job_id,
                    MemorySourceDelivery.candidate_id.is_not(None),
                )
            )
            latest = self.session.execute(
                select(MemoryMaintenanceJob.status, MemoryBatchRun.last_code)
                .join(MemoryBatchRun, MemoryBatchRun.job_id == MemoryMaintenanceJob.id)
                .where(
                    MemoryBatchRun.scope_setting_id == setting.id,
                    or_(MemoryMaintenanceJob.status != "failed", assigned),
                )
                .order_by(
                    case(
                        (MemoryMaintenanceJob.status == "running", 0),
                        (MemoryMaintenanceJob.status == "failed", 1),
                        (MemoryMaintenanceJob.status == "pending", 2),
                        else_=3,
                    ),
                    MemoryMaintenanceJob.created_at.desc(),
                    MemoryMaintenanceJob.id.desc(),
                )
                .limit(1)
            ).first()
            if latest is not None:
                job_state, last_code = latest
                if enabled:
                    state = {
                        "running": "running",
                        "pending": "pending",
                        "failed": "attention",
                        "succeeded": "completed",
                        "cancelled": "paused",
                    }.get(job_state, "waiting")
        return MemoryBatchSettings(
            version=0 if config is None else config.version,
            memory_enabled=enabled,
            ai_enabled=False if config is None else config.ai_enabled,
            shutdown_enabled=True if config is None else config.shutdown_enabled,
            schedule_enabled=False if config is None else config.schedule_enabled,
            local_time="22:30" if config is None else config.local_time,
            timezone=zone,
            next_due_at=None
            if config is None
            or not enabled
            or not config.ai_enabled
            or not config.schedule_enabled
            else config.next_due_at,
            model_id=None if profile is None else profile.model_id,
            profile_version=0 if profile is None else profile.version,
            pending_count=pending,
            status=state,
            last_code=last_code,
            last_completed_at=last_completed_at,
        )

    def save_settings(
        self,
        scope: MemoryScope,
        *,
        expected_version: int,
        expected_profile_version: int,
        ai_enabled: bool,
        shutdown_enabled: bool,
        schedule_enabled: bool,
        local_time: str,
        consent_version: str | None,
        model_id: str | None,
        idempotency_key: str,
        now: datetime,
    ) -> MemoryBatchSettings:
        zone = self.timezone(scope)
        schedule_time(local_time)
        normalize_memory_idempotency_key(idempotency_key)
        if ai_enabled and (consent_version != MEMORY_CONSENT_VERSION or not model_id):
            raise MemoryValidationError("memory_selection_consent_required")
        if model_id is not None and (
            not isinstance(model_id, str) or not 1 <= len(model_id) <= 120
        ):
            raise MemoryValidationError("memory_selection_model_invalid")
        setting = self.memory.get_or_create_scope_setting(scope)
        current = self.session.get(MemoryBatchSetting, setting.id)
        profile = self.session.get(MemoryBatchProfile, scope.owner_id)
        digest = hashlib.sha256(
            json.dumps(
                [
                    ai_enabled,
                    shutdown_enabled,
                    schedule_enabled,
                    local_time,
                    consent_version,
                    model_id,
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if current is not None and current.last_request_key == idempotency_key:
            if current.last_request_digest != digest:
                raise MemoryConflictError("memory_batch_replay_conflict")
            return self.settings(scope)
        if expected_version != (
            0 if current is None else current.version
        ) or expected_profile_version != (0 if profile is None else profile.version):
            raise MemoryConflictError("memory_batch_settings_version_conflict")
        if current is None:
            current = MemoryBatchSetting(
                scope_setting_id=setting.id, timezone=zone, version=1
            )
            self.session.add(current)
        else:
            changed = self.session.execute(
                update(MemoryBatchSetting)
                .where(
                    MemoryBatchSetting.scope_setting_id == setting.id,
                    MemoryBatchSetting.version == expected_version,
                )
                .values(version=expected_version + 1)
            )
            if changed.rowcount != 1:
                raise MemoryConflictError("memory_batch_settings_version_conflict")
        if model_id:
            if profile is None:
                profile = MemoryBatchProfile(
                    owner_id=scope.owner_id,
                    model_id=model_id,
                    version=1,
                    updated_at=now,
                )
                self.session.add(profile)
            elif profile.model_id != model_id:
                changed = self.session.execute(
                    update(MemoryBatchProfile)
                    .where(
                        MemoryBatchProfile.owner_id == scope.owner_id,
                        MemoryBatchProfile.version == expected_profile_version,
                    )
                    .values(
                        model_id=model_id,
                        version=expected_profile_version + 1,
                        updated_at=now,
                    )
                )
                if changed.rowcount != 1:
                    raise MemoryConflictError("memory_batch_settings_version_conflict")
        current.ai_enabled, current.shutdown_enabled = ai_enabled, shutdown_enabled
        current.consent_version = MEMORY_CONSENT_VERSION if ai_enabled else None
        current.schedule_enabled, current.local_time, current.timezone = (
            schedule_enabled,
            local_time,
            zone,
        )
        consumed = (
            None
            if current.last_consumed_date is None
            else date.fromisoformat(current.last_consumed_date)
        )
        current.next_due_at = (
            next_daily_slot(
                after=now,
                local_time=local_time,
                timezone=zone,
                last_consumed_date=consumed,
            )
            if schedule_enabled and ai_enabled
            else None
        )
        current.last_request_key, current.last_request_digest, current.updated_at = (
            idempotency_key,
            digest,
            now,
        )
        if not schedule_enabled:
            if current.trigger_kind == "scheduled":
                current.trigger_cutoff, current.trigger_kind = 0, None
            jobs = self.session.scalars(
                select(MemoryMaintenanceJob)
                .join(MemoryBatchRun, MemoryBatchRun.job_id == MemoryMaintenanceJob.id)
                .where(
                    MemoryBatchRun.scope_setting_id == setting.id,
                    MemoryBatchRun.trigger == "scheduled",
                    MemoryMaintenanceJob.status == "pending",
                    MemoryMaintenanceJob.attempt_count == 0,
                )
            ).all()
            for job in jobs:
                job.status, job.completed_at = "cancelled", now
                self.session.execute(
                    update(MemorySourceDelivery)
                    .where(MemorySourceDelivery.batch_job_id == job.id)
                    .values(batch_job_id=None)
                )
        self.session.flush()
        return self.settings(scope)

    def enqueue(
        self,
        *,
        scope_setting_id: str,
        candidate_ids: tuple[str, ...],
        cutoff: int,
        trigger: str,
        now: datetime,
        explicit_key: str = "",
    ) -> str | None:
        if not candidate_ids:
            return None
        scope = self.session.get(MemoryScopeSettingModel, scope_setting_id)
        config = self.session.get(MemoryBatchSetting, scope_setting_id)
        if (
            scope is None
            or not scope.enabled
            or config is None
            or not config.ai_enabled
            or config.consent_version != MEMORY_CONSENT_VERSION
        ):
            return None
        profile = self.session.get(MemoryBatchProfile, scope.owner_id)
        if profile is None:
            return None
        # Key excludes trigger/clock/settings: re-opening or changing schedules
        # cannot reset this batch's durable retry budget.
        ids_json = json.dumps(sorted(candidate_ids), separators=(",", ":"))
        key = (
            "mb2:"
            + hashlib.sha256(
                (scope_setting_id + ids_json + explicit_key).encode()
            ).hexdigest()
        )
        job = self.queue.enqueue(
            scope_setting_id=scope_setting_id,
            reason="memory_selection_v2",
            idempotency_key=key,
        )
        if self.session.get(MemoryBatchRun, job) is None:
            self.session.add(
                MemoryBatchRun(
                    job_id=job,
                    scope_setting_id=scope_setting_id,
                    trigger=trigger,
                    scope_version=scope.version,
                    settings_version=config.version,
                    profile_version=profile.version,
                    model_id=profile.model_id,
                    cutoff_sequence=cutoff,
                    candidate_ids_json=ids_json,
                    available_at=now,
                )
            )
            self.session.flush()
        else:
            previous = self.session.get(MemoryMaintenanceJob, job)
            if previous.status == "cancelled" and previous.attempt_count == 0:
                previous.status, previous.completed_at = "pending", None
                self.session.get(MemoryBatchRun, job).trigger = trigger
        self.session.execute(
            update(MemorySourceDelivery)
            .where(
                MemorySourceDelivery.scope_setting_id == scope_setting_id,
                MemorySourceDelivery.candidate_id.in_(candidate_ids),
            )
            .values(batch_job_id=job)
        )
        return job

    def retry_failed(
        self, scope: MemoryScope, *, idempotency_key: str, now: datetime
    ) -> None:
        normalize_memory_idempotency_key(idempotency_key)
        setting = self.memory.get_scope_setting(scope)
        if setting is None:
            raise MemoryValidationError("memory_selection_settings_required")
        config = self.settings(scope)
        if not config.memory_enabled or not config.ai_enabled:
            raise MemoryValidationError("memory_selection_settings_required")
        assigned = exists(
            select(MemorySourceDelivery.sequence).where(
                MemorySourceDelivery.batch_job_id == MemoryBatchRun.job_id,
                MemorySourceDelivery.candidate_id.is_not(None),
            )
        )
        runs = self.session.scalars(
            select(MemoryBatchRun)
            .join(
                MemoryMaintenanceJob, MemoryMaintenanceJob.id == MemoryBatchRun.job_id
            )
            .where(
                MemoryBatchRun.scope_setting_id == setting.id,
                MemoryMaintenanceJob.status == "failed",
                assigned,
            )
            .order_by(MemoryMaintenanceJob.created_at)
            .limit(8)
        ).all()
        for run in runs:
            # Repeated clicks cannot mint another paid retry. The explicit
            # request is distinct from automatic attempts and remains audited.
            candidates = tuple(
                self.session.scalars(
                    select(MemorySourceDelivery.candidate_id).where(
                        MemorySourceDelivery.batch_job_id == run.job_id,
                        MemorySourceDelivery.candidate_id.is_not(None),
                    )
                )
            )
            if candidates:
                self.enqueue(
                    scope_setting_id=setting.id,
                    candidate_ids=candidates,
                    cutoff=run.cutoff_sequence,
                    trigger="explicit",
                    explicit_key=idempotency_key,
                    now=now,
                )

    def claim(self, *, lease_token: str, now: datetime) -> MemorySelectionBatch | None:
        # Runtime calls this on a fresh session; SQLite serializes read/claim.
        if self.session.bind.dialect.name == "sqlite":
            self.session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        active = self.session.scalar(
            select(MemoryMaintenanceJob.id)
            .join(MemoryBatchRun, MemoryBatchRun.job_id == MemoryMaintenanceJob.id)
            .where(
                MemoryMaintenanceJob.status == "running",
                MemoryMaintenanceJob.lease_expires_at > now,
            )
            .limit(1)
        )
        if active is not None:
            return None
        rows = self.session.scalars(
            select(MemoryBatchRun)
            .join(
                MemoryMaintenanceJob, MemoryMaintenanceJob.id == MemoryBatchRun.job_id
            )
            .join(
                MemoryBatchSetting,
                MemoryBatchSetting.scope_setting_id == MemoryBatchRun.scope_setting_id,
            )
            .join(
                MemoryScopeSettingModel,
                MemoryScopeSettingModel.id == MemoryBatchRun.scope_setting_id,
            )
            .where(
                MemoryScopeSettingModel.enabled.is_(True),
                MemoryBatchSetting.ai_enabled.is_(True),
                MemoryBatchSetting.consent_version == MEMORY_CONSENT_VERSION,
                MemoryBatchRun.available_at <= now,
                or_(
                    MemoryMaintenanceJob.status == "pending",
                    (MemoryMaintenanceJob.status == "running")
                    & (MemoryMaintenanceJob.lease_expires_at <= now),
                ),
            )
            .order_by(
                MemoryBatchSetting.last_claimed_at.asc().nullsfirst(),
                MemoryBatchRun.available_at,
                MemoryBatchRun.job_id,
            )
            .limit(50)
        ).all()
        for run in rows:
            scope = self.session.get(MemoryScopeSettingModel, run.scope_setting_id)
            config = self.session.get(MemoryBatchSetting, run.scope_setting_id)
            if (
                scope is None
                or config is None
                or not scope.enabled
                or not config.ai_enabled
                or config.consent_version != MEMORY_CONSENT_VERSION
            ):
                continue
            profile = self.session.get(MemoryBatchProfile, scope.owner_id)
            if profile is None:
                continue
            job = self.session.get(MemoryMaintenanceJob, run.job_id)
            try:
                self.memory.validate_scope(self.memory._to_scope(scope).scope)
            except MemoryDomainError:
                job.status, job.completed_at = "failed", now
                job.lease_token = job.lease_expires_at = None
                job.last_error_code = run.last_code = (
                    "memory_selection_scope_unavailable"
                )
                config.last_claimed_at = now
                continue
            if (
                job.attempt_count >= MAX_BATCH_ATTEMPTS
                or run.physical_calls >= MAX_BATCH_ATTEMPTS
            ):
                job.status, job.completed_at = "failed", now
                job.lease_token = job.lease_expires_at = None
                job.last_error_code = "memory_selection_attempts_exhausted"
                run.last_code = "memory_selection_attempts_exhausted"
                continue
            work = self.queue.claim(
                lease_token=lease_token,
                now=now,
                lease_for=MAINTENANCE_LEASE_DURATION,
                job_id=run.job_id,
            )
            if work is None:
                continue
            # A retry starts a new immutable settings snapshot, never revives an
            # earlier response. Attempt counters remain on this same job.
            run.scope_version, run.settings_version = scope.version, config.version
            run.profile_version, run.model_id = profile.version, profile.model_id
            config.last_claimed_at = now
            ids = json.loads(run.candidate_ids_json)
            candidates = self.session.scalars(
                select(MemoryCandidate)
                .where(
                    MemoryCandidate.id.in_(ids),
                    MemoryCandidate.scope_setting_id == run.scope_setting_id,
                    MemoryCandidate.status == "pending",
                )
                .order_by(MemoryCandidate.id)
            ).all()
            return MemorySelectionBatch(
                run.job_id,
                self.memory._to_scope(scope),
                tuple(self.memory._to_candidate(row) for row in candidates),
                run.model_id,
                scope.version,
                config.version,
                profile.version,
                work.attempt_count,
                lease_token,
            )
        self.session.flush()
        return None

    def fence(self, batch: MemorySelectionBatch, *, now: datetime) -> None:
        self.session.expire_all()
        self.memory.validate_scope(batch.setting.scope)
        scope = self.session.get(MemoryScopeSettingModel, batch.setting.id)
        config = self.session.get(MemoryBatchSetting, batch.setting.id)
        profile = self.session.get(MemoryBatchProfile, batch.setting.scope.owner_id)
        if (
            scope is None
            or not scope.enabled
            or scope.version != batch.scope_version
            or config is None
            or not config.ai_enabled
            or config.version != batch.settings_version
            or profile is None
            or profile.version != batch.profile_version
        ):
            raise MemoryConflictError("memory_selection_scope_changed")
        self.queue.renew(
            job_id=batch.job_id,
            lease_token=batch.lease_token,
            now=now,
            lease_for=MAINTENANCE_LEASE_DURATION,
        )

    def record_call(self, batch: MemorySelectionBatch, *, now: datetime) -> None:
        self.fence(batch, now=now)
        run = self.session.get(MemoryBatchRun, batch.job_id)
        if run.physical_calls >= MAX_BATCH_ATTEMPTS:
            raise MemoryConflictError("memory_selection_attempts_exhausted")
        run.physical_calls += 1
        self.session.flush()

    def record_telemetry(self, batch, *, latency_ms, usage):
        run = self.session.get(MemoryBatchRun, batch.job_id)
        run.provider_latency_ms = max(0, latency_ms)
        for field in ("input_tokens", "output_tokens", "thought_tokens"):
            value = getattr(usage, field, None)
            if isinstance(value, int) and value >= 0:
                setattr(run, field, value)
        self.session.flush()

    def record_decision(self, batch, candidate, *, decision, reason, item_id, now):
        self.session.add(
            MemorySelectionDecisionModel(
                id=str(uuid4()),
                job_id=batch.job_id,
                candidate_id=candidate.id,
                source_digest=candidate.source_digest,
                decision=decision,
                reason_code=reason,
                item_id=item_id,
                created_at=now,
            )
        )

    def complete(self, batch: MemorySelectionBatch, *, now: datetime) -> None:
        # Flush item/evidence/decisions before expiring the loaded snapshot.
        self.session.flush()
        self.fence(batch, now=now)
        self.session.get(
            MemoryBatchRun, batch.job_id
        ).last_code = "memory_selection_completed"
        self.session.get(MemoryBatchSetting, batch.setting.id).brief_dirty = True
        self.queue.complete(job_id=batch.job_id, lease_token=batch.lease_token, now=now)

    def fail(self, batch: MemorySelectionBatch, *, code: str, now: datetime) -> None:
        run = self.session.get(MemoryBatchRun, batch.job_id)
        job = self.session.get(MemoryMaintenanceJob, batch.job_id)
        if (
            run is None
            or job is None
            or job.status != "running"
            or job.lease_token != batch.lease_token
        ):
            return
        retryable = (
            batch.attempt < MAX_BATCH_ATTEMPTS
            and code != "memory_selection_settings_required"
        )
        # A cancelled/expired provider cannot commit; the same durable run is
        # recoverable without relying on a still-live lease for failure audit.
        changed = self.session.execute(
            update(MemoryMaintenanceJob)
            .where(
                MemoryMaintenanceJob.id == batch.job_id,
                MemoryMaintenanceJob.status == "running",
                MemoryMaintenanceJob.lease_token == batch.lease_token,
            )
            .values(
                status="pending" if retryable else "failed",
                started_at=None if retryable else job.started_at,
                last_error_code=code,
                lease_token=None,
                lease_expires_at=None,
                completed_at=None if retryable else now,
            )
        )
        if changed.rowcount != 1:
            return
        run.last_code, run.available_at = code, as_utc(now) + retry_delay(batch.attempt)
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
