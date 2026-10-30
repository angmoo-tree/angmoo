"""Historical input and current memory rights are independent contracts."""
from dataclasses import replace
from hashlib import sha256
import pytest
from sqlalchemy import event, select
from memory.test_activity_situation_contract import stack, values, NOW
from memory.test_activity_situation_application import real_source, apply
from app.domains.memory.contracts.activity_situation import CommittedEffect
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.models.experience import MemoryExperienceSnapshot, MemoryExperienceInput
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.experience import accessible, read_snapshot, packet, tombstone, copy_for_correction
from app.domains.memory.repository.experience_inputs import record_input
from app.runtime.memory.situation_sources import SituationSources


def captured(session, scope, post):
    manifest, draft, result = values(session,scope,target=post.id)
    source = SituationSources(session).describe(scope,kind="POST",identifier=post.id,
        delivered=post.body,path="/target/body",role="core",ordinal=0,target=post.id)
    source = replace(source,delivery_payload_digest=manifest.payload_digest)
    manifest = replace(manifest,version=3,sources=(source,))
    result = replace(result,planned_effects=("post",),effects=(CommittedEffect("post","POST",post.id,"succeeded"),),
        result_sources=(replace(source,role="committed_result",ordinal=1),))
    return manifest,draft,result


@pytest.mark.parametrize("change",["edit","delete"])
def test_delivered_text_survives_change_before_apply_without_source_reads(stack,monkeypatch,change):
    db,scope,setting,memory=stack
    post=real_source(db,scope);original=post.body
    manifest,draft,result=captured(db,scope,post)
    record_input(db,manifest,"submission_uncertain",now=NOW);db.commit()
    if change=="edit":post.body="Changed later, never delivered"
    else:post.deleted_at=NOW
    db.commit()
    def forbidden(*args,**kwargs):raise AssertionError("live source validation")
    monkeypatch.setattr(SituationSources,"validate",forbidden)
    queries=[]
    def observe(conn,cursor,statement,parameters,context,executemany):queries.append(statement.lower())
    event.listen(db.bind,"before_cursor_execute",observe)
    try:
        receipt=admit(db,manifest=manifest,draft=draft,result=result,now=NOW);db.commit()
        apply(db,setting,memory)
        assert receipt.state=="applied",receipt.error_code
        item=db.get(MemoryItem,receipt.applied_item_id)
        assert accessible(db,scope,item,NOW)
        result_packet=packet(db,item)
        assert [s.text for u in result_packet.units for s in u.sources]==[original,original]
        assert not any("from posts" in q or "from messages" in q for q in queries)
        snapshot=read_snapshot(db,item)
        assert snapshot.status=="historical_snapshot"
        assert snapshot.payload["sources"][0]["text_digest"]==sha256(original.encode()).hexdigest()
    finally:event.remove(db.bind,"before_cursor_execute",observe)
    assert db.get(MemoryExperienceInput,receipt.manifest_id).state=="effect_committed"


def test_input_rollback_replay_and_scope_change(stack):
    db,scope,setting,memory=stack
    post=real_source(db,scope)
    manifest,_,_=captured(db,scope,post)
    record_input(db,manifest,"submission_uncertain",now=NOW)
    db.rollback()
    assert db.scalar(select(MemoryExperienceInput)) is None
    row=record_input(db,manifest,"received",now=NOW);db.commit()
    assert record_input(db,manifest,"received",now=NOW).manifest_id==row.manifest_id
    record_input(db,manifest,"submission_uncertain",now=NOW)
    assert row.state=="received"
    stored=db.get(MemoryScopeSettingModel,setting.id);stored.enabled=False;db.commit()
    with pytest.raises(Exception,match="activation_closed"):
        record_input(db,manifest,"received",now=NOW)


def test_known_failed_reply_keeps_read_text_without_claiming_success(stack):
    from app.runtime.autonomous_activity.experience_failures import record_failure
    from app.domains.memory.models.activity_situation import MemorySituationReceipt
    db,scope,setting,memory=stack
    post=real_source(db,scope);original=post.body
    manifest,_,_=captured(db,scope,post)
    record_input(db,manifest,"submission_uncertain",now=NOW);db.commit()
    state={"identity":{"activity_id":"failed-reply"},"decision":{
        "_situation_manifest":manifest.to_dict(),"decisions":[{"target_id":post.id,"action":"comment"}]}}
    post.deleted_at=NOW;db.commit()
    assert record_failure(db,"feed",state,"network_timeout",now=NOW)==0
    assert record_failure(db,"feed",state,"feed_target_stale",now=NOW)==1
    db.commit()
    assert record_failure(db,"feed",state,"feed_target_stale",now=NOW)==0
    apply(db,setting,memory)
    receipt=db.scalar(select(MemorySituationReceipt))
    assert receipt.state=="applied",receipt.error_code
    item=db.get(MemoryItem,receipt.applied_item_id)
    value=packet(db,item)
    assert original==value.units[0].sources[0].text
    assert value.experience_outcome["experience_state"]=="observed_action_failed"
    assert value.experience_outcome["effects"]==[]
    assert "실행되지 않았다" in item.summary
    assert db.get(MemoryExperienceInput,receipt.manifest_id).state=="failed"


def test_corrupt_snapshot_and_other_scope_never_reach_provider(stack):
    db,scope,setting,memory=stack
    post=real_source(db,scope)
    manifest,draft,result=captured(db,scope,post)
    receipt=admit(db,manifest=manifest,draft=draft,result=result,now=NOW)
    apply(db,setting,memory)
    item=db.get(MemoryItem,receipt.applied_item_id)
    assert not accessible(db,replace(scope,owner_id="foreign"),item,NOW)
    snapshot=read_snapshot(db,item)
    snapshot.payload={**snapshot.payload,"scope":{"owner_id":"foreign"}}
    db.flush()
    assert not accessible(db,scope,item,NOW)


def test_explicit_delete_revokes_flat_derived_snapshot(stack):
    db,scope,setting,memory=stack
    post=real_source(db,scope)
    manifest,draft,result=captured(db,scope,post)
    receipt=admit(db,manifest=manifest,draft=draft,result=result,now=NOW)
    apply(db,setting,memory)
    old=db.get(MemoryItem,receipt.applied_item_id)
    # Copy the actual row's required fields while making a distinct owner-scoped item.
    fields={c.key:getattr(old,c.key) for c in MemoryItem.__table__.columns}
    fields.update(id="derived-experience",idempotency_key="derived-experience") if "idempotency_key" in fields else fields.update(id="derived-experience")
    derived=MemoryItem(**fields);db.add(derived);db.flush()
    copy_for_correction(db,old,derived,now=NOW);db.commit()
    assert accessible(db,scope,derived,NOW)
    tombstone(db,old,setting.id,now=NOW);db.commit()
    assert not accessible(db,scope,old,NOW)
    assert not accessible(db,scope,derived,NOW)


def test_large_original_does_not_expand_relationship_input():
    from app.domains.relationships.policies.daily_review import prompt_payload,partition_review_inputs
    raw="한글 기억 😊 "*6500
    entry={"memory_id":"m","summary":"summary","occurred_at":"2026-10-28",
        "source_refs":["POST:p"],"snapshots":[{"reference":"POST:p","text":raw}]}
    prompt=prompt_payload({"memories":[entry]})
    assert len(partition_review_inputs({k:v for k,v in prompt.items() if k!='memories'},prompt['memories']))==1
    assert prompt['memories']==[{"memory_id":"m","summary":"summary","occurred_at":"2026-10-28"}]
    assert entry['snapshots'][0]['text']==raw
