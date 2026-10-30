"""Immutable experience copies and current memory rights, without source reads."""
from datetime import UTC, datetime
from hashlib import sha256
from sqlalchemy import select
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.contracts.episode_packet import EpisodePacket, EpisodePacketSource, EpisodePacketUnit
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.experience import (
    MemoryExperienceSnapshot, MemoryExperienceDependency, MemoryExperienceTombstone,
)
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.policies.retrievability import item_retrievable

EXPERIENCE_POLICY = "memory-experience-snapshot.v1"
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


def rights_columns():
    from sqlalchemy.orm import load_only
    return load_only(*(getattr(MemoryItem, name) for name in (
        "id", "owner_id", "world_id", "subject_world_character_id", "thread_id",
        "status", "deleted_at", "superseded_by_id", "valid_from", "valid_until")), raiseload=True)


def item_scope(item):
    return MemoryScope(item.owner_id, item.world_id, item.subject_world_character_id)


def scope_value(scope):
    return {"owner_id": scope.owner_id, "world_id": scope.world_id,
            "subject_world_character_id": scope.subject_world_character_id}


def prepare(session, items, now, *, validation, include_snapshots=True):
    """One bounded batch; no prior-memory traversal or live-source lookup."""
    ids = tuple(dict.fromkeys(item.id for item in items))
    from app.domains.memory.repository.access_batch import indexed
    if include_snapshots:
        indexed(validation, MemoryExperienceSnapshot, MemoryExperienceSnapshot.memory_item_id, ids)
    blocked = set(session.scalars(select(MemoryExperienceDependency.memory_item_id).join(
        MemoryExperienceTombstone,
        (MemoryExperienceTombstone.scope_setting_id == MemoryExperienceDependency.scope_setting_id)
        & (MemoryExperienceTombstone.memory_item_id == MemoryExperienceDependency.origin_memory_id)
    ).where(MemoryExperienceDependency.memory_item_id.in_(ids)))) if ids else set()
    blocked.update(session.scalars(select(MemoryExperienceTombstone.memory_item_id).where(
        MemoryExperienceTombstone.memory_item_id.in_(ids))))
    for identifier in ids:
        validation.collections[("experience_revoked", identifier)] = identifier in blocked
    validation.prepared_items.update(ids)


def read_snapshot(session, item, *, validation=None):
    row = session.get(MemoryExperienceSnapshot, item.id) if validation is None else validation.get(MemoryExperienceSnapshot, item.id)
    if row is None:
        return None  # Legacy summary only, never fall back to a source reader.
    payload = row.payload
    if (not isinstance(payload, dict) or row.policy_version != EXPERIENCE_POLICY
            or payload.get("policy") != EXPERIENCE_POLICY or stable_digest(payload) != row.content_digest
            or payload.get("scope") != scope_value(item_scope(item))
            or payload.get("thread_id") != item.thread_id or payload.get("status") != row.status):
        raise ValueError("memory_snapshot_integrity_invalid")
    if not isinstance(payload.get("sources"), list):
        raise ValueError("memory_snapshot_integrity_invalid")
    setting = session.get(MemoryScopeSettingModel,row.scope_setting_id) if validation is None else validation.get(MemoryScopeSettingModel,row.scope_setting_id)
    if setting is None or (setting.owner_id,setting.world_id,setting.subject_world_character_id) != (
            item.owner_id,item.world_id,item.subject_world_character_id):
        raise ValueError("memory_snapshot_integrity_invalid")
    for source in payload.get("sources", ()):
        text = source.get("text")
        if text is not None and (not isinstance(text, str)
                or sha256(text.encode()).hexdigest() != source.get("text_digest")):
            raise ValueError("memory_snapshot_integrity_invalid")
    return row


def accessible(session, scope, item, now, *, validation=None, require_enabled=True, check_snapshot=True, captured=False):
    # A correction/merge supersedes a search candidate, not an already captured
    # experience. Explicit deletion, expiry and tombstone dependencies still revoke it.
    eligible = item_retrievable(item, now)
    if captured and item.status == 'superseded' and item.deleted_at is None:
        expiry = item.valid_until
        start = item.valid_from
        eligible = ((start.replace(tzinfo=UTC) if start.tzinfo is None else start) <= now
                    and (expiry is None or (expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry) > now))
    if item_scope(item) != scope or not eligible:
        return False
    from app.domains.memory.contracts.access_validation import MemoryAccessValidation
    from app.runtime.memory.scope_queries import read_scope_presence
    validation = validation or MemoryAccessValidation(session, now)
    validation.check_context(session, now)
    key = ("experience", scope, require_enabled)
    if key not in validation.scopes:
        setting = session.scalar(select(MemoryScopeSettingModel).where(
            MemoryScopeSettingModel.owner_id == scope.owner_id,
            MemoryScopeSettingModel.world_id == scope.world_id,
            MemoryScopeSettingModel.subject_world_character_id == scope.subject_world_character_id))
        validation.scopes[key] = (setting is not None and (setting.enabled or not require_enabled)
            and all(value is not None for value in read_scope_presence(session, scope)))
    if not validation.scopes[key]:
        return False
    if item.thread_id:
        from app.domains.chat.models import MessageThread
        thread = validation.get(MessageThread,item.thread_id)
        if (thread is None or thread.deleted_at is not None or (thread.requester_id,thread.world_id)!=(scope.owner_id,scope.world_id)
                or scope.subject_world_character_id not in {
                    thread.requester_world_character_id,thread.responding_world_character_id}):
            return False
    # Unknown representation policies remain closed; historical source revisions
    # no longer determine access to a memory owned by this scope.
    from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo
    from app.domains.memory.models.episode import MemoryEpisodeInfo
    from app.domains.memory.contracts.activity_situation import SITUATION_POLICY
    from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION
    from app.domains.memory.contracts.episode import EPISODE_VERSION
    info = validation.get(MemoryActivitySituationInfo, item.id)
    episode = validation.get(MemoryEpisodeInfo, item.id)
    if info is not None and info.policy_version != SITUATION_POLICY:
        return False
    if episode is not None and episode.policy_version not in {ACTIVITY_POLICY_VERSION, EPISODE_VERSION}:
        return False
    if ("experience_revoked", item.id) not in validation.collections:
        prepare(session, (item,), now, validation=validation, include_snapshots=check_snapshot)
    if validation.collections[("experience_revoked", item.id)]:
        return False
    try:
        if check_snapshot:
            read_snapshot(session, item, validation=validation)
    except (ValueError, TypeError, KeyError):
        return False
    return True


def guard_metadata(session, scope, items, now, *, captured=False):
    """Current rights and immutable digest columns; never reload original text."""
    from app.domains.memory.contracts.access_validation import MemoryAccessValidation
    from app.domains.memory.repository.access_batch import prepare_representation
    validation=MemoryAccessValidation(session,now)
    prepare_representation(validation,items)
    prepare(session,items,now,validation=validation,include_snapshots=False)
    digests=dict(session.execute(select(MemoryExperienceSnapshot.memory_item_id,MemoryExperienceSnapshot.content_digest)
        .where(MemoryExperienceSnapshot.memory_item_id.in_(tuple(item.id for item in items)))).all())
    return {item.id:digests.get(item.id,"") for item in items
        if accessible(session,scope,item,now,validation=validation,check_snapshot=False,captured=captured)}


def source_snapshot(entry):
    text = entry.delivered_text
    return {"reference": f"{entry.source_type}:{entry.source_id}",
        "source_type": entry.source_type, "source_id": entry.source_id,
        "source_digest": entry.source_digest, "source_version": entry.source_version,
        "text": text, "text_digest": entry.delivered_digest if text is not None else None,
        "status": "historical_snapshot" if text is not None else "snapshot_unavailable",
        "role": entry.role, "ordinal": entry.ordinal, "author_id": entry.actor_id,
        "author_role": entry.author_role, "counterpart_id": entry.counterpart_id,
        "occurred_at": entry.source_created_at, "payload_path": entry.payload_path,
        "source_ranges": [list(pair) for pair in entry.ranges],
        "delivered_ranges": [list(pair) for pair in entry.delivered_ranges],
        "partial": entry.partial, "coordinate_system": "delivered_fragment"}


def stored_evidence(session, item):
    """Metadata already owned by this memory, never reconstructed source truth."""
    from app.domains.memory.models.items import MemoryItemEvidence
    from app.domains.memory.contracts.provenance import MemorySourceTypeV1
    from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
    return tuple(CanonicalMemoryEvidence(
        MemorySourceTypeV1(row.source_type),row.source_id,row.source_world_id,row.source_digest,
        row.source_created_at,item.summary,True,True,True,True,False,
        actor_world_character_id=row.actor_world_character_id,
        target_world_character_id=row.target_world_character_id,observation_id=row.observation_id,
        source_event_id=row.source_event_id,counterpart_world_character_id=item.counterpart_world_character_id,
        thread_id=item.thread_id) for row in session.scalars(select(MemoryItemEvidence).where(
            MemoryItemEvidence.memory_item_id==item.id)))


def validate_captured_sources(session, context, result_sources, receipt, *, now):
    """Receipt integrity was checked by restore_admission; check memory rights."""
    from app.domains.memory.contracts.situation_validation import SituationSourceAccess
    from app.domains.memory.contracts.provenance import MemorySourceTypeV1
    from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
    scope=context.snapshot.scope
    access=[]
    for entry in (*context.sources,*result_sources):
        if entry.world_id!=scope.world_id or entry.thread_id not in {None,context.private_thread_id}:
            raise ValueError("situation_source_scope_forbidden")
        if entry.source_type=="MEMORY_ITEM":
            prior=session.scalar(select(MemoryItem).options(rights_columns()).where(
                MemoryItem.id == entry.source_id).execution_options(populate_existing=True))
            if (prior is None or item_scope(prior)!=scope
                    or not accessible(session,scope,prior,now,check_snapshot=False,captured=True)):
                raise ValueError("situation_prior_memory_deleted")
            # The immutable manifest proves the earlier text/version. A normal
            # correction must not substitute today's summary into that experience.
        evidence=None
        if entry.source_type in MemorySourceTypeV1.values():
            evidence=CanonicalMemoryEvidence(MemorySourceTypeV1(entry.source_type),entry.source_id,entry.world_id,
                entry.source_digest,datetime.fromisoformat(entry.source_created_at) if entry.source_created_at else receipt.occurred_at,
                entry.delivered_text or receipt.description or "",True,True,True,True,False,
                actor_world_character_id=entry.actor_id,target_world_character_id=entry.counterpart_id,
                counterpart_world_character_id=entry.counterpart_id,thread_id=entry.thread_id)
        access.append((entry,SituationSourceAccess("available",evidence,proof_origin="stored_experience")))
    return access


def store(session, item, setting_id, sources, *, now, dependencies=(), outcome=None, reason=None):
    """Join the owning receipt/correction transaction; no commit or AI call."""
    sources = list(sources)
    present = sum(source.get("text") is not None for source in sources)
    status = "historical_snapshot" if sources and present == len(sources) else (
        "partial_snapshot" if present else "snapshot_unavailable")
    dependencies = tuple(sorted(set(dependencies) - {item.id}))
    payload = {"policy": EXPERIENCE_POLICY, "scope": scope_value(item_scope(item)),
        "thread_id": item.thread_id, "status": status, "sources": sources,
        "dependencies": list(dependencies), "outcome": outcome or {}, "unavailable_reason": reason}
    import json
    if len(json.dumps(payload,ensure_ascii=False).encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError("memory_snapshot_input_limit")
    digest = stable_digest(payload)
    existing = session.get(MemoryExperienceSnapshot, item.id)
    if existing is not None:
        if existing.content_digest != digest:
            raise ValueError("memory_snapshot_content_conflict")
        return existing
    row = MemoryExperienceSnapshot(memory_item_id=item.id, scope_setting_id=setting_id,
        policy_version=EXPERIENCE_POLICY, status=status, payload=payload,
        content_digest=digest, created_at=now)
    session.add(row)
    for identifier in dependencies:
        session.add(MemoryExperienceDependency(memory_item_id=item.id,
            origin_memory_id=identifier, scope_setting_id=setting_id))
    return row


def inherited_dependencies(session, identifiers):
    ids = set(identifiers)
    if ids:
        ids.update(session.scalars(select(MemoryExperienceDependency.origin_memory_id).where(
            MemoryExperienceDependency.memory_item_id.in_(tuple(ids)))))
    return ids


def from_situation(session, item, setting_id, context, receipt, *, now):
    entries = (*context.sources, *context.result_sources)
    sources = [source_snapshot(entry) for entry in entries
        if entry.target_key in {None, receipt.target_key}]
    if sources and receipt.result.get("thought") is not None:
        sources[-1].update(thought=receipt.result["thought"],thought_reference=receipt.result.get("thought_reference"))
    priors = [entry.source_id for entry in entries if entry.source_type == "MEMORY_ITEM"]
    return store(session,item,setting_id,sources,now=now,
        dependencies=inherited_dependencies(session,priors), outcome={
            "receipt_sequence": receipt.sequence,"lane":receipt.lane,
            "logical_activity_id":receipt.logical_activity_id,"effects":receipt.result.get("effects",[]),
            "experience_state":receipt.result.get("experience_state","action_succeeded"),
            "failure_reason":receipt.result.get("failure_reason"),
            "captured_at":receipt.captured_at.isoformat(),"occurred_at":receipt.occurred_at.isoformat()},
        reason="legacy_input_not_preserved" if any(entry.delivered_text is None for entry in entries) else None)


def copy_for_correction(session, old, replacement, *, now):
    setting_id = session.scalar(select(MemoryScopeSettingModel.id).where(
        MemoryScopeSettingModel.owner_id == old.owner_id, MemoryScopeSettingModel.world_id == old.world_id,
        MemoryScopeSettingModel.subject_world_character_id == old.subject_world_character_id))
    row = read_snapshot(session, old)
    return store(session,replacement,setting_id,[] if row is None else row.payload["sources"],
        now=now,dependencies=inherited_dependencies(session,(old.id,)),
        outcome={**({} if row is None else row.payload.get("outcome", {})), "corrected_memory_id":old.id},
        reason="legacy_input_not_preserved" if row is None else None)


def tombstone(session, item, setting_id, *, now):
    if session.get(MemoryExperienceTombstone,(setting_id,item.id)) is None:
        session.add(MemoryExperienceTombstone(scope_setting_id=setting_id,memory_item_id=item.id,deleted_at=now))
    # The flat dependencies also cover pre-existing corrected/combined copies.
    # Query guards prevent stale indexes and late result callbacks from using them.


def packet(session, item, *, representation="activity_situation_v1", validation=None):
    from app.contracts.activity_thought import ActivityThought
    row = read_snapshot(session,item,validation=validation)
    if row is None:
        return EpisodePacket(item.id,item.summary,representation,())
    units = []
    groups = {}
    for index, source in enumerate(row.payload["sources"]):
        groups.setdefault(source.get("unit_key",f"snapshot:{item.id}:{index}"),[]).append(source)
    for reference, sources in groups.items():
        material=[]
        for source in sources:
            text=source.get("text")
            at=source.get("occurred_at")
            material.append(EpisodePacketSource(source["reference"],source["role"],text,
                "verified" if text is not None else "missing",0,len(text) if text is not None else None,
                source.get("author_id"),datetime.fromisoformat(at) if at else None,
                source.get("author_label"),source.get("author_role")))
        source = next((s for s in sources if s.get("thought")),sources[0])
        units.append(EpisodePacketUnit(reference,tuple(material),
            thought=ActivityThought(**source.get("thought", {})), thought_reference=source.get("thought_reference"),
            coverage="partial" if any(s.get("partial") or s.get("text") is None for s in sources) else "complete"))
    return EpisodePacket(item.id,item.summary,representation,tuple(units),
        experience_outcome=row.payload.get("outcome"),snapshot_status=row.status)
