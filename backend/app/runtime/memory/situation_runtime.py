"""One bounded canonical consumer; background projections own embedding I/O."""
from app.core import work_observation as observation
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import logging
from time import monotonic
from sqlalchemy import select, update, or_, exists
from app.core.sqlite_concurrency import is_sqlite_contention
from app.core.database_transactions import database_write

from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryCapacityReached, MemoryConflictError
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemorySituationApplyRun, MemorySituationProcessingSetting, MemorySituationRequest
from app.domains.memory.repository.situation_runs import claim_run, request_run, next_due
from app.domains.memory.repository.situation_apply import apply_page, prepare_page, SituationPageStale
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.situation_application_sources import PreparedSituationSources


class SituationRuntime:
    def __init__(self, session_factory, *, data_root=None):
        self.session_factory = session_factory
        from app.runtime.memory.situation_result_basis import CheckpointResultBasis
        from app.runtime.checkpoint_registry import bound_store
        checkpoint_store=bound_store(data_root) if data_root is not None else None
        self.result_basis = CheckpointResultBasis(data_root / "runtime/activity/activity-checkpoints.sqlite" if data_root is not None and checkpoint_store is None else None,store=checkpoint_store)
        self.quit_identity = None

    @observation.observed("situation_due_admission")
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
                    database_write(db, prepare_setting, require_clean=True)
                except MemoryConflictError as exc:
                    if str(exc) != "situation_scope_busy":
                        raise

    def tick(self, run_id=None):
        try:
            return self._tick(run_id)
        except Exception as exc:
            if not is_sqlite_contention(exc):
                raise
            # No claim or release acknowledgement was durable. Its existing
            # lease, if any, is the only recovery owner; never create a new run.
            return "situation_storage_busy"

    @observation.observed("situation_claim")
    def candidate(self):
        """One immutable run identity; never return an ORM row to async code."""
        now = datetime.now(UTC)
        with self.session_factory() as db:
            row = db.execute(select(MemorySituationApplyRun.id, MemorySituationApplyRun.created_at,
                MemoryScopeSettingModel.world_id, MemoryScopeSettingModel.subject_world_character_id)
                .join(MemoryScopeSettingModel, MemoryScopeSettingModel.id == MemorySituationApplyRun.scope_setting_id)
                .where(MemorySituationApplyRun.state.in_(("pending", "running", "deferred")),
                    or_(MemorySituationApplyRun.lease_until.is_(None), MemorySituationApplyRun.lease_until <= now))
                .order_by(MemorySituationApplyRun.created_at, MemorySituationApplyRun.id).limit(1)).first()
            return None if row is None else dict(kind="memory", id=row[0], accepted_at=utc_instant(row[1]), world_id=row[2], actor_id=row[3])

    def _tick(self, selected_run_id=None):
        now = datetime.now(UTC)
        with self.session_factory() as db:
            run_info = db.execute(select(MemorySituationApplyRun.id, MemoryScopeSettingModel.world_id, MemoryScopeSettingModel.subject_world_character_id).join(MemoryScopeSettingModel, MemoryScopeSettingModel.id == MemorySituationApplyRun.scope_setting_id).where(
                MemorySituationApplyRun.state.in_(("pending", "running", "deferred")),
                (MemorySituationApplyRun.lease_until.is_(None)) | (MemorySituationApplyRun.lease_until <= now),
                *([MemorySituationApplyRun.id == selected_run_id] if selected_run_id else []),
            ).order_by(MemorySituationApplyRun.created_at, MemorySituationApplyRun.id).limit(1)).first()
            if run_info is None:
                return "memory_batch_queue_empty"
            run_id, world_id, actor_id = run_info
            db.rollback()
            token = database_write(db,
                lambda: claim_run(db, run_id, now=now), require_clean=True)
        if token is None:
            return "situation_claim_conflict"
        with observation.scope(world_id=world_id, actor_id=actor_id, run_id=run_id):
            return self._apply_claimed(run_id, token)

    def _apply_claimed(self, run_id, token):
        try:
            for attempt in range(3):
                started = monotonic()
                with self.session_factory() as db:
                    prepared = prepare_page(db, run_id=run_id, token=token, now=datetime.now(UTC), page_size=1)
                observation.emit("page", boundary="prepared", run_id=run_id, receipt_ids=[str(row[0]) for row in prepared.admissions], byte_size=prepared.byte_size, cursor=prepared.cursor, cutoff=prepared.cutoff)
                with observation.span("situation_result_basis"):
                    basis = self.result_basis.prepare(prepared)
                prepared_at = monotonic()
                try:
                    with self.session_factory() as db:
                        database_write(db, lambda: apply_page(db, memory_repository(db), PreparedSituationSources(db, result_basis=basis),
                            run_id=run_id, token=token, now=datetime.now(UTC), page_size=1, prepared=prepared), require_clean=True)
                    observation.emit("page", boundary="committed", run_id=run_id, receipt_ids=[str(row[0]) for row in prepared.admissions])
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
            def release():
                run = db.get(MemorySituationApplyRun, run_id, populate_existing=True, with_for_update=True)
                if run is None or run.lease_token != token:
                    return
                due = None
                control = dict(run.maintenance or {})
                new_state, new_code = state, code
                if code in {"situation_storage_busy", "situation_preparation_stale"}:
                    from random import uniform
                    first = datetime.fromisoformat(control.get("storage_first", datetime.now(UTC).isoformat()))
                    first = first.replace(tzinfo=UTC) if first.tzinfo is None else first
                    rounds = control.get("storage_rounds", 0)+1
                    control.update(storage_first=first.isoformat(), storage_rounds=rounds)
                    if rounds >= 3 or (datetime.now(UTC)-first).total_seconds() >= 120:
                        new_state, new_code = "error", "situation_storage_retry_exhausted"
                        control["hold"] = "manual"
                    else:
                        due = min(first+timedelta(seconds=120), datetime.now(UTC)+timedelta(seconds=(5,15)[rounds-1]+uniform(0,1)))
                run.state, run.error_code = new_state, new_code
                run.lease_token, run.lease_until, run.maintenance = None, due, control
            database_write(db, release, require_clean=True)

    def fence(self):
        with self.session_factory() as db:
            result = db.execute(update(MemorySituationApplyRun).where(MemorySituationApplyRun.state == "running").values(
                state="deferred", lease_token=None, lease_until=None, error_code="situation_shutdown_deferred"))
            unfinished = db.scalar(select(MemorySituationApplyRun.id).where(
                MemorySituationApplyRun.state.in_(("pending", "running", "deferred"))).limit(1)) is not None
            db.commit()
            return result.rowcount > 0 or unfinished
