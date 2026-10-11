from dataclasses import replace
from memory.test_activity_situation_contract import stack, NOW
from memory.test_activity_situation_application import real_source, receipt, apply
from app.domains.memory.models.activity_situation import MemoryActivitySituationSource
from app.runtime.memory.situation_detail import situation_detail
from sqlalchemy import select


def test_delivery_proof_owner_detail_memory_off_and_source_change(stack):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    from app.domains.memory.models.items import MemoryScopeSettingModel
    db.get(MemoryScopeSettingModel, setting.id).enabled = False
    db.commit()
    material = situation_detail(db, scope, admitted.applied_item_id, NOW)
    assert material.evidence[0].availability.value == "available"
    assert material.evidence[0].source_id == post.id
    assert material.episode["units"][0]["sources"][0]["status"] == "verified"
    assert material.evidence[0].excerpt == post.body
    post.body = "changed"
    db.commit()
    changed = situation_detail(db, scope, admitted.applied_item_id, NOW)
    assert all(row.availability.value != "available" and row.excerpt is None for row in changed.evidence)
    assert changed.episode is None or not changed.episode["units"]
    assert situation_detail(db, replace(scope, world_id="other"), admitted.applied_item_id, NOW).evidence == ()


def test_exact_range_and_nullable_evidence_never_borrow_another_proof(stack):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    source = db.scalar(select(MemoryActivitySituationSource).where(MemoryActivitySituationSource.memory_item_id == admitted.applied_item_id))
    source.evidence_id = None
    db.commit()
    assert situation_detail(db, scope, admitted.applied_item_id, NOW).evidence[0].availability.value == "available"
    value = dict(source.source)
    value["ranges"] = [[0, 1]]
    source.source = value
    db.commit()
    assert situation_detail(db, scope, admitted.applied_item_id, NOW).evidence == ()


def test_damaged_origin_does_not_fall_back_to_legacy_feed_policy(stack):
    from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo
    from app.domains.memory.models.items import MemoryItem
    from memory.test_activity_situation_recall import readers
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    db.delete(db.get(MemoryActivitySituationInfo, admitted.applied_item_id))
    db.commit()
    assert situation_detail(db, scope, admitted.applied_item_id, NOW).evidence == ()
    reader, request, ranked, _ = readers(db, scope, db.get(MemoryItem, admitted.applied_item_id))
    assert reader.revalidate(request, (ranked,)) == ()
