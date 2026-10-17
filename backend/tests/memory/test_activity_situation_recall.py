"""Real canonical readers: a projection never grants access or returns stale text."""
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

from sqlalchemy.orm import sessionmaker

from memory.test_activity_situation_contract import stack, NOW
from memory.test_activity_situation_application import real_source, receipt, apply
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest, RankedMemoryCandidate
from app.domains.memory.contracts.recall import MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.episode_hybrid_recall import SqlAlchemyEpisodeHybridReader
from app.domains.memory.repository.recall import SqlAlchemyCanonicalRecallRepository
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.source_composition import source_evidence_reader


def readers(session, scope, item):
    factory = sessionmaker(session.bind)
    reader = SqlAlchemyEpisodeHybridReader(factory, detail_reader_factory=RuntimeEpisodeDetailReader, clock=lambda: NOW)
    request = HybridRecallRequest("request", "call", "0"*64, scope, "평범한", "fixture",
        (RecallDocumentKind.MEMORY_ITEM,), episode_source_kinds=(RecallDocumentKind.POST,))
    candidate = MemoryRecallCandidate(f"memory-item:{item.id}", item.id, RecallDocumentKind.MEMORY_ITEM,
        item.id, 1.0, item.summary, counterpart_world_character_id=item.counterpart_world_character_id,
        thread_id=item.thread_id, metadata={"item_version": str(item.version)})
    ranked = RankedMemoryCandidate(candidate, item.version, sha256(item.summary.encode()).hexdigest())
    return reader, request, ranked, factory


def test_deleted_before_apply_remains_a_summary_hit_without_original_fanout(stack):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    post.deleted_at = NOW
    db.commit()
    apply(db, setting, memory)
    item = db.get(MemoryItem, admitted.applied_item_id)
    reader, request, ranked, factory = readers(db, scope, item)
    records = reader.revalidate(request, (ranked,))
    assert len(records) == 1 and records[0].text == admitted.description
    assert records[0].metadata["representation"] == "activity_situation_v1"
    hydrated = reader.hydrate(request, records)
    assert len(hydrated.records) == 1
    assert post.body not in hydrated.records[0].text
    legacy = SqlAlchemyCanonicalRecallRepository(factory, source_reader_factory=source_evidence_reader, character_rows=lambda *_: ())
    assert legacy.revalidate_candidates(scope=scope, candidates=(ranked.candidate,), now=NOW)[0].text == item.summary
    assert reader.revalidate(replace(request, occurred_from=NOW+timedelta(seconds=1)), (ranked,)) == ()


def test_projection_hash_version_scope_and_source_privacy_are_independently_revalidated(stack):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    item = db.get(MemoryItem, admitted.applied_item_id)
    reader, request, ranked, _ = readers(db, scope, item)
    assert reader.revalidate(request, (replace(ranked, version=99),)) == ()
    assert reader.revalidate(request, (replace(ranked, content_hash="0"*64),)) == ()
    assert reader.revalidate(replace(request, scope=replace(scope, world_id="other-world")), (ranked,)) == ()
    selected = reader.revalidate(request, (ranked,))
    assert len(selected) == 1
    post.report_hidden_at = NOW
    db.commit()
    assert reader.revalidate(request, (ranked,)) == ()
    assert reader.hydrate(request, selected).records == ()


def test_changed_canonical_version_between_selection_and_hydration_is_not_returned(stack):
    db, scope, setting, memory = stack
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    item = db.get(MemoryItem, admitted.applied_item_id)
    reader, request, ranked, _ = readers(db, scope, item)
    selected = reader.revalidate(request, (ranked,))
    item.version += 1
    item.summary = "정정된 경험"
    db.commit()
    assert reader.hydrate(request, selected).records == ()


def test_unicode_head_tail_and_name_binding_maps_only_delivered_source_spans():
    from app.domains.memory.policies.situation_ranges import delivered_ranges
    original = "🙂 오늘의 인사와 소식 " + "x"*100 + " 마지막 안부입니다"
    delivered = original[:14] + " [중간 생략] " + original[-10:]
    spans, transmitted = delivered_ranges(original, delivered)
    assert len(spans) >= 2
    assert all(original[a:b] == delivered[c:d] for (a,b), (c,d) in zip(spans, transmitted))
    original = "{{user}} 님은 오늘 공원에서 조용히 책을 읽었습니다."
    delivered = "Bram 님은 오늘 공원에서 조용히 책을 읽었습니다."
    spans, transmitted = delivered_ranges(original, delivered)
    assert spans and all(original[a:b] == delivered[c:d] for (a,b), (c,d) in zip(spans, transmitted))
    assert all(a >= len("{{user}}") for a,b in spans)


def test_receipt_and_empty_manual_request_do_not_rebuild_or_prepare_existing_search(stack, tmp_path):
    from sqlalchemy import event
    from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection
    from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run
    db, scope, setting, _ = stack
    # Watch the same public ORM event used by the real projection listener.
    event.listen(db, "do_orm_execute", EmbeddedMemoryRecallProjection._do_orm_execute)
    try:
        get_or_create_settings(db, setting.id, timezone="UTC", now=NOW)
        request_run(db, setting, trigger="manual", request_key="projection-empty-request", expected_version=1, now=NOW)
        receipt(db, scope, real_source(db, scope))
        db.commit()
        assert not db.info.get("angmoo_memory_recall_pending_setting_ids")
        assert not db.info.get("angmoo_memory_recall_pending_full_sync")
    finally:
        event.remove(db, "do_orm_execute", EmbeddedMemoryRecallProjection._do_orm_execute)


def test_hydrated_packet_uses_verified_source_event_time_not_summary_creation(stack):
    db,scope,setting,memory=stack
    post=real_source(db,scope)
    post.created_at=NOW-timedelta(days=2)
    db.commit()
    admitted=receipt(db,scope,post)
    apply(db,setting,memory)
    item=db.get(MemoryItem,admitted.applied_item_id)
    reader,request,ranked,_=readers(db,scope,item)
    selected=reader.revalidate(request,(ranked,))
    row=reader.hydrate(request,selected).records[0]
    assert row.metadata["event_time_from"]==(NOW-timedelta(days=2)).isoformat()
    assert row.metadata["event_time_to"]==row.metadata["event_time_from"]
    assert row.metadata["recorded_at"]!=row.metadata["event_time_from"]
    post.deleted_at=NOW;db.commit()
    row=reader.hydrate(request,reader.revalidate(request,(ranked,))).records[0]
    assert row.metadata["event_time_from"]==row.metadata["event_time_to"]==""
    assert row.metadata["recorded_at"]
