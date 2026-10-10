"""One bounded canonical consumer; background projections own embedding I/O."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import select, update, or_, exists

from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryCapacityReached, MemoryConflictError
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemorySituationApplyRun, MemorySituationProcessingSetting, MemorySituationRequest
from app.domains.memory.repository.situation_runs import claim_run, request_run, next_due
from app.domains.memory.repository.situation_apply import apply_page
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
            rows = list(db.scalars(query.order_by(MemorySituationProcessingSetting.next_due_at, MemorySituationProcessingSetting.scope_setting_id).limit(32)))
            memory = memory_repository(db)
            for config in rows:
                if config.timezone != zone:
                    config.timezone, config.updated_at = zone, now
                    config.version += 1
                    config.next_due_at = next_due(now, config.local_time, zone) if config.daily_enabled else None
                elif config.daily_enabled and config.next_due_at is None:
                    config.next_due_at = next_due(now, config.local_time, zone)
                if not shutdown and (not config.daily_enabled or config.next_due_at is None or utc_instant(config.next_due_at) > now):
                    continue
                row = db.get(MemoryScopeSettingModel, config.scope_setting_id)
                scope = MemoryScope(row.owner_id, row.world_id, row.subject_world_character_id)
                memory.validate_scope(scope)
                setting = memory.get_scope_setting(scope)
                try:
                    request_run(db, setting, trigger="quit" if shutdown else "scheduled",
                        request_key=self.quit_identity if shutdown else "daily:" + stable_digest(utc_instant(config.next_due_at).isoformat()),
                        expected_version=config.version, now=now)
                except MemoryConflictError as exc:
                    if str(exc) != "situation_scope_busy":
                        raise
                    # Keep the due time / quit request absent so the next bounded
                    # prepare retries it after the owner's recheck completes.
                    continue
            db.commit()

    def tick(self):
        now = datetime.now(UTC)
        with self.session_factory() as db:
            run_id = db.scalar(select(MemorySituationApplyRun.id).where(
                MemorySituationApplyRun.state.in_(("pending", "running", "deferred")),
                (MemorySituationApplyRun.lease_until.is_(None)) | (MemorySituationApplyRun.lease_until <= now),
            ).order_by(MemorySituationApplyRun.attempts, MemorySituationApplyRun.created_at, MemorySituationApplyRun.id).limit(1))
            if run_id is None:
                return "memory_batch_queue_empty"
            token = claim_run(db, run_id, now=now)
            db.commit()
        if token is None:
            return "situation_claim_conflict"
        try:
            with self.session_factory() as db:
                apply_page(db, memory_repository(db), SituationSources(db, result_basis=self.result_basis),
                    run_id=run_id, token=token, now=datetime.now(UTC), page_size=16)
                db.commit()
            return "situation_page_applied"
        except MemoryCapacityReached:
            code = "memory_capacity_reached"
        except MemoryConflictError:
            code = "situation_apply_conflict"
        except Exception:
            # The page transaction rolled back; no partial progress or canonical
            # memory escapes it. Preserve its cutoff for an explicit retry;
            # an unexpected poison page must not loop forever in the background.
            code = "situation_apply_failed"
        with self.session_factory() as db:
            db.execute(update(MemorySituationApplyRun).where(MemorySituationApplyRun.id == run_id,
                MemorySituationApplyRun.lease_token == token).values(
                    state="error",
                    error_code=code, lease_token=None,
                    lease_until=None))
            db.commit()
        return code

    def fence(self):
        with self.session_factory() as db:
            result = db.execute(update(MemorySituationApplyRun).where(MemorySituationApplyRun.state == "running").values(
                state="deferred", lease_token=None, lease_until=None, error_code="situation_shutdown_deferred"))
            unfinished = db.scalar(select(MemorySituationApplyRun.id).where(
                MemorySituationApplyRun.state != "completed").limit(1)) is not None
            db.commit()
            return result.rowcount > 0 or unfinished
