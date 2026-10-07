"""Bounded run identities shared by explicit save, due schedules and native quit."""
from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import func, select, update

from app.core.calendar import utc_instant, wall_time
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.items import normalize_memory_idempotency_key
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.models.activity_situation import (
    MemorySituationProcessingSetting, MemorySituationApplyRun, MemorySituationRequest, MemorySituationReceipt,
)


def next_due(now, local_time, timezone):
    try:
        hour, minute = map(int, local_time.split(":"))
        if len(local_time) != 5 or not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError()
        day = utc_instant(now).astimezone(ZoneInfo(timezone)).date()
        candidate = wall_time(day, hour, minute, timezone)
        return candidate if candidate > utc_instant(now) else wall_time(day + timedelta(days=1), hour, minute, timezone)
    except (ValueError, KeyError):
        raise MemoryValidationError("situation_schedule_invalid") from None


def get_or_create_settings(session, setting_id, *, timezone, now):
    session.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id == setting_id).values(id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    row = session.get(MemorySituationProcessingSetting, setting_id)
    if row is None:
        legacy = session.get(MemoryBatchSetting, setting_id)
        row = MemorySituationProcessingSetting(scope_setting_id=setting_id,
            daily_enabled=legacy.schedule_enabled if legacy else False,
            local_time=legacy.local_time if legacy else "22:30", timezone=legacy.timezone if legacy else timezone,
            shutdown_apply_enabled=legacy.shutdown_enabled if legacy else True,
            next_due_at=legacy.next_due_at if legacy else None, version=1, updated_at=now)
        session.add(row)
        session.flush()
    return row


def request_run(session, setting, *, trigger, request_key, expected_version, now):
    """Flush only. Idempotent aliases retain their original result, even when empty."""
    if trigger not in {"manual", "scheduled", "quit"}:
        raise MemoryValidationError("situation_trigger_invalid")
    normalize_memory_idempotency_key(request_key)
    session.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id == setting.id).values(id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    current = session.get(MemoryScopeSettingModel, setting.id, populate_existing=True)
    if current is None or not current.enabled:
        raise MemoryConflictError("situation_memory_disabled")
    config = session.get(MemorySituationProcessingSetting, setting.id, populate_existing=True)
    if config is None:
        raise MemoryConflictError("situation_settings_missing")
    digest = stable_digest({"scope": asdict(setting.scope), "trigger": trigger, "version": expected_version})
    old = session.get(MemorySituationRequest, (setting.id, request_key))
    if old is not None:
        if old.request_digest != digest:
            raise MemoryConflictError("situation_request_conflict")
        _resume_error(session, old.run_id)
        return old
    if config.version != expected_version or current.version != setting.version:
        raise MemoryConflictError("situation_settings_version_conflict")
    if trigger == "scheduled" and (not config.daily_enabled or config.next_due_at is None or utc_instant(config.next_due_at) > utc_instant(now)):
        raise MemoryConflictError("situation_schedule_not_due")
    if trigger == "quit" and not config.shutdown_apply_enabled:
        raise MemoryConflictError("situation_shutdown_disabled")
    active = session.scalar(select(MemorySituationApplyRun).where(
        MemorySituationApplyRun.scope_setting_id == setting.id,
        MemorySituationApplyRun.state.in_(("pending", "running", "deferred", "error")),
    ).order_by(MemorySituationApplyRun.created_at, MemorySituationApplyRun.id).limit(1))
    if active is not None:
        _resume_error(session, active.id)
    cutoff_at = utc_instant(config.next_due_at) if trigger == "scheduled" else None
    pending = select(func.max(MemorySituationReceipt.sequence)).where(
        MemorySituationReceipt.scope_setting_id == setting.id,
        MemorySituationReceipt.state == "pending")
    if cutoff_at is not None:
        pending = pending.where(MemorySituationReceipt.captured_at <= cutoff_at)
    cutoff = session.scalar(pending)
    if active is None and cutoff is not None:
        active = MemorySituationApplyRun(id=str(uuid4()), scope_setting_id=setting.id,
            trigger=trigger, request_identity=request_key, cutoff_sequence=cutoff, cursor=0,
            settings_snapshot={"scope_version": setting.version, "version": config.version,
                "local_time": config.local_time, "timezone": config.timezone,
                "cutoff_at": cutoff_at.isoformat() if cutoff_at else None,
                "due_at": config.next_due_at.isoformat() if config.next_due_at else None},
            state="pending", created_at=now)
        session.add(active)
        session.flush()
    receipt = MemorySituationRequest(scope_setting_id=setting.id, request_key=request_key,
        request_digest=digest, run_id=active.id if active else None,
        result_code="accepted" if active else "empty", created_at=now)
    session.add(receipt)
    if trigger == "scheduled":
        config.next_due_at = next_due(now, config.local_time, config.timezone)
    session.flush()
    return receipt


def _resume_error(session, run_id):
    # An explicit retry reuses its durable cutoff. It never starts a replacement
    # run over arrivals accepted after that cutoff.
    if run_id:
        session.execute(update(MemorySituationApplyRun).where(
            MemorySituationApplyRun.id == run_id, MemorySituationApplyRun.state == "error",
        ).values(state="deferred", error_code=None, lease_token=None, lease_until=None))


def claim_run(session, run_id, *, now, lease_seconds=30):
    token = str(uuid4())
    changed = session.execute(update(MemorySituationApplyRun).where(
        MemorySituationApplyRun.id == run_id,
        MemorySituationApplyRun.state.in_(("pending", "running", "deferred")),
        (MemorySituationApplyRun.lease_until.is_(None)) | (MemorySituationApplyRun.lease_until <= now),
    ).values(state="running", lease_token=token, lease_until=now + timedelta(seconds=lease_seconds),
        attempts=MemorySituationApplyRun.attempts + 1))
    return token if changed.rowcount == 1 else None


def require_run_fence(session, run_id, token, now):
    row = session.get(MemorySituationApplyRun, run_id, populate_existing=True)
    if (row is None or row.state != "running" or row.lease_token != token
        or row.lease_until is None or utc_instant(row.lease_until) <= utc_instant(now)):
        raise MemoryConflictError("situation_run_fence_lost")
    return row
