"""One bounded canonical consumer; background projections own embedding I/O."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import logging
from time import monotonic
from sqlalchemy import select, update, or_, exists
from app.core.sqlite_concurrency import is_sqlite_contention, run_sqlite_session_immediate

from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryCapacityReached, MemoryConflictError
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemorySituationApplyRun, MemorySituationProcessingSetting, MemorySituationRequest
from app.domains.memory.repository.situation_runs import claim_run, request_run, next_due
from app.domains.memory.repository.situation_apply import apply_page, prepare_page, SituationPageStale
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.situation_sources import SituationSources


class SituationRuntime:
    def __init__(self, session_factory, *, data_root=None):
        self.session_factory = session_factory
        from app.runtime.memory.situation_result_basis import CheckpointResultBasis
        self.result_basis = CheckpointResultBasis(data_root / "runtime/activity/activity-checkpoints.sqlite" if data_root is not None else None)
        self.quit_identity = None

    def prepare(self, *, shutdown=False):
        now = datetime.now(UTC)
        if shutdown and self.quit_identity is None:
            self.quit_identity = "quit:" + uuid4().hex
        with self.session_factory() as db:
            from app.domains.identity.service.environment import installation_snapshot
            zone = installation_snapshot(db).timezone
            query = select(MemorySituationProcessingSetting).join(MemoryScopeSettingModel,
                MemoryScopeSettingModel.id == MemorySituationProcessingSetting.scope_setting_id).where(MemoryScopeSettingModel.enabled.is_(True))
            query = query.where(MemorySituationProcessingSetting.shutdown_apply_enabled.is_(True), ~exists().where(
                MemorySituationRequest.scope_setting_id == MemorySituationProcessingSetting.scope_setting_id,
                MemorySituationRequest.request_key == self.quit_identity)) if shutdown else query.where(or_(
                MemorySituationProcessingSetting.timezone != zone,
                MemorySituationProcessingSetting.daily_enabled.is_(True) & or_(MemorySituationProcessingSetting.next_due_at <= now,
                    MemorySituationProcessingSetting.next_due_at.is_(None))))
            identifiers = tuple(db.scalars(query.with_only_columns(MemorySituationProcessingSetting.scope_setting_id)
                .order_by(MemorySituationProcessingSetting.next_due_at, MemorySituationProcessingSetting.scope_setting_id).limit(32)))
        for setting_id in identifiers:
            with self.session_factory() as db:
                def prepare_setting():
                    from app.domains.identity.service.environment import installation_snapshot
                    zone = installation_snapshot(db).timezone
                    config = db.get(MemorySituationProcessingSetting, setting_id, populate_existing=True)
                    row = db.get(MemoryScopeSettingModel, setting_id, populate_existing=True)
                    if config is None or row is None or not row.enabled:
                        return
                    if shutdown and not config.shutdown_apply_enabled:
                        return
                    if config.timezone != zone:
                        config.timezone, config.updated_at = zone, now
                        config.version += 1
                        config.next_due_at = next_due(now, config.local_time, zone) if config.daily_enabled else None
                    elif config.daily_enabled and config.next_due_at is None:
                        config.next_due_at = next_due(now, config.local_time, zone)
                    if not shutdown and (not config.daily_enabled or config.next_due_at is None or utc_instant(config.next_due_at) > now):
                        return
                    scope = MemoryScope(row.owner_id, row.world_id, row.subject_world_character_id)
                    memory = memory_repository(db)
                    memory.validate_scope(scope)
                    setting = memory.get_scope_setting(scope)
                    request_run(db, setting, trigger="quit" if shutdown else "scheduled",
                        request_key=self.quit_identity if shutdown else "daily:" + stable_digest(utc_instant(config.next_due_at).isoformat()),
                        expected_version=config.version, now=now)
                try:
                    run_sqlite_session_immediate(db, prepare_setting, require_clean=True)
                except MemoryConflictError as exc:
                    if str(exc) != "situation_scope_busy":
                        raise

    def tick(self):
        try:
            return self._tick()
        except Exception as exc:
            if not is_sqlite_contention(exc):
                raise
            # No claim or release acknowledgement was durable. Its existing
            # lease, if any, is the only recovery owner; never create a new run.
            return "situation_storage_busy"

    def _tick(self):
        now = datetime.now(UTC)
        with self.session_factory() as db:
            run_id = db.scalar(select(MemorySituationApplyRun.id).where(
                MemorySituationApplyRun.state.in_(("pending", "running", "deferred")),
                (MemorySituationApplyRun.lease_until.is_(None)) | (MemorySituationApplyRun.lease_until <= now),
            ).order_by(MemorySituationApplyRun.attempts, MemorySituationApplyRun.created_at, MemorySituationApplyRun.id).limit(1))
            if run_id is None:
                return "memory_batch_queue_empty"
            db.rollback()
            token = run_sqlite_session_immediate(db,
                lambda: claim_run(db, run_id, now=now), require_clean=True)
        if token is None:
            return "situation_claim_conflict"
        try:
            for attempt in range(3):
                started = monotonic()
                with self.session_factory() as db:
                    prepared = prepare_page(db, run_id=run_id, token=token, now=datetime.now(UTC), page_size=1)
                basis = self.result_basis.prepare(prepared)
                prepared_at = monotonic()
                try:
                    with self.session_factory() as db:
                        run_sqlite_session_immediate(db, lambda: apply_page(db, memory_repository(db), SituationSources(db, result_basis=basis),
                            run_id=run_id, token=token, now=datetime.now(UTC), page_size=1, prepared=prepared), require_clean=True)
                    logging.getLogger(__name__).info("situation_page run=%s count=%s bytes=%s prepare_ms=%.3f apply_elapsed_ms=%.3f",
                        run_id, len(prepared.admissions), prepared.byte_size,
                        (prepared_at - started) * 1000, (monotonic() - prepared_at) * 1000)
                    return "situation_page_applied"
                except SituationPageStale:
                    if attempt == 2:
                        self._release(run_id, token, state="deferred", code="situation_preparation_stale")
                        return "situation_preparation_stale"
        except MemoryCapacityReached:
            code = "memory_capacity_reached"
        except MemoryConflictError:
            code = "situation_apply_conflict"
        except Exception as exc:
            if is_sqlite_contention(exc):
                self._release(run_id, token, state="deferred", code="situation_storage_busy")
                return "situation_storage_busy"
            # The page transaction rolled back; no partial progress or canonical
            # memory escapes it. Preserve its cutoff for an explicit retry;
            # an unexpected poison page must not loop forever in the background.
            code = "situation_apply_failed"
        self._release(run_id, token, state="error", code=code)
        return code

    def _release(self, run_id, token, *, state, code):
        with self.session_factory() as db:
            run_sqlite_session_immediate(db, lambda: db.execute(update(MemorySituationApplyRun).where(
                MemorySituationApplyRun.id == run_id, MemorySituationApplyRun.lease_token == token).values(
                    state=state, error_code=code, lease_token=None, lease_until=None)), require_clean=True)

    def fence(self):
        with self.session_factory() as db:
            result = db.execute(update(MemorySituationApplyRun).where(MemorySituationApplyRun.state == "running").values(
                state="deferred", lease_token=None, lease_until=None, error_code="situation_shutdown_deferred"))
            unfinished = db.scalar(select(MemorySituationApplyRun.id).where(
                MemorySituationApplyRun.state != "completed").limit(1)) is not None
            db.commit()
            return result.rowcount > 0 or unfinished
