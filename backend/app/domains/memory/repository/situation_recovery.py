"""Owner recovery on canonical receipts; no provider, source edits or commits."""
from dataclasses import asdict
from sqlalchemy import delete, select, update

from app.core.calendar import utc_instant
from app.domains.memory.contracts.activity_situation import stable_digest, VALIDATION_REVISION
from app.domains.memory.contracts.items import normalize_memory_idempotency_key
from app.domains.memory.exceptions import MemoryConflictError, MemoryNotFoundError
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import (
    MemorySituationApplyRun, MemorySituationManifest, MemorySituationReceipt, MemorySituationRequest,
    MemoryActivitySituationInfo,
    MemorySituationRecheckAttempt,
)


def active_run(session, setting_id):
    return session.scalar(select(MemorySituationApplyRun).where(
        MemorySituationApplyRun.scope_setting_id == setting_id,
        MemorySituationApplyRun.state.in_(("pending", "running", "deferred", "error")),
    ).order_by(MemorySituationApplyRun.created_at, MemorySituationApplyRun.id).limit(1))


def live_scope_lease(session, setting_id, *, now):
    return session.scalar(select(MemorySituationApplyRun.id).where(
        MemorySituationApplyRun.scope_setting_id == setting_id,
        MemorySituationApplyRun.state == "running", MemorySituationApplyRun.lease_token.is_not(None),
        MemorySituationApplyRun.lease_until > utc_instant(now),
    ).limit(1)) is not None


def discard(session, setting, *, sequence, expected_version, request_key, now):
    normalize_memory_idempotency_key(request_key)
    digest = stable_digest({"scope": asdict(setting.scope), "operation": "discard",
        "receipt_sequence": sequence, "receipt_version": expected_version})
    session.execute(update(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id == setting.id).values(
        id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    previous = session.get(MemorySituationRequest, (setting.id, request_key))
    if previous is not None:
        if previous.request_digest != digest:
            raise MemoryConflictError("situation_request_conflict")
        return previous
    receipt = session.get(MemorySituationReceipt, sequence, populate_existing=True)
    if receipt is None or receipt.scope_setting_id != setting.id:
        raise MemoryNotFoundError("situation_receipt_not_found")
    if receipt.state == "discarded":
        request = MemorySituationRequest(scope_setting_id=setting.id, request_key=request_key,
            request_digest=digest, run_id=None, result_code="already_discarded", created_at=now)
        session.add(request)
        session.flush()
        return request
    if live_scope_lease(session, setting.id, now=now):
        raise MemoryConflictError("situation_scope_busy")
    if (receipt.state != "blocked" or receipt.state_version != expected_version or receipt.applied_item_id is not None
            or session.scalar(select(MemoryActivitySituationInfo.memory_item_id).where(
                MemoryActivitySituationInfo.receipt_sequence == sequence).limit(1)) is not None):
        raise MemoryConflictError("situation_receipt_version_conflict")
    manifest_id = receipt.manifest_id
    queued = active_run(session, setting.id)
    if (queued is not None and queued.work_kind == "blocked_recheck"
        and queued.cursor < sequence <= queued.cutoff_sequence
        and queued.settings_snapshot.get("receipt_sequence") in {None, sequence}):
        # Record the cancelled frozen candidate under the same scope lock. The
        # resumed consumer selects only blocked rows, so it cannot revive this
        # receipt or count the owner's discard as an applied memory.
        session.add(MemorySituationRecheckAttempt(run_id=queued.id, receipt_sequence=sequence,
            validation_revision=queued.settings_snapshot.get("validation_revision", VALIDATION_REVISION),
            outcome="discarded", reason="situation_discarded", previous_run_id=receipt.run_id,
            previous_state=receipt.state, previous_error_code=receipt.error_code, applied_item_id=None,
            before_version=expected_version, after_version=expected_version + 1, created_at=now))
        queued.skipped_count += 1
    changed = session.execute(update(MemorySituationReceipt).where(
        MemorySituationReceipt.sequence == sequence, MemorySituationReceipt.scope_setting_id == setting.id,
        MemorySituationReceipt.state == "blocked", MemorySituationReceipt.state_version == expected_version,
    ).values(state="discarded", state_version=expected_version + 1, discarded_at=now, discard_request_key=request_key,
        description=None, result={}, manifest_id=None).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise MemoryConflictError("situation_receipt_version_conflict")
    session.expire(receipt)
    from app.domains.memory.models.situation_result_binding import MemorySituationResultBinding
    session.execute(delete(MemorySituationResultBinding).where(MemorySituationResultBinding.receipt_sequence == sequence))
    shared = session.scalar(select(MemorySituationReceipt.sequence).where(
        MemorySituationReceipt.manifest_id == manifest_id).limit(1))
    if shared is None:
        session.execute(delete(MemorySituationManifest).where(MemorySituationManifest.id == manifest_id))
    request = MemorySituationRequest(scope_setting_id=setting.id, request_key=request_key,
        request_digest=digest, run_id=None, result_code="discarded", created_at=now)
    session.add(request)
    session.flush()
    return request
