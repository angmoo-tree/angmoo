"""Character rounds, historical failure exclusion and real short-write scopes."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from dataclasses import replace
import pytest
from sqlalchemy import select, func, event
from sqlalchemy.orm import sessionmaker, Session
from memory.test_manual_relationship_followup import setup, memories, finish_memory
from memory.test_p8_l_r_memory_batch_safety import memory_session
from app.domains.memory.service import consolidation_requests as service
from app.domains.relationships.models.manual_review import RelationshipReviewRequest as Request
from app.domains.relationships.models.personalization import RelationshipReviewWork as Work, RelationshipReviewMemoryReceipt as Receipt
from app.runtime.relationships.manual_review_worker import advance_manual_requests
from app.runtime.relationships.manual_review import ManualRelationshipFollowup
from app.runtime.relationships.review_commands import command
from app.domains.relationships.service.review_history import reconcile_closed_history, active_snapshot, pending_receipts
from app.domains.relationships.service.daily_review import run_review_step, apply_review
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest
from test_relationship_daily_review import Provider, References


def closed_fixture(db, monkeypatch):
    scope, setting, workflows, data = setup(db)
    target, payloads = memories(db, scope, monkeypatch, count=8)
    future = payloads[5:]
    del payloads[5:]
    result = service.submit(scope=scope, db=db, workflows=workflows, data=data)
    finish_memory(db, result['request_id'])
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    original = db.get(Request, result['request_id'])
    work = db.get(Work, original.work_ids[0])
    work.status, work.error_code, work.maintenance = 'failed', 'relationship_review_storage_text_invalid', {'hold':'manual'}
    db.commit()
    command(db, original, mode='close_without_retry', key='close-original-failure', expected_revision=0)
    db.commit()
    return scope, workflows, data, original, work, payloads, future


@pytest.mark.parametrize('new_memories', [False, True])
def test_closed_failure_never_joins_next_request_but_same_counterpart_can_return(memory_session, monkeypatch, new_memories):
    db = memory_session
    scope, workflows, data, original, old, payloads, future = closed_fixture(db, monkeypatch)
    old_snapshot = original.snapshot
    assert all(r.status == 'excluded' for r in db.scalars(select(Receipt).where(Receipt.work_id == old.id)))
    if new_memories:
        payloads.extend(future)
    result = service.submit(scope=scope, db=db, workflows=workflows,
        data=data.model_copy(update={'idempotency_key':uuid4().hex}))
    finish_memory(db, result['request_id'])
    advance_manual_requests(db, datetime.now(UTC)); db.commit()
    request = db.get(Request, result['request_id'])
    assert len(request.snapshot) == (3 if new_memories else 0)
    assert old.id not in request.work_ids
    assert original.snapshot == old_snapshot and old.status == 'failed' and old.maintenance['hold'] == 'closed'
    if not new_memories:
        assert request.state == 'no_relationship_work' and request.work_ids == []
    else:
        provider = Provider()
        factory = sessionmaker(db.bind)
        assert asyncio.run(run_review_step(factory, work_id=request.work_ids[0], references_factory=lambda db:References(), provider_factory=lambda base:provider)) == 'ready'
        apply_review(db, work_id=request.work_ids[0], references=References(), now=datetime.now(UTC))
        advance_manual_requests(db, datetime.now(UTC)); db.commit()
        value = service.read(scope=scope, db=db, workflows=workflows)['progress']['relationship']
        assert (value['target_count'], value['completed_count'], value['changed_count']) == (1,1,1)
        assert len(provider.calls) == 1


def test_v4_contaminated_snapshot_is_reconciled_once_without_erasing_history(memory_session, monkeypatch):
    db=memory_session
    scope, workflows, data, original, old, payloads, future = closed_fixture(db, monkeypatch)
    payloads.extend(future)
    result=service.submit(scope=scope,db=db,workflows=workflows,data=data.model_copy(update={'idempotency_key':uuid4().hex}))
    finish_memory(db,result['request_id']);advance_manual_requests(db,datetime.now(UTC));db.commit()
    request=db.get(Request,result['request_id'])
    new=db.get(Work,request.work_ids[0])
    new.status,new.result='applied',{'decision':'keep'}
    for receipt in db.scalars(select(Receipt).where(Receipt.work_id==new.id)):
        receipt.status='applied'
    for receipt in db.scalars(select(Receipt).where(Receipt.work_id==old.id)):
        receipt.status,receipt.reason='pending',None
    request.snapshot=request.snapshot+original.snapshot
    request.work_ids=request.work_ids+[old.id]
    request.state='closed'
    db.commit()
    frozen=list(request.snapshot); original_frozen=list(original.snapshot)
    assert reconcile_closed_history(db)==1
    db.commit()
    assert reconcile_closed_history(db)==0
    assert request.snapshot==frozen and original.snapshot==original_frozen
    assert len(active_snapshot(request))==3 and request.state=='completed'
    progress=ManualRelationshipFollowup(db).extend(db.get(MemoryConsolidationRequest,request.memory_request_id),
        {'state':'completed','accepted_at':request.accepted_at})['relationship']
    assert (progress['target_count'],progress['completed_count'],progress['kept_count'],progress['failed_count'])==(1,1,1,0)
    assert old.status=='failed' and old.error_code=='relationship_review_storage_text_invalid'


def test_unclosed_failure_stays_with_original_manual_recovery(memory_session,monkeypatch):
    db=memory_session
    scope,_,_,_,old,_,_=closed_fixture(db,monkeypatch)
    old.maintenance={**old.maintenance,'hold':'manual'}
    for receipt in db.scalars(select(Receipt).where(Receipt.work_id==old.id)):
        receipt.status,receipt.reason='pending',None
    db.commit()
    assert pending_receipts(db,world_id=scope.world_id,actor_id=scope.subject_world_character_id)==[]


def test_memory_round_exceeds_internal_burst_and_leaves_late_input_for_next_round(tmp_path,monkeypatch):
    from memory.test_situation_prepared_page import setup as page_setup
    from memory.test_activity_situation_contract import NOW,values
    from app.domains.memory.models.activity_situation import MemorySituationApplyRun as Run,MemorySituationReceipt as Situation
    from app.domains.memory.repository.situation_admission import admit
    from app.domains.memory.repository.situation_runs import get_or_create_settings
    from app.runtime.memory.batch_runtime import MemoryBatchRuntime
    from app.runtime.memory.composition import memory_repository
    from app.domains.memory.contracts.scope import MemoryScope
    from app.domains.memory.models.items import MemoryScopeSettingModel
    engine,run_id,_,_,_=page_setup(tmp_path)
    factory=sessionmaker(engine)
    with factory() as db:
        run=db.get(Run,run_id);setting=db.get(MemoryScopeSettingModel,run.scope_setting_id)
        scope=MemoryScope(setting.owner_id,setting.world_id,setting.subject_world_character_id)
        for i in range(36):
            manifest,draft,result=values(db,scope,target='situation-post',logical='burst-'+str(i),call='burst-'+str(i))
            admit(db,manifest=manifest,draft=draft,result=result,now=NOW)
        db.flush()
        run.cutoff_sequence=db.scalar(select(func.max(Situation.sequence)))
        cutoff=run.cutoff_sequence
        run.state,run.lease_token,run.lease_until='pending',None,None
        manifest,draft,result=values(db,scope,target='situation-post',logical='late-memory',call='late-memory')
        late=admit(db,manifest=manifest,draft=draft,result=result,now=NOW)
        late_id=late.sequence;db.commit()
    runtime=MemoryBatchRuntime(factory,None,generation_policy='activity_situation')
    monkeypatch.setattr(runtime.situations,'prepare',lambda **kw:None)
    monkeypatch.setattr(runtime,'_rebuild_situation_brief',lambda:None)
    async def exercise():
        assert await runtime.tick()=='situation_page_applied'
        await runtime.stop()
    asyncio.run(exercise())
    with factory() as db:
        row=db.get(Run,run_id)
        assert row.state=='completed' and row.cursor==cutoff
        assert db.get(Situation,late_id).state=='pending'
    engine.dispose()


def test_three_character_rounds_do_not_interleave_and_slot_does_not_hold_connection(monkeypatch):
    from test_relationship_daily_review import seed
    from app.runtime.memory.batch_runtime import MemoryBatchRuntime
    from app.runtime.memory.maintenance_slot import MaintenanceSlot
    factory,_,_=seed(1)
    now=datetime.now(UTC)
    events=[]
    waiting=[dict(kind='memory',id='may',actor_id='may',world_id='world',accepted_at=now),
             dict(kind='memory',id='taeo',actor_id='taeo',world_id='world',accepted_at=now+timedelta(seconds=2))]
    counts={'may':37,'taeo':3}
    class Situations:
        quit_identity=None
        def prepare(self,**kwargs): pass
        def candidate(self): return waiting[0] if waiting else None
        def tick(self,identifier):
            assert identifier==waiting[0]['id']
            if not counts[identifier]:
                waiting.pop(0)
                return 'memory_batch_queue_empty'
            counts[identifier]-=1
            events.append(identifier)
            return 'situation_page_applied'
    class Relationships:
        done=False
        async def candidate(self):
            return None if self.done else dict(kind='relationship',id='doyun',actor_id='doyun',world_id='world',accepted_at=now+timedelta(seconds=1))
        async def run_round(self,identifier):
            # During a provider wait, another session can read/write while a
            # second maintenance runtime is excluded by the durable token.
            assert MaintenanceSlot(factory).acquire('memory') is None
            with factory() as db:
                db.execute(select(func.count()).select_from(Work));db.rollback()
            for _ in range(2):
                events.append(identifier)
                await asyncio.sleep(0)
            self.done=True
            return 'relationship_queue_empty'
    runtime=MemoryBatchRuntime(factory,None,generation_policy='activity_situation',relationship_work=Relationships())
    runtime.situations=Situations()
    monkeypatch.setattr(runtime,'_rebuild_situation_brief',lambda:None)
    async def exercise():
        for _ in range(3): await runtime.tick()
        await runtime.stop()
    asyncio.run(exercise())
    assert events==['may']*37+['doyun']*2+['taeo']*3


def test_relationship_round_runs_selected_roots_only(memory_session,monkeypatch,tmp_path):
    db=memory_session
    scope,_,workflows,data=setup(db)
    _,payloads=memories(db,scope,monkeypatch)
    result=service.submit(scope=scope,db=db,workflows=workflows,data=data)
    finish_memory(db,result['request_id']);advance_manual_requests(db,datetime.now(UTC));db.commit()
    request=db.get(Request,result['request_id'])
    original=db.get(Work,request.work_ids[0])
    unrelated=Work(**{column.name:getattr(original,column.name) for column in Work.__table__.columns if column.name!='id'})
    unrelated.id='unrelated-root';unrelated.period_key='unrelated-period';db.add(unrelated);db.commit()
    from app.runtime.relationships.review_runtime import RelationshipReviewRuntime
    from app.core.result_journal import ResultJournal
    factory=sessionmaker(db.bind)
    provider=Provider()
    runtime=RelationshipReviewRuntime(factory,lambda base:provider,media_root=tmp_path)
    monkeypatch.setattr('app.runtime.relationships.review_runtime.ReviewMemoryReferences',lambda db:References())
    def transition(sessions,identifier,now,apply=False):
        if apply:
            with sessions() as current:
                outcome=apply_review(current,work_id=identifier,references=References(),now=now)
                current.commit();return outcome
        return 'prepared'
    monkeypatch.setattr('app.runtime.relationships.review_transitions.transition',transition)
    assert asyncio.run(runtime.run_round(request.memory_request_id))=='relationship_queue_empty'
    db.expire_all()
    assert len(provider.calls)==1 and db.get(Work,original.id).status=='applied'
    assert db.get(Work,unrelated.id).status=='pending'
