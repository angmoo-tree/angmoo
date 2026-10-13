"""Owner authorization and UoW for processing settings and explicit save."""
from datetime import UTC, datetime
from sqlalchemy import func, select
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.items import normalize_memory_idempotency_key
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.memory.models.activity_situation import MemorySituationProcessingSetting, MemorySituationApplyRun, MemorySituationReceipt, MemorySituationRequest
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.repository.situation_runs import get_or_create_settings, next_due, request_run
from app.domains.memory.schemas.situation import MemoryProcessingRead
from app.domains.memory.repository.situation_recovery import active_run
from app.domains.memory.models.batch import MemoryActivationEpoch


def read(*, scope, db, workflows, result=None, request_key=None):
    memory = workflows.batch_repository(db).memory
    memory.validate_scope(scope)
    setting = memory.get_scope_setting(scope)
    config = db.get(MemorySituationProcessingSetting, setting.id) if setting else None
    legacy = db.get(MemoryBatchSetting, setting.id) if setting and config is None else None
    pending = blocked = 0
    run = None
    resolved = None
    if setting:
        if request_key is not None:
            resolved = db.get(MemorySituationRequest, (setting.id, request_key))
        counts = dict(db.execute(select(MemorySituationReceipt.state, func.count()).where(
            MemorySituationReceipt.scope_setting_id == setting.id).group_by(MemorySituationReceipt.state)).all())
        pending, blocked = counts.get("pending", 0), counts.get("blocked", 0) + counts.get("error", 0)
        run = (db.get(MemorySituationApplyRun, resolved.run_id) if resolved and resolved.run_id else None) if request_key is not None else db.scalar(
            select(MemorySituationApplyRun).where(MemorySituationApplyRun.scope_setting_id == setting.id)
            .order_by(MemorySituationApplyRun.created_at.desc(), MemorySituationApplyRun.id.desc()).limit(1))
    status = "idle"
    if run:
        status = "applying" if run.state == "running" else "accepted" if run.state in {"pending", "deferred"} else "partial_error" if run.state == "error" or run.blocked_count else "saved"
    zone = config.timezone if config else legacy.timezone if legacy else workflows.batch_repository(db).timezone(scope)
    busy = active_run(db, setting.id) is not None if setting else False
    eligible = db.scalar(select(MemorySituationReceipt.sequence).join(MemoryActivationEpoch,
        MemoryActivationEpoch.id == MemorySituationReceipt.activation_epoch).where(
            MemorySituationReceipt.scope_setting_id == setting.id, MemorySituationReceipt.state == "blocked",
            MemorySituationReceipt.scope_version == setting.version,
            MemoryActivationEpoch.scope_setting_id == setting.id, MemoryActivationEpoch.closed_at.is_(None)).limit(1)) if setting and setting.enabled else None
    return MemoryProcessingRead(scope={"world_id": scope.world_id, "subject_world_character_id": scope.subject_world_character_id},
        version=config.version if config else 1, memory_enabled=bool(setting and setting.enabled),
        daily_enabled=config.daily_enabled if config else legacy.schedule_enabled if legacy else False,
        local_time=config.local_time if config else legacy.local_time if legacy else "22:30",
        timezone=zone, shutdown_apply_enabled=config.shutdown_apply_enabled if config else legacy.shutdown_enabled if legacy else True,
        next_due_at=config.next_due_at if config else legacy.next_due_at if legacy else None,
        last_applied_at=config.last_applied_at if config else None,
        pending_count=pending, blocked_count=blocked, status=status, applied_count=run.applied_count if run else 0,
        result=resolved.result_code if resolved else result,
        resolved_request_key=resolved.request_key if resolved else None,
        operation=run.work_kind if run else None, run_id=run.id if run else None, run_state=run.state if run else None,
        rejected_count=run.blocked_count if run else 0, skipped_count=run.skipped_count if run else 0,
        scope_busy=busy, can_recheck=eligible is not None and not busy)


def _ensure(db, workflows, scope, now):
    batch = workflows.batch_repository(db)
    batch.memory.validate_scope(scope)
    setting = batch.memory.get_or_create_scope_setting(scope)
    old = db.get(MemorySituationProcessingSetting, setting.id)
    config = get_or_create_settings(db, setting.id, timezone=batch.timezone(scope), now=now)
    return setting, config, old is None


def save_settings(*, scope, db, workflows, data):
    now = datetime.now(UTC)
    try:
        normalize_memory_idempotency_key(data.idempotency_key)
        setting, config, created = _ensure(db, workflows, scope, now)
        digest = stable_digest(data.model_dump(exclude={"idempotency_key"}))
        if config.last_request_key == data.idempotency_key:
            if config.last_request_digest != digest:
                raise MemoryConflictError("situation_request_conflict")
        else:
            expected = config.version
            if expected != data.expected_version:
                raise MemoryConflictError("situation_settings_version_conflict")
            due = next_due(now, data.local_time, config.timezone)
            changed = (config.daily_enabled, config.local_time) != (data.daily_enabled, data.local_time)
            config.daily_enabled, config.local_time = data.daily_enabled, data.local_time
            config.shutdown_apply_enabled = data.shutdown_apply_enabled
            if changed or (data.daily_enabled and config.next_due_at is None):
                config.next_due_at = due if data.daily_enabled else None
            config.version = data.expected_version + 1
            config.last_request_key, config.last_request_digest = data.idempotency_key, digest
            config.updated_at = now
        db.commit()
    except Exception:
        db.rollback()
        raise
    return read(scope=scope, db=db, workflows=workflows)


def save_now(*, scope, db, workflows, data):
    now = datetime.now(UTC)
    try:
        setting, config, created = _ensure(db, workflows, scope, now)
        value = request_run(db, setting, trigger="manual", request_key=data.idempotency_key,
            expected_version=data.expected_version, now=now)
        result = value.result_code
        db.commit()
    except Exception:
        db.rollback()
        raise
    return read(scope=scope, db=db, workflows=workflows, result=result, request_key=data.idempotency_key)
