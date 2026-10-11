"""Situation lineage and privacy, including owner-authored corrections."""
from sqlalchemy import select

from app.domains.memory.contracts.activity_situation import DeliveredInputManifest, DeliveredSourceEntry, SITUATION_POLICY
from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo, MemoryActivitySituationSource, MemorySituationReceipt, MemorySituationManifest
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.situation_validation import restore_context


def situation_origin(session, item, *, validation=None):
    if validation is not None and item.id in validation.origins:
        return validation.origins[item.id]
    get = session.get if validation is None else validation.get
    visited = set()
    row = item
    while row is not None:
        if row.id in visited:
            raise ValueError("situation_correction_lineage_invalid")
        visited.add(row.id)
        info = get(MemoryActivitySituationInfo, row.id)
        if info is not None:
            if validation is not None:
                validation.origins[item.id] = info
            return info
        sources = validation.collections.get(("situation_sources", row.id)) if validation is not None else None
        if sources is None:
            sources = tuple(session.scalars(select(MemoryActivitySituationSource).where(
                MemoryActivitySituationSource.memory_item_id == row.id).limit(1)))
        if sources:
            # A lost origin cannot turn remaining situation proof into legacy access.
            raise ValueError("situation_correction_lineage_invalid")
        parents = (validation.collections.get(("correction_parents", row.id)) if validation is not None else None)
        if parents is None:
            parents = tuple(session.scalars(select(MemoryItem).where(MemoryItem.superseded_by_id == row.id)))
        parents = tuple(parent for parent in parents if (parent.owner_id, parent.world_id, parent.subject_world_character_id) == (item.owner_id, item.world_id, item.subject_world_character_id))
        if len(parents) > 1:
            raise ValueError("situation_correction_lineage_invalid")
        row = parents[0] if parents else None
        if row is None:
            if validation is not None:
                validation.origins[item.id] = None
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


def representation(session, item, *, validation=None):
    if situation_origin(session, item, validation=validation) is not None:
        return "activity_situation_v1"
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
    if info.policy_version != SITUATION_POLICY or item.id in ancestors:
        return False
    validate = getattr(reader, "validate_situation_source", None)
    if validate is None:
        return False
    from app.domains.memory.contracts.access_validation import MemoryAccessValidation
    validation = validation if validation is not None else MemoryAccessValidation(session, now)
    validation.check_context(session, now)
    try:
        material = read_manifest(session, info, validation=validation)
        if material is None:
            return False
        manifest, results = material
        if manifest.snapshot.scope != scope or manifest.private_thread_id != item.thread_id:
            return False
        entries = (*manifest.sources, *results)
        if not entries:
            return False
        for entry in entries:
            access = validate(manifest, entry, now=now, ancestors=ancestors | {item.id}, validation=validation)
            if access.state not in {"available", "deleted"} or (entry.role == "prior" and access.state == "deleted"):
                return False
        return True
    except (ValueError, TypeError, KeyError, RecursionError):
        return False
