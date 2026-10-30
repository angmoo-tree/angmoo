"""Real review preparation/delivery guards use saved text and current rights."""
import asyncio
from datetime import UTC,datetime,timedelta
import re
from sqlalchemy import event,select
from sqlalchemy.orm import sessionmaker
import pytest
from memory.test_activity_situation_contract import stack,NOW
from memory.test_activity_situation_application import real_source,apply
from memory.test_experience_snapshots import captured
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.models.activity_configuration import MemorySubjectProfile
from app.domains.relationships.models.personalization import RelationshipPolicy,RelationshipReviewWork
from app.domains.relationships.service.daily_review import plan_review,run_review_step,apply_review
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.service import world_credentials
from app.runtime.relationships.review_credentials import snapshot as credential_snapshot
from app.runtime.relationships.review_identity import review_identity_context
from app.runtime.relationships.review_memories import resolve_memory_batch,ReviewMemoryReferences
from test_relationship_daily_review import Provider


def prepare(db,scope,setting,memory,*,original_text=None):
    post=real_source(db,scope)
    if original_text is not None:
        post.body=original_text
    post.author_world_character_id='consolidation-counterpart'
    post.author_character_id='consolidation-counterpart-character'
    from app.domains.social.models.feed import WorldCharacterFeedObservation
    db.add(WorldCharacterFeedObservation(id='snapshot-observed',world_id=scope.world_id,
        observer_world_character_id=scope.subject_world_character_id,post_id=post.id,
        status='observed',claim_token='fixture',cycle_key='fixture',run_id='fixture',
        lease_expires_at=NOW,observed_at=NOW,post_created_at=NOW,claimed_at=NOW))
    db.commit()
    manifest,draft,result=captured(db,scope,post)
    from dataclasses import replace
    result=replace(result,counterpart_id=post.author_world_character_id)
    receipt=admit(db,manifest=manifest,draft=draft,result=result,now=NOW)
    apply(db,setting,memory)
    item=db.get(MemoryItem,receipt.applied_item_id)
    item.valid_until=datetime.now(UTC)+timedelta(days=30)
    db.add(RelationshipPolicy(world_id=scope.world_id,mode='interpreted',activated_at=NOW-timedelta(days=1)))
    batch=db.get(MemoryBatchSetting,setting.id)
    if batch is None:
        batch=MemoryBatchSetting(scope_setting_id=setting.id,timezone='UTC');db.add(batch)
    batch.ai_enabled=True;batch.consent_version='synthetic';batch.schedule_enabled=True
    profile=MemorySubjectProfile(scope_setting_id=setting.id,model_id='gemini-3.1-flash-lite',thinking_level='high',version=1,updated_at=NOW)
    db.add(profile)
    world_credentials.save(db,owner_id=scope.owner_id,world_id=scope.world_id,
        world_character_id=scope.subject_world_character_id,purpose='consolidation',
        data=WorldCredentialWrite(expected_revision=0,provider='google',model=profile.model_id,
            thinking_level='high',api_key='synthetic-review-only'))
    db.commit()
    identity=review_identity_context(db,owner_id=scope.owner_id,world_id=scope.world_id,
        actor_id=scope.subject_world_character_id,target_id=post.author_world_character_id)
    base={**credential_snapshot(db,scope,profile),'identity':identity,'owner_id':scope.owner_id,
        'setting_id':setting.id,'profile_version':1,'model_id':profile.model_id,'thinking_level':'high'}
    return post,item,base


@pytest.mark.parametrize('change',['edit','delete'])
@pytest.mark.parametrize('stage',['before_prepare','during_provider','before_apply'])
def test_actual_review_uses_summary_only_and_applies_once_without_original_or_snapshot_reads(stack,change,stage):
    db,scope,setting,memory=stack
    post,item,base=prepare(db,scope,setting,memory)
    original=post.body;target=post.author_world_character_id
    post_id=post.id
    def mutate():
        from app.domains.social.models.posts import Post
        from app.domains.social.models.feed import WorldCharacterFeedObservation
        from sqlalchemy import delete,update
        # Explicit source mutations are part of the adversarial fixture, not
        # source reads by memory preparation/delivery/application.
        if change=='edit':db.execute(update(Post).where(Post.id==post_id).values(body='later and unobserved'))
        else:
            db.execute(delete(WorldCharacterFeedObservation).where(WorldCharacterFeedObservation.post_id==post_id))
            db.execute(delete(Post).where(Post.id==post_id))
        db.commit()
    if stage=='before_prepare':mutate()
    seen=[]
    def no_original(conn,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith(('SELECT','WITH')) and re.search(r'\b(?:FROM|JOIN)\s+(?:posts|message_messages|social_events|memory_experience_snapshots|memory_situation_manifests|memory_situation_sources)\b',statement,re.I):
            raise AssertionError('historical_original_read')
        seen.append(statement)
    event.listen(db.bind,'before_cursor_execute',no_original)
    try:
        resolved=resolve_memory_batch(db,scope=scope,items=[item],activation=NOW-timedelta(days=1),now=NOW)
        assert resolved[0][0]==target and resolved[0][2] is None
        assert 'snapshots' not in resolved[0][1]
        assert resolved[0][1]['summary']==item.summary
        work=plan_review(db,world_id=scope.world_id,actor_id=scope.subject_world_character_id,
            target_id=target,period_key='snapshot-boundary',base=base,memories=[resolved[0][1]])
        identifier=work.id;db.commit()
        class MutatingProvider(Provider):
            async def review(self,payload,**kwargs):
                if stage=='during_provider':mutate()
                return await super().review(payload,**kwargs)
        provider=MutatingProvider();sessions=sessionmaker(db.bind,expire_on_commit=False)
        def run():return asyncio.run(run_review_step(sessions,work_id=identifier,
            references_factory=ReviewMemoryReferences,provider_factory=lambda _:provider))
        assert run()=='ready';assert run()=='ready';assert len(provider.calls)==1
        assert set(provider.calls[0])=={'existing_relationship','memories'}
        assert set(provider.calls[0]['existing_relationship'])=={'relationship_label','perception'}
        assert set(provider.calls[0]['memories'][0])=={'memory_id','summary','occurred_at'}
        assert provider.calls[0]['memories'][0]['summary']==item.summary
        if stage=='before_apply':mutate()
        db.expire_all()
        assert apply_review(db,work_id=identifier,references=ReviewMemoryReferences(db),now=datetime.now(UTC))=='applied'
        db.commit()
        assert apply_review(db,work_id=identifier,references=ReviewMemoryReferences(db),now=datetime.now(UTC))=='applied'
        assert db.get(RelationshipReviewWork,identifier).status=='applied'
        assert seen
    finally:event.remove(db.bind,'before_cursor_execute',no_original)


def test_explicit_memory_delete_after_input_preparation_still_revokes_review(stack):
    db,scope,setting,memory=stack
    post,item,base=prepare(db,scope,setting,memory)
    resolved=resolve_memory_batch(db,scope=scope,items=[item],activation=NOW-timedelta(days=1),now=NOW)
    work=plan_review(db,world_id=scope.world_id,actor_id=scope.subject_world_character_id,
        target_id=post.author_world_character_id,period_key='delete-boundary',base=base,memories=[resolved[0][1]])
    db.commit()
    ReviewMemoryReferences(db).revalidate(work)
    from app.domains.memory.repository.experience import tombstone
    tombstone(db,item,setting.id,now=NOW);db.commit()
    with pytest.raises(ValueError,match='relationship_review_evidence_changed'):
        ReviewMemoryReferences(db).revalidate(work)


def test_compact_reduction_root_preserves_summaries_and_current_memory_guard(stack):
    db,scope,setting,memory=stack
    original='당시 실제로 읽은 원문 😊 ' * 3500
    post,item,base=prepare(db,scope,setting,memory,original_text=original)
    resolved=resolve_memory_batch(db,scope=scope,items=[item],activation=NOW-timedelta(days=1),now=NOW)
    entry=resolved[0][1]
    # Many distinct memories require bounded summary reduction; a large original
    # alone no longer creates any extra relationship provider call.
    entries=[]
    for index in range(36):
        fields={c.key:getattr(item,c.key) for c in MemoryItem.__table__.columns}
        fields.update(id=f'summary-part-{index}',summary=('함께 고민하고 서로 도운 경험. ' * 90),
            counterpart_world_character_id=post.author_world_character_id)
        clone=MemoryItem(**fields);db.add(clone);db.flush()
        from app.runtime.relationships.review_memories import _digest
        entries.append({**entry,'memory_id':clone.id,'summary':clone.summary,'digest':_digest(clone)})
    work=plan_review(db,world_id=scope.world_id,actor_id=scope.subject_world_character_id,
        target_id=post.author_world_character_id,period_key='compact-summary',base=base,memories=entries)
    identifier=work.id
    assert work.phase=='final'
    frozen=work.manifest['memories'][0]
    assert all(key not in frozen for key in ('summary','snapshots','experience_outcome'))
    assert frozen['digest']==entries[0]['digest'] and 'snapshot_digest' not in frozen
    children=list(db.scalars(select(RelationshipReviewWork).where(RelationshipReviewWork.parent_id==identifier)
        .order_by(RelationshipReviewWork.part_key)))
    summaries=[m for child in children for m in child.manifest['payload']['memories']]
    child_ids=[child.id for child in children]
    assert [m['summary'] for m in summaries]==[m['summary'] for m in entries]
    assert all(set(m)=={'memory_id','summary','occurred_at'} for m in summaries)
    db.commit()
    ReviewMemoryReferences(db).revalidate(work)
    changed=db.get(MemoryItem,entries[0]['memory_id']);changed.version+=1;db.flush()
    with pytest.raises(ValueError,match='relationship_review_memory_changed'):
        ReviewMemoryReferences(db).revalidate(work)
    db.rollback()
    provider=Provider();sessions=sessionmaker(db.bind,expire_on_commit=False)
    # Scalar IDs avoid an expired ORM access reopening the fixture's read
    # transaction across provider calls. Production uses a fresh transaction
    # for final application, rather than retaining a SERIALIZABLE snapshot.
    for child_id in child_ids:
        assert asyncio.run(run_review_step(sessions,work_id=child_id,
            references_factory=ReviewMemoryReferences,provider_factory=lambda _:provider))=='ready'
    assert asyncio.run(run_review_step(sessions,work_id=identifier,
        references_factory=ReviewMemoryReferences,provider_factory=lambda _:provider))=='ready'
    db.expire_all()
    assert apply_review(db,work_id=identifier,references=ReviewMemoryReferences(db),now=datetime.now(UTC))=='applied'
    db.commit()
    assert len(provider.calls)==len(children)+1


@pytest.mark.parametrize('state',['unsubmitted','received','unknown'])
def test_old_input_policy_preserves_attempts_and_only_replans_unsubmitted_work(stack,state):
    from app.domains.relationships.contracts.daily_review import manifest_digest
    from app.domains.relationships.models.personalization import RelationshipReviewMemoryReceipt
    from app.domains.relationships.policies.daily_review import REVIEW_INPUT_POLICY
    from app.runtime.relationships.review_policy_upgrade import retire_old_review
    db,scope,setting,memory=stack
    post,item,base=prepare(db,scope,setting,memory)
    target=post.author_world_character_id
    entry=resolve_memory_batch(db,scope=scope,items=[item],activation=NOW-timedelta(days=1),now=NOW)[0][1]
    root=plan_review(db,world_id=scope.world_id,actor_id=scope.subject_world_character_id,
        target_id=target,period_key='old-policy',base=base,memories=[entry])
    root.manifest={k:v for k,v in root.manifest.items() if k!='input_policy'}
    root.manifest={**root.manifest,'memories':[{**entry,'snapshots':[{'text':'old captured original'}]}]}
    root.manifest_digest=manifest_digest(root.manifest)
    if state=='received':
        root.attempts=1;root.status='ready'
        result={'decision':'keep','memory_refs':[item.id]}
        root.result={**result,'_execution':{'result_digest':manifest_digest(result)}}
    elif state=='unknown':
        root.attempts=1;root.status='failed';root.error_code='relationship_review_outcome_unknown'
    identifier=root.id;before_hash=root.manifest_digest;before_result=root.result
    db.commit()
    if state=='received':
        with pytest.raises(ValueError,match='relationship_review_input_policy_changed'):
            apply_review(db,work_id=identifier,references=ReviewMemoryReferences(db),now=datetime.now(UTC))
        db.rollback()
    retire_old_review(db,root);db.commit()
    assert root.status=='stale' and root.manifest_digest==before_hash and root.result==before_result
    # Re-entry cannot duplicate the successor or relabel an old attempt.
    retire_old_review(db,root);db.commit()
    successors=list(db.scalars(select(RelationshipReviewWork).where(RelationshipReviewWork.id!=identifier)))
    receipt=db.scalar(select(RelationshipReviewMemoryReceipt).where(RelationshipReviewMemoryReceipt.memory_id==item.id))
    if state!='unsubmitted':
        assert successors==[] and receipt.status=='excluded' and receipt.work_id==identifier
        assert root.attempts==1
        return
    assert len(successors)==1 and successors[0].manifest['input_policy']==REVIEW_INPUT_POLICY
    successor=successors[0];successor_id=successor.id
    assert receipt.work_id==successor_id and receipt.status=='pending'
    provider=Provider();sessions=sessionmaker(db.bind,expire_on_commit=False)
    db.rollback()
    assert asyncio.run(run_review_step(sessions,work_id=successor_id,
        references_factory=ReviewMemoryReferences,provider_factory=lambda _:provider))=='ready'
    assert len(provider.calls)==1 and 'snapshots' not in provider.calls[0]['memories'][0]
    assert apply_review(db,work_id=successor_id,references=ReviewMemoryReferences(db),now=datetime.now(UTC))=='applied'
    db.commit()
