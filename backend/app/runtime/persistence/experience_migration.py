"""Offline historical snapshot migration. Never rewrites old identity hashes.

Live sources are consulted only here and only accepted when their original
source digest AND exact delivered-text digest match the saved manifest.
Unprovable originals remain explicitly unavailable; summaries are retained.
"""
from dataclasses import asdict, replace
from datetime import UTC, datetime
from hashlib import sha256
from sqlalchemy import select
from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo, MemorySituationReceipt
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.models.experience import MemoryExperienceSnapshot
from app.domains.memory.repository.experience import store, item_scope, source_snapshot, tombstone

from app.runtime.persistence.experience_tables import TABLES


def reconstruct_entry(db, scope, entry, *, read_sources=None):
    if entry.delivered_text is not None:
        return entry
    # Relationship versions and inferred parent identities are not original
    # text. Do not fabricate snapshots from those later representations.
    if entry.source_type not in {'POST','REPLY','CHAT_MESSAGE','OWNER_MEMORY_REQUEST'}:
        return entry
    if read_sources is None:
        raise ValueError("experience_migration_source_reader_required")
    details=read_sources(scope=scope,
        identities=((entry.source_type,entry.source_id),))
    detail=details.get((entry.source_type,entry.source_id))
    if detail is None or detail.evidence.source_digest!=entry.source_digest:
        return entry
    raw=detail.text
    if entry.source_type in {'POST','REPLY'}:
        from app.domains.social.models.posts import Post
        post=db.get(Post,entry.source_id)
        if post is None or post.world_id!=scope.world_id:return entry
        # Situation manifests captured body ranges; legacy episode bundles
        # used title+body. Do not apply one coordinate system to the other.
        raw=post.body
    candidates=[raw]
    if entry.ranges and all(0<=a<=b<=len(raw) for a,b in entry.ranges):
        candidates.append(''.join(raw[a:b] for a,b in entry.ranges))
    original=next((value for value in candidates if sha256(value.encode()).hexdigest()==entry.delivered_digest),None)
    if original is None:
        return entry
    return replace(entry,delivered_text=original,source_created_at=detail.evidence.source_created_at.isoformat())


def migrate(db, *, now=None, read_sources=None):
    """Flush on the owner's offline transaction; replay is idempotent."""
    now=now or datetime.now(UTC)
    settings={(s.owner_id,s.world_id,s.subject_world_character_id):s.id
        for s in db.scalars(select(MemoryScopeSettingModel))}
    counts={'historical_snapshot':0,'partial_snapshot':0,'snapshot_unavailable':0,'existing':0}
    cursor=None
    while True:
        query=select(MemoryItem).order_by(MemoryItem.id).limit(100)
        if cursor is not None:query=query.where(MemoryItem.id>cursor)
        batch=list(db.scalars(query))
        if not batch:break
        cursor=batch[-1].id
        for item in batch:
            scope=item_scope(item);setting=settings.get((scope.owner_id,scope.world_id,scope.subject_world_character_id))
            if setting is None:raise ValueError('memory_snapshot_migration_scope_missing')
            if item.status=='deleted' or item.deleted_at is not None:
                tombstone(db,item,setting,now=now)
            if db.get(MemoryExperienceSnapshot,item.id) is not None:
                counts['existing']+=1;continue
            original=item;ancestors=[];seen={item.id}
            info=db.get(MemoryActivitySituationInfo,item.id)
            episode=db.get(MemoryEpisodeInfo,item.id)
            # Only migration walks a correction lineage. Every replacement
            # receives its own copy and flat explicit-deletion dependencies.
            while info is None and episode is None:
                parents=list(db.scalars(select(MemoryItem).where(MemoryItem.superseded_by_id==original.id)))
                if not parents:break
                if len(parents)!=1:raise ValueError('memory_snapshot_migration_ambiguous_lineage')
                original=parents[0]
                if original.id in seen or len(seen)>=128 or item_scope(original)!=scope:
                    raise ValueError('memory_snapshot_migration_lineage_invalid')
                seen.add(original.id);ancestors.append(original.id)
                info=db.get(MemoryActivitySituationInfo,original.id)
                episode=db.get(MemoryEpisodeInfo,original.id)
            sources=[];reason='historical_input_not_preserved';outcome={'migration':'experience-v1'}
            if info is not None:
                receipt=db.get(MemorySituationReceipt,info.receipt_sequence)
                if receipt is not None:
                    from app.domains.memory.repository.situation_validation import restore_admission
                    try:
                        admission=restore_admission(db,receipt)
                    except (ValueError,KeyError,TypeError):
                        reason='historical_receipt_integrity_unavailable'
                    else:
                        entries=(*admission.manifest.sources,*admission.result_sources)
                        sources=[source_snapshot(reconstruct_entry(db,scope,e,read_sources=read_sources)) for e in entries
                            if e.target_key in {None,receipt.target_key}]
                        if sources and admission.result.get('thought') is not None:
                            sources[-1].update(thought=admission.result['thought'],
                                thought_reference=admission.result.get('thought_reference'))
                        ancestors.extend(e.source_id for e in entries if e.source_type=='MEMORY_ITEM')
                        outcome.update(receipt_sequence=receipt.sequence,effects=admission.result.get('effects',[]))
                        reason=None if sources and all(s['text'] is not None for s in sources) else 'historical_text_digest_unavailable'
                outcome.update(representation="activity_situation_v1", occurred_at=info.occurred_at.isoformat())
            elif episode is not None:
                sources,reason=episode_sources(db,original,scope,read_sources=read_sources)
                outcome.update(representation="episode_v1")
            from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction
            restriction=db.get(MemoryEpisodeRestriction,original.id)
            if restriction is not None:
                import json
                ancestors.extend(p['id'] for p in json.loads(restriction.priors_json))
            row=store(db,item,setting,sources,now=now,dependencies=ancestors,outcome=outcome,reason=reason)
            counts[row.status]+=1
        db.flush()
        db.expunge_all()
    flatten_dependencies(db)
    return counts


def episode_sources(db,item,scope,*,read_sources=None):
    """Only persisted evidence ranges with a matching source digest qualify."""
    from app.domains.memory.models.episode import MemoryEpisodeUnit,MemoryEpisodeUnitEvidence
    from app.domains.memory.models.items import MemoryItemEvidence
    sources=[]
    rows=db.execute(select(MemoryEpisodeUnit,MemoryEpisodeUnitEvidence,MemoryItemEvidence).join(
        MemoryEpisodeUnitEvidence,MemoryEpisodeUnitEvidence.unit_id==MemoryEpisodeUnit.id).join(
        MemoryItemEvidence,MemoryItemEvidence.id==MemoryEpisodeUnitEvidence.evidence_id).where(
        MemoryEpisodeUnit.memory_item_id==item.id).order_by(MemoryEpisodeUnit.ordinal,MemoryEpisodeUnitEvidence.ordinal)).all()
    if rows and read_sources is None:
        raise ValueError("experience_migration_source_reader_required")
    details=read_sources(scope=scope,identities=tuple(dict.fromkeys((e.source_type,e.source_id) for _,_,e in rows))) if rows else {}
    references={unit.id:('chat:'+str(unit.chat_thought_message_id) if unit.chat_thought_message_id is not None
        else 'social:'+unit.social_thought_id if unit.social_thought_id else None) for unit,_,_ in rows}
    thoughts=reader.read_thoughts(scope=scope,references=tuple(set(filter(None,references.values())))) if any(references.values()) else {}
    for unit,span,evidence in rows:
        detail=details.get((evidence.source_type,evidence.source_id));text=None
        if detail is not None and detail.evidence.source_digest==evidence.source_digest:
            end=span.end_offset if span.end_offset is not None else len(detail.text)
            if 0<=span.start_offset<=end<=len(detail.text):text=detail.text[span.start_offset:end]
        sources.append({'reference':f'{evidence.source_type}:{evidence.source_id}',
            'unit_key':unit.unit_key,
            'source_type':evidence.source_type,'source_id':evidence.source_id,'source_digest':evidence.source_digest,
            'text':text,'text_digest':sha256(text.encode()).hexdigest() if text is not None else None,
            'status':'historical_snapshot' if text is not None else 'snapshot_unavailable',
            'role':span.role,'author_id':evidence.actor_world_character_id,'occurred_at':evidence.source_created_at.isoformat(),
            'source_ranges':[[span.start_offset,span.end_offset]],'partial':unit.coverage!='complete',
            'coordinate_system':'delivered_fragment'})
        # A historical thought is preserved only with its originally stored
        # digest. A missing or changed thought is never replaced by new text.
        thought=thoughts.get(references[unit.id])
        if thought is not None:
            import json
            if sha256(json.dumps(asdict(thought),sort_keys=True).encode()).hexdigest()==unit.thought_digest:
                sources[-1].update(thought=asdict(thought),thought_reference=references[unit.id])
    return sources, None if sources and all(s['text'] is not None for s in sources) else 'historical_text_digest_unavailable'


def flatten_dependencies(db):
    from app.domains.memory.models.experience import MemoryExperienceDependency as D
    # Bounded migration-only closure, in the database instead of retaining the
    # whole memory graph in phone RAM. Runtime performs one indexed join.
    from sqlalchemy import text
    for _ in range(128):
        result=db.execute(text('''INSERT INTO memory_experience_dependencies(memory_item_id,origin_memory_id,scope_setting_id)
            SELECT DISTINCT a.memory_item_id,b.origin_memory_id,a.scope_setting_id
            FROM memory_experience_dependencies a JOIN memory_experience_dependencies b
            ON a.origin_memory_id=b.memory_item_id AND a.scope_setting_id=b.scope_setting_id
            WHERE NOT EXISTS (SELECT 1 FROM memory_experience_dependencies c
                WHERE c.memory_item_id=a.memory_item_id AND c.origin_memory_id=b.origin_memory_id)
            ON CONFLICT(memory_item_id,origin_memory_id) DO NOTHING'''))
        if db.scalar(select(D.memory_item_id).where(D.memory_item_id==D.origin_memory_id).limit(1)) is not None:
            raise ValueError('memory_snapshot_migration_dependency_cycle')
        if result.rowcount==0:return
    raise ValueError('memory_snapshot_migration_dependency_depth')
