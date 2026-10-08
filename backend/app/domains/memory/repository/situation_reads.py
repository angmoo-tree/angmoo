"""Situation lineage and privacy, including owner-authored corrections."""
from sqlalchemy import select

from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, DeliveredSourceEntry, SITUATION_POLICY
from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo, MemorySituationReceipt, MemorySituationManifest
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_validation import restore_context


def situation_origin(session, item):
    visited = set()
    row = item
    for _ in range(32):
        if row.id in visited:
            return None
        visited.add(row.id)
        info = session.get(MemoryActivitySituationInfo, row.id)
        if info is not None:
            return info
        row = session.scalar(select(MemoryItem).where(MemoryItem.superseded_by_id == row.id,
            MemoryItem.owner_id == item.owner_id, MemoryItem.world_id == item.world_id,
            MemoryItem.subject_world_character_id == item.subject_world_character_id))
        if row is None:
            return None
    return None


def correction_evidence(session, reader, scope, item, now):
    info = situation_origin(session, item)
    if info is None:
        return None
    if not situation_accessible(session, reader, scope, item, info, now, ancestors=frozenset()):
        from app.domains.memory.exceptions import MemoryConflictError
        raise MemoryConflictError("memory_correction_source_unavailable")
    from app.domains.memory.models.activity_situation import MemoryActivitySituationSource
    manifest, _ = read_manifest(session, info)
    evidence = {}
    for row in session.scalars(select(MemoryActivitySituationSource).where(
            MemoryActivitySituationSource.memory_item_id == info.memory_item_id)):
        entry = DeliveredSourceEntry.from_dict(row.source)
        access = reader.validate_situation_source(manifest, entry, now=now)
        if access.evidence is not None:
            evidence[(entry.source_type, entry.source_id)] = access.evidence
    return tuple(evidence.values())


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


def representation(session, item):
    if situation_origin(session, item) is not None:
        return "activity_situation_v1"
    from app.domains.memory.models.episode import MemoryEpisodeInfo
    return "episode_v1" if session.get(MemoryEpisodeInfo, item.id) is not None else "legacy_summary"


def read_manifest(session, info):
    receipt = session.get(MemorySituationReceipt, info.receipt_sequence)
    if receipt is None or receipt.state != "applied" or receipt.policy_version != SITUATION_POLICY:
        return None
    try:
        context = restore_context(session, receipt)
    except (ValueError, TypeError, KeyError):
        return None
    return context, context.result_sources


def situation_accessible(session, reader, scope, item, info, now, *, ancestors):
    if info.policy_version != SITUATION_POLICY or item.id in ancestors:
        return False
    validate = getattr(reader, "validate_situation_source", None)
    if validate is None:
        return False
    try:
        material = read_manifest(session, info)
        if material is None:
            return False
        manifest, results = material
        if manifest.snapshot.scope != scope or manifest.private_thread_id != item.thread_id:
            return False
        entries = (*manifest.sources, *results)
        if not entries:
            return False
        for entry in entries:
            access = validate(manifest, entry, now=now, ancestors=ancestors | {item.id})
            if access.state not in {"available", "deleted"} or (entry.role == "prior" and access.state == "deleted"):
                return False
        return True
    except (ValueError, TypeError, KeyError, RecursionError):
        return False
