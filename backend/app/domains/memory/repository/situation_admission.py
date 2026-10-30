"""Join the actual activity writer's transaction. Never commit or call a provider."""
from dataclasses import asdict
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

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

    PostgreSQL shares the policy guard across independent admissions. Unique
    constraints arbitrate duplicate identities, with content checked on reuse.
    The caller still owns the effect and receipt in one transaction.
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
    if manifest.version < 3:
        payload.pop("thought",None)
        payload.pop("experience_state",None)
        payload.pop("failure_reason",None)
        if result.experience_state != "action_succeeded":
            raise MemoryValidationError("situation_failure_requires_snapshot")
    payload["result_sources"] = [entry.to_dict(version=manifest.version) for entry in result.result_sources]
    payload["occurred_at"] = result.occurred_at.isoformat()
    content_digest = stable_digest({"manifest": manifest.to_dict(), "draft": asdict(draft), "result": payload})
    postgres = session.get_bind().dialect.name == "postgresql"
    scope_predicates = (
        MemoryScopeSettingModel.id == snapshot.setting_id,
        MemoryScopeSettingModel.owner_id == snapshot.scope.owner_id,
        MemoryScopeSettingModel.world_id == snapshot.scope.world_id,
        MemoryScopeSettingModel.subject_world_character_id == snapshot.scope.subject_world_character_id,
    )
    if postgres:
        # A real policy UPDATE/delete must wait until this effect commits. A
        # shared lock creates no fake policy revision or needless SSI writer.
        # Stale snapshots still raise 40001 through the caller's bounded retry.
        found = session.scalar(select(MemoryScopeSettingModel.id).where(
            *scope_predicates).with_for_update(read=True)) is not None
    else:
        locked = session.execute(update(MemoryScopeSettingModel).where(
            *scope_predicates).values(id=MemoryScopeSettingModel.id,
                updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
        found = locked.rowcount == 1
    if not found:
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
    manifest_query = select(MemorySituationManifest).where(
        MemorySituationManifest.scope_setting_id == snapshot.setting_id,
        MemorySituationManifest.call_identity == manifest.call_identity,
    )
    stored = session.scalar(manifest_query)
    if stored is None:
        manifest_values = dict(id=manifest_digest, scope_setting_id=snapshot.setting_id,
            call_identity=manifest.call_identity, content_digest=manifest_digest,
            payload=manifest.to_dict(), created_at=now)
        if postgres:
            stored = session.scalar(pg_insert(MemorySituationManifest).values(**manifest_values)
                .on_conflict_do_nothing(constraint="uq_situation_manifest_call")
                .returning(MemorySituationManifest))
            if stored is None:
                stored = session.execute(manifest_query).scalar_one()
        else:
            stored = MemorySituationManifest(**manifest_values)
            session.add(stored)
            session.flush()
    if stored.content_digest != manifest_digest:
        raise MemoryConflictError("situation_manifest_content_conflict")
    if manifest.version >= 3:
        from app.domains.memory.models.experience import MemoryExperienceInput
        journal=session.scalar(select(MemoryExperienceInput).where(
            MemoryExperienceInput.manifest_id==manifest_digest).with_for_update())
        if journal is not None:
            if journal.state != "effect_committed":
                journal.state="failed" if result.experience_state=="observed_action_failed" else "effect_committed"
            outcome={"logical_activity_id":result.logical_activity_id,"lane":result.lane,
                "target_key":result.target_key,"effects":payload["effects"],
                "experience_state":result.experience_state,"failure_reason":result.failure_reason}
            journal.outcome={"targets":{**journal.outcome.get("targets",{}),result.target_key:outcome}}
            journal.updated_at=now
    if manifest.version >= 2:
        payload["_admission"] = {"draft": asdict(draft), "manifest_digest": manifest_digest,
            "result_digest": stable_digest(payload)}
    setting = session.get(MemoryScopeSettingModel, snapshot.setting_id, populate_existing=True)
    epoch = session.get(MemoryActivationEpoch, snapshot.activation_epoch, populate_existing=True)
    inactive = (not setting.enabled or setting.version != snapshot.scope_version or epoch is None
        or epoch.scope_setting_id != setting.id or epoch.closed_at is not None)
    code = "situation_activation_closed" if inactive else result.eligibility_code or draft.error_code
    state = "skipped" if inactive or code == "situation_no_action" else "blocked" if code or draft.status != "valid" else "pending"
    receipt_values = dict(scope_setting_id=setting.id, logical_activity_id=result.logical_activity_id,
        lane=result.lane, target_key=result.target_key, manifest_id=stored.id,
        policy_version=snapshot.policy_version, activation_epoch=snapshot.activation_epoch,
        scope_version=snapshot.scope_version, content_digest=content_digest,
        description=draft.description if draft.status == "valid" else None,
        description_status=draft.status, result=payload, occurred_at=result.occurred_at,
        captured_at=now, state=state, error_code=code)
    if postgres:
        row = session.scalar(pg_insert(MemorySituationReceipt).values(**receipt_values)
            .on_conflict_do_nothing(constraint="uq_situation_activity_target")
            .returning(MemorySituationReceipt))
        if row is None:
            row = session.execute(select(MemorySituationReceipt).where(
                MemorySituationReceipt.scope_setting_id == setting.id,
                MemorySituationReceipt.logical_activity_id == result.logical_activity_id,
                MemorySituationReceipt.lane == result.lane,
                MemorySituationReceipt.target_key == result.target_key)).scalar_one()
        if row.content_digest != content_digest:
            raise MemoryConflictError("situation_receipt_content_conflict")
        return row
    row = MemorySituationReceipt(**receipt_values)
    session.add(row)
    session.flush()
    return row


def confirm_committed_result(session, *, scope_setting_id, logical_activity_id, lane, target_key,
                             manifest_digest, source_type, source_id, effect_kind):
    """Read an existing effect binding, including invalid auxiliary descriptions.

    This does not create a receipt or change historical description/state.
    """
    row = session.scalar(select(MemorySituationReceipt).where(
        MemorySituationReceipt.scope_setting_id == scope_setting_id,
        MemorySituationReceipt.logical_activity_id == logical_activity_id,
        MemorySituationReceipt.lane == lane, MemorySituationReceipt.target_key == target_key))
    if row is None or row.manifest_id != manifest_digest:
        raise MemoryConflictError("situation_committed_receipt_missing")
    stored = session.get(MemorySituationManifest, manifest_digest, populate_existing=True)
    result = dict(row.result)
    admission = result.pop("_admission", None)
    draft = admission.get("draft") if admission else asdict(SituationDraft(row.target_key, row.description, row.description_status))
    if (stored is None or stored.scope_setting_id != scope_setting_id
            or stable_digest(stored.payload) != manifest_digest
            or stable_digest({"manifest": stored.payload, "draft": draft, "result": result}) != row.content_digest
            or result.get("logical_activity_id") != logical_activity_id or result.get("lane") != lane
            or result.get("target_key") != target_key
            or result.get("planned_effects") != [effect_kind]
            or result.get("effects") != [{"kind": effect_kind, "source_type": source_type, "source_id": source_id, "status": "succeeded"}]):
        raise MemoryConflictError("situation_committed_receipt_binding_invalid")
    return row
