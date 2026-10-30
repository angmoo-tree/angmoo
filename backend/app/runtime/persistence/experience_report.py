"""Content-free audit of snapshot migration and retained in-flight work."""
from collections import Counter
from hashlib import sha256
import json
from sqlalchemy import func, select
from app.domains.memory.contracts.activity_situation import stable_digest
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.experience import MemoryExperienceSnapshot, MemoryExperienceDependency


def audit(db):
    counts=Counter(); body=sha256(); payload_bytes=0; source_count=0
    settings={s.id:(s.owner_id,s.world_id,s.subject_world_character_id)
        for s in db.scalars(select(MemoryScopeSettingModel))}
    query=select(MemoryItem,MemoryExperienceSnapshot).outerjoin(MemoryExperienceSnapshot,
        MemoryExperienceSnapshot.memory_item_id==MemoryItem.id).order_by(MemoryItem.id)
    for item,snapshot in db.execute(query.execution_options(yield_per=100)):
        counts['memories']+=1
        body.update(json.dumps([item.id,item.summary,item.version,item.status],ensure_ascii=False).encode())
        body.update(b'\n')
        if snapshot is None:
            counts['missing_snapshots']+=1;continue
        counts[snapshot.status]+=1
        expected=(item.owner_id,item.world_id,item.subject_world_character_id)
        payload=snapshot.payload
        scope=payload.get('scope',{})
        if (settings.get(snapshot.scope_setting_id)!=expected or
                tuple(scope.get(k) for k in ('owner_id','world_id','subject_world_character_id'))!=expected):
            counts['scope_errors']+=1
        if snapshot.content_digest!=stable_digest(payload):counts['digest_errors']+=1
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()
        payload_bytes+=len(encoded)
        for source in payload.get('sources',[]):
            source_count+=1
            value=source.get('text')
            if value is not None and sha256(value.encode()).hexdigest()!=source.get('text_digest'):
                counts['text_digest_errors']+=1
    orphan=db.scalar(select(func.count()).select_from(MemoryExperienceSnapshot).outerjoin(
        MemoryItem,MemoryItem.id==MemoryExperienceSnapshot.memory_item_id).where(MemoryItem.id.is_(None)))
    dependencies=db.scalar(select(func.count()).select_from(MemoryExperienceDependency))
    valid=not any(counts[k] for k in ('missing_snapshots','scope_errors','digest_errors','text_digest_errors')) and not orphan
    return {'policy':'memory-experience-snapshot.v1','valid':valid,'counts':dict(counts),
        'summary_state_sha256':body.hexdigest(),'snapshot_json_bytes':payload_bytes,
        'source_entries':source_count,'flat_dependencies':dependencies,'orphan_snapshots':orphan,
        'pending_work':pending_work(db)}


def pending_work(db):
    from app.domains.memory.models.activity_situation import MemorySituationReceipt,MemorySituationManifest
    from app.domains.memory.models.episode import MemoryEpisodeBundle
    from app.domains.relationships.models.personalization import RelationshipReviewWork
    from app.domains.world_characters.activity_models import ActivityGraphRun
    from app.domains.chat.models import ChatResponseRequest
    result={}; counts=Counter()
    for receipt,manifest in db.execute(select(MemorySituationReceipt,MemorySituationManifest).join(
            MemorySituationManifest,MemorySituationManifest.id==MemorySituationReceipt.manifest_id).where(
                MemorySituationReceipt.state.in_(('pending','blocked'))).execution_options(yield_per=100)):
        version=manifest.payload.get('version',1)
        counts['exact_input' if version>=3 else 'legacy_hash_only_summary_retained']+=1
    result['situation_receipts']=dict(counts);counts=Counter()
    for row in db.scalars(select(MemoryEpisodeBundle).execution_options(yield_per=100)):
        value=json.loads(row.manifest_json)
        if 'input' not in value or value.get('state') in {'completed','split'}:continue
        captured=value['input'].get('snapshot_version')==1
        counts['exact_input_resumable' if captured else 'needs_reprocessing_original_unavailable']+=1
        counts['received_result_retained']+=int(any(c.get('result') is not None for c in value.get('calls',[])))
    result['episode_work']=dict(counts);counts=Counter()
    for row in db.scalars(select(RelationshipReviewWork).where(
            RelationshipReviewWork.status.in_(('pending','running','ready'))).execution_options(yield_per=100)):
        captured=all('snapshot_status' in m for m in row.manifest.get('memories',[]))
        counts['exact_input_resumable' if captured else 'legacy_summary_input_preserved']+=1
        counts['received_result_retained']+=int(row.result is not None)
    result['relationship_work']=dict(counts)
    result['sns_run_status']=dict(db.execute(select(ActivityGraphRun.status,func.count()).group_by(ActivityGraphRun.status)).all())
    result['chat_request_status']=dict(db.execute(select(ChatResponseRequest.state,func.count()).group_by(ChatResponseRequest.state)).all())
    result['resume_policy']={
        'situation':'Old receipt hashes remain intact; missing historical originals stay unavailable.',
        'episode':'Missing durable original input fails before a provider call with episode_manifest_snapshot_unavailable.',
        'sns':'Legacy memory-validation checkpoint policy fails closed with activity_memory_snapshot_policy_changed; committed effects and received-result recovery remain authoritative.',
        'relationship':'Frozen inputs/results retain their hash. Obsolete unsubmitted reviews may adopt relationship-situation-summary.v1 with current memory guards; attempted reviews retire explicitly without automatic provider replay.',
        'chat':'Existing durable publication and response-request receipts remain authoritative; new calls journal exact final input.'}
    return result
