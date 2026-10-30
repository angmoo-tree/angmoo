"""Situation lineage and privacy, including owner-authored corrections."""
from sqlalchemy import select

from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, DeliveredSourceEntry, SITUATION_POLICY
from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo, MemoryActivitySituationSource, MemorySituationReceipt, MemorySituationManifest
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_validation import restore_context


def situation_origin(session, item, *, validation=None):
    # Corrections and migration own their direct metadata; no ancestry hydration.
    if validation is not None:
        return validation.get(MemoryActivitySituationInfo, item.id)
    return session.get(MemoryActivitySituationInfo, item.id)

def correction_evidence(session, reader, scope, item, now, *, validation=None):
    from app.domains.memory.repository.experience import accessible, stored_evidence
    from app.domains.memory.exceptions import MemoryConflictError
    if not accessible(session, scope, item, now, validation=validation):
        raise MemoryConflictError("memory_correction_source_unavailable")
    return stored_evidence(session, item)

def copy_correction_origin(session, old, replacement):
    """The correction owns its metadata even when retention removes its parent."""
    from app.domains.memory.models.activity_situation import MemoryActivitySituationSource
    info = situation_origin(session, old)
    if info is None:
        return
    session.add(MemoryActivitySituationInfo(memory_item_id=replacement.id,
        receipt_sequence=info.receipt_sequence, policy_version=info.policy_version,
        locale=info.locale, occurred_at=info.occurred_at, thought_reference=info.thought_reference))
    for row in session.scalars(select(MemoryActivitySituationSource).where(
            MemoryActivitySituationSource.memory_item_id == info.memory_item_id)):
        session.add(MemoryActivitySituationSource(memory_item_id=replacement.id,
            ordinal=row.ordinal, evidence_id=None, source=dict(row.source), state=row.state))


def representation(session, item, *, validation=None):
    if situation_origin(session, item, validation=validation) is not None:
        return "activity_situation_v1"
    from app.domains.memory.repository.experience import read_snapshot
    snapshot=read_snapshot(session,item,validation=validation)
    if snapshot is not None and snapshot.payload.get("outcome",{}).get("representation") in {"activity_situation_v1","episode_v1"}:
        return snapshot.payload["outcome"]["representation"]
    from app.domains.memory.models.episode import MemoryEpisodeInfo
    return "episode_v1" if (session.get(MemoryEpisodeInfo, item.id) if validation is None else validation.get(MemoryEpisodeInfo, item.id)) is not None else "legacy_summary"


def read_manifest(session, info, *, validation=None):
    if validation is not None and info.receipt_sequence in validation.restored:
        return validation.restored[info.receipt_sequence]
    receipt = session.get(MemorySituationReceipt, info.receipt_sequence) if validation is None else validation.get(MemorySituationReceipt, info.receipt_sequence)
    if receipt is None or receipt.state != "applied" or receipt.policy_version != SITUATION_POLICY:
        if validation is not None:
            validation.restored[info.receipt_sequence] = None
        return None
    try:
        context = restore_context(session, receipt, validation=validation)
    except (ValueError, TypeError, KeyError):
        if validation is not None:
            validation.restored[info.receipt_sequence] = None
        return None
    material = context, context.result_sources
    if validation is not None:
        validation.restored[info.receipt_sequence] = material
    return material


def situation_accessible(session, reader, scope, item, info, now, *, ancestors, validation=None):
    from app.domains.memory.repository.experience import accessible
    return accessible(session, scope, item, now, validation=validation)
