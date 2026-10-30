"""Durable final input journal on the caller's short database transaction."""
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.models.activity_situation import MemorySituationManifest
from app.domains.memory.models.experience import MemoryExperienceInput
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.exceptions import MemoryConflictError


def record_input(session, manifest, state, *, outcome=None, now=None):
    if state not in {"prepared","submission_uncertain","received","effect_committed","failed","cancelled"}:
        raise ValueError("memory_input_state_invalid")
    now=now or datetime.now(UTC)
    setting=session.get(MemoryScopeSettingModel,manifest.snapshot.setting_id)
    scope=manifest.snapshot.scope
    if (setting is None or not setting.enabled or setting.version!=manifest.snapshot.scope_version
            or (setting.owner_id,setting.world_id,setting.subject_world_character_id)
                !=(scope.owner_id,scope.world_id,scope.subject_world_character_id)):
        raise MemoryConflictError("situation_activation_closed")
    payload=manifest.to_dict();digest=stable_digest(payload)
    values=dict(id=digest,scope_setting_id=setting.id,call_identity=manifest.call_identity,
        content_digest=digest,payload=payload,created_at=now)
    query=select(MemorySituationManifest).where(MemorySituationManifest.scope_setting_id==setting.id,
        MemorySituationManifest.call_identity==manifest.call_identity)
    stored=session.scalar(query)
    if stored is None:
        if session.get_bind().dialect.name=="postgresql":
            session.execute(pg_insert(MemorySituationManifest).values(**values)
                .on_conflict_do_nothing(constraint="uq_situation_manifest_call"))
            stored=session.scalar(query)
        else:
            stored=MemorySituationManifest(**values);session.add(stored);session.flush()
    if stored.content_digest!=digest:
        raise MemoryConflictError("situation_manifest_content_conflict")
    input_values=dict(manifest_id=digest,scope_setting_id=setting.id,state=state,
        outcome=outcome or {},captured_at=now,updated_at=now)
    if session.get_bind().dialect.name=="postgresql":
        session.execute(pg_insert(MemoryExperienceInput).values(**input_values)
            .on_conflict_do_nothing(index_elements=["manifest_id"]))
    row=session.scalar(select(MemoryExperienceInput).where(
        MemoryExperienceInput.manifest_id==digest).with_for_update())
    if row is None:
        row=MemoryExperienceInput(**input_values)
        session.add(row)
    elif row.state not in {"effect_committed","failed","cancelled"} and (
        {"prepared":0,"submission_uncertain":1,"received":2}.get(state,3)
        >= {"prepared":0,"submission_uncertain":1,"received":2}.get(row.state,3)):
        # Network replay cannot regress a durable outcome or confirmed receipt.
        row.state=state;row.updated_at=now
        if outcome is not None:row.outcome=outcome
    session.flush()
    return row


def record_terminal(session, call_identity, state, *, reason, now=None):
    """Join the existing fenced terminal transaction, without generating memory.

    Cancellation/failure describes the local workflow outcome. It does not
    pretend that an uncertain provider submission was never delivered.
    """
    if state not in {"failed", "cancelled"}:
        raise ValueError("memory_input_terminal_state_invalid")
    row=session.scalar(select(MemoryExperienceInput).join(MemorySituationManifest,
        MemorySituationManifest.id==MemoryExperienceInput.manifest_id).where(
            MemorySituationManifest.call_identity==call_identity).with_for_update())
    if row is None or row.state in {"effect_committed","failed","cancelled"}:
        return
    row.outcome={**row.outcome,"local_outcome":state,"reason":reason,"delivery_state":row.state}
    row.state=state;row.updated_at=now or datetime.now(UTC)
    session.flush()
