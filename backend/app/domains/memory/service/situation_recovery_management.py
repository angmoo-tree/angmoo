"""Owner-only, bounded recovery API use cases with explicit transaction ownership."""
import base64
import json
from datetime import UTC, datetime
from sqlalchemy import func, select

from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.models.batch import MemoryActivationEpoch
from app.domains.memory.repository.situation_recovery import live_scope_lease, discard
from app.domains.memory.repository.situation_runs import request_run
from app.domains.memory.repository.situation_validation import restore_context
from app.domains.memory.repository.experience import validate_captured_sources
from app.domains.memory.schemas.situation import MemoryUnsavedExperiencesRead, MemorySituationDiscardRead
from app.domains.memory.service.situation_management import _ensure, read


def _reason(code):
    code = code or ""
    if code == "situation_description_language_only":
        return "description_language_only"
    if "activation" in code:
        return "activation_closed"
    if "description" in code or "policy" in code:
        return "description_invalid"
    if "result" in code or "success" in code:
        return "result_invalid"
    if "proof" in code or "manifest" in code or "integrity" in code or "basis" in code or "binding" in code:
        return "proof_unavailable"
    if "changed" in code:
        return "source_changed"
    if "forbidden" in code or "scope" in code:
        return "access_unavailable"
    return "validation_failed"


def _cursor(value, setting_id):
    try:
        decoded = json.loads(base64.urlsafe_b64decode(value.encode() + b"=" * (-len(value) % 4)))
        if (set(decoded) != {"scope", "before", "cutoff"} or decoded["scope"] != stable_digest(setting_id)
            or type(decoded["before"]) is not int or type(decoded["cutoff"]) is not int
            or not 0 < decoded["before"] <= decoded["cutoff"]):
            raise ValueError()
        return decoded["before"], decoded["cutoff"]
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise MemoryValidationError("situation_cursor_invalid") from None


def list_unsaved(*, scope, db, workflows, cursor=None, limit=20):
    if not 1 <= limit <= 100:
        raise MemoryValidationError("situation_page_size_invalid")
    memory = workflows.batch_repository(db).memory
    memory.validate_scope(scope)
    setting = memory.get_scope_setting(scope)
    status = read(scope=scope, db=db, workflows=workflows)
    if setting is None:
        return MemoryUnsavedExperiencesRead(scope=status.scope, items=[], next_cursor=None,
            blocked_count=0, scope_busy=False, can_recheck=False)
    query = select(MemorySituationReceipt).where(MemorySituationReceipt.scope_setting_id == setting.id,
        MemorySituationReceipt.state == "blocked")
    cutoff = db.scalar(select(func.max(MemorySituationReceipt.sequence)).where(
        MemorySituationReceipt.scope_setting_id == setting.id, MemorySituationReceipt.state == "blocked")) or 0
    if cursor:
        before, cutoff = _cursor(cursor, setting.id)
        query = query.where(MemorySituationReceipt.sequence < before)
    rows = list(db.scalars(query.where(MemorySituationReceipt.sequence <= cutoff).order_by(
        MemorySituationReceipt.sequence.desc()).limit(limit + 1)))
    now, items = datetime.now(UTC), []
    discard_busy = live_scope_lease(db, setting.id, now=now)
    for row in rows[:limit]:
        visible = False
        try:
            context = restore_context(db, row)
            # Owner scope and persisted receipt integrity authorize the saved
            # description. Later SNS/Chat changes are not memory revocations.
            visible = context.snapshot.scope == scope and bool(validate_captured_sources(
                db, context, context.result_sources, row, now=now))
        except (ValueError, TypeError, KeyError):
            pass
        epoch = db.get(MemoryActivationEpoch, row.activation_epoch)
        enabled = setting.enabled and row.scope_version == setting.version and epoch is not None and epoch.closed_at is None and epoch.scope_setting_id == setting.id
        items.append({"receipt_sequence": row.sequence, "state_version": row.state_version,
            "occurred_at": row.occurred_at, "description": row.description[:1000] if visible and row.description else None,
            "reason": _reason(row.error_code), "can_recheck": bool(enabled and not status.scope_busy),
            "can_discard": not discard_busy and row.applied_item_id is None})
    next_cursor = None
    if len(rows) > limit:
        next_cursor = base64.urlsafe_b64encode(json.dumps({"scope": stable_digest(setting.id),
            "before": rows[limit - 1].sequence, "cutoff": cutoff}, separators=(",", ":")).encode()).decode().rstrip("=")
    return MemoryUnsavedExperiencesRead(scope=status.scope, items=items, next_cursor=next_cursor,
        blocked_count=status.blocked_count, scope_busy=status.scope_busy, can_recheck=status.can_recheck)


def recheck(*, scope, db, workflows, data, sequence=None):
    now = datetime.now(UTC)
    try:
        setting, _, _ = _ensure(db, workflows, scope, now)
        request_run(db, setting, trigger="manual", work_kind="blocked_recheck",
            request_key=data.idempotency_key, expected_version=data.expected_version, now=now,
            receipt_sequence=sequence, expected_receipt_version=getattr(data, "expected_receipt_version", None))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return read(scope=scope, db=db, workflows=workflows, request_key=data.idempotency_key)


def discard_experience(*, scope, db, workflows, data, sequence):
    now = datetime.now(UTC)
    try:
        memory = workflows.batch_repository(db).memory
        memory.validate_scope(scope)
        setting = memory.get_scope_setting(scope)
        if setting is None:
            raise MemoryConflictError("situation_scope_removed")
        resolved = discard(db, setting, sequence=sequence, expected_version=data.expected_receipt_version,
            request_key=data.idempotency_key, now=now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    receipt = db.get(MemorySituationReceipt, sequence)
    status = read(scope=scope, db=db, workflows=workflows)
    return MemorySituationDiscardRead(scope=status.scope, receipt_sequence=sequence, state=receipt.state,
        state_version=receipt.state_version, discarded_at=receipt.discarded_at, result=resolved.result_code,
        resolved_request_key=resolved.request_key, pending_count=status.pending_count, blocked_count=status.blocked_count)
