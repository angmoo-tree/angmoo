"""Join the actual activity writer's transaction. Never commit or call a provider."""
from dataclasses import asdict
from datetime import datetime
from sqlalchemy import select, update

from app.domains.memory.contracts.activity_situation import (
    CommittedActivityResult, DeliveredInputManifest, SituationDraft, SituationPolicySnapshot, stable_digest,
)
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.batch import MemoryActivationEpoch
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemorySituationManifest, MemorySituationReceipt
from app.domains.memory.policies.situation_output import parse_description


def snapshot_for(session, scope: MemoryScope, *, locale: str, environment_revision: int = 0):
    """Called at activity admission; callers persist this snapshot across retries."""
    row = session.scalar(select(MemoryScopeSettingModel).where(
        MemoryScopeSettingModel.owner_id == scope.owner_id,
        MemoryScopeSettingModel.world_id == scope.world_id,
        MemoryScopeSettingModel.subject_world_character_id == scope.subject_world_character_id,
    ))
    if row is None or not row.enabled:
        return None
    epoch = session.scalar(select(MemoryActivationEpoch).where(
        MemoryActivationEpoch.scope_setting_id == row.id,
        MemoryActivationEpoch.scope_version == row.version,
        MemoryActivationEpoch.closed_at.is_(None),
    ))
    if epoch is None:
        raise MemoryConflictError("situation_activation_missing")
    return SituationPolicySnapshot(scope, row.id, epoch.id, row.version, locale, environment_revision)


def admit(session, *, manifest: DeliveredInputManifest, draft: SituationDraft,
          result: CommittedActivityResult, now: datetime) -> MemorySituationReceipt | None:
    """Receipt failure aborts the activity transaction. A deleted scope is a no-op.

    The scope row lock also serializes duplicate admissions before reading their
    unique identities. No IntegrityError blanket catch can hide a failed writer.
    """
    snapshot = manifest.snapshot
    if draft.target_key != result.target_key:
        raise MemoryValidationError("situation_target_mismatch")
    entries = (*manifest.sources, *result.result_sources)
    if (len({entry.ordinal for entry in entries}) != len(entries)
        or any(entry.world_id != snapshot.scope.world_id or entry.thread_id not in {None, manifest.private_thread_id}
            or entry.role not in {"committed_result", "thought"}
            or entry.target_key != result.target_key for entry in result.result_sources)):
        raise MemoryValidationError("situation_result_source_mismatch")
    valid = parse_description(draft.description, target_key=draft.target_key)
    if draft.status == "valid" and valid.status != "valid":
        raise MemoryValidationError("situation_draft_invalid")
    payload = asdict(result)
    payload["occurred_at"] = result.occurred_at.isoformat()
    content_digest = stable_digest({"manifest": manifest.to_dict(), "draft": asdict(draft), "result": payload})
    locked = session.execute(update(MemoryScopeSettingModel).where(
        MemoryScopeSettingModel.id == snapshot.setting_id,
        MemoryScopeSettingModel.owner_id == snapshot.scope.owner_id,
        MemoryScopeSettingModel.world_id == snapshot.scope.world_id,
        MemoryScopeSettingModel.subject_world_character_id == snapshot.scope.subject_world_character_id,
    ).values(id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    if locked.rowcount != 1:
        if session.get(MemoryScopeSettingModel, snapshot.setting_id) is not None:
            raise MemoryConflictError("situation_scope_mismatch")
        return None
    previous = session.scalar(select(MemorySituationReceipt).where(
        MemorySituationReceipt.scope_setting_id == snapshot.setting_id,
        MemorySituationReceipt.logical_activity_id == result.logical_activity_id,
        MemorySituationReceipt.lane == result.lane,
        MemorySituationReceipt.target_key == result.target_key,
    ))
    if previous is not None:
        if previous.content_digest != content_digest:
            raise MemoryConflictError("situation_receipt_content_conflict")
        return previous
    manifest_digest = stable_digest(manifest.to_dict())
    stored = session.scalar(select(MemorySituationManifest).where(
        MemorySituationManifest.scope_setting_id == snapshot.setting_id,
        MemorySituationManifest.call_identity == manifest.call_identity,
    ))
    if stored is None:
        stored = MemorySituationManifest(id=manifest_digest, scope_setting_id=snapshot.setting_id,
            call_identity=manifest.call_identity, content_digest=manifest_digest,
            payload=manifest.to_dict(), created_at=now)
        session.add(stored)
        session.flush()
    elif stored.content_digest != manifest_digest:
        raise MemoryConflictError("situation_manifest_content_conflict")
    setting = session.get(MemoryScopeSettingModel, snapshot.setting_id, populate_existing=True)
    epoch = session.get(MemoryActivationEpoch, snapshot.activation_epoch, populate_existing=True)
    inactive = (not setting.enabled or setting.version != snapshot.scope_version or epoch is None
        or epoch.scope_setting_id != setting.id or epoch.closed_at is not None)
    code = "situation_activation_closed" if inactive else result.eligibility_code or draft.error_code
    state = "skipped" if inactive or code == "situation_no_action" else "blocked" if code or draft.status != "valid" else "pending"
    row = MemorySituationReceipt(scope_setting_id=setting.id, logical_activity_id=result.logical_activity_id,
        lane=result.lane, target_key=result.target_key, manifest_id=stored.id,
        policy_version=snapshot.policy_version, activation_epoch=snapshot.activation_epoch,
        scope_version=snapshot.scope_version, content_digest=content_digest,
        description=draft.description if draft.status == "valid" else None,
        description_status=draft.status, result=payload, occurred_at=result.occurred_at,
        captured_at=now, state=state, error_code=code)
    session.add(row)
    session.flush()
    return row
