"""Actual Chat receipt survives Session disposal, application and canonical recall."""
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from chat.today_like_fixture import prepare, execute, f
from app.domains.memory.contracts.activity_situation import DeliveredInputManifest
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest, RankedMemoryCandidate
from app.domains.memory.contracts.recall import MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.models.activity_situation import MemorySituationReceipt, MemorySituationManifest, MemorySituationApplyRun
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.service.scope import MemoryScopeService
from app.domains.memory.repository.situation_runs import get_or_create_settings, request_run, claim_run
from app.domains.memory.repository.situation_apply import apply_page
from app.domains.memory.repository.situation_validation import restore_context
from app.domains.memory.repository.episode_hybrid_recall import SqlAlchemyEpisodeHybridReader
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.relationships.models.social import SocialEvent
from app.domains.social.models.posts import Post
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.memory.situation_application_sources import PreparedSituationSources
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader

response_session = f.response_session


@pytest.mark.parametrize("transitions", [(True,), (True, False)])
def test_new_session_apply_recall_hydrate_and_currentness(response_session, monkeypatch, transitions):
    case = prepare(response_session, transitions=transitions, nested=True)
    result = execute(case, monkeypatch)
    assert not result.errors
    receipt_sequence = result.receipts[0].sequence
    setting_id, post_id, scope, engine = case.setting.id, case.post.id, case.scope, case.db.bind
    case.db.close()
    now = datetime.now(UTC)
    with Session(engine) as db:
        receipt = db.get(MemorySituationReceipt, receipt_sequence)
        context = restore_context(db, receipt)
        manual = tuple(s for s in context.sources if s.source_type == "SOCIAL_EVENT")
        assert len(manual) == len(transitions)
        from app.domains.memory.repository.experience import validate_captured_sources
        captured_access = dict((source.source_id, access) for source, access in
            validate_captured_sources(db, context, (), receipt, now=now, reader=RuntimeEpisodeDetailReader(db)))
        for source in manual:
            access = captured_access[source.source_id]
            assert access.state == "available" and access.proof_origin == "stored_experience"
            assert db.get(SocialEvent, source.source_id).retrieval_status == "audit_only"
        raw_manifest = DeliveredInputManifest.from_dict(db.get(MemorySituationManifest, receipt.manifest_id).payload)
        assert raw_manifest.version == 3
        # A bare manifest is not a restored durable proof, including old v1.
        for unproven in (raw_manifest, replace(raw_manifest, version=1)):
            assert SituationSources(db).validate(unproven, manual[0], now=now).state == "forbidden"
        setting = MemoryScopeService(memory_repository(db)).get_or_create(scope)
        assert setting.id == setting_id
        config = get_or_create_settings(db, setting.id, timezone="UTC", now=now)
        run = request_run(db, setting, trigger="manual", request_key="chat-today-apply", expected_version=config.version, now=now)
        token = claim_run(db, run.run_id, now=now)
        db.commit()
        for _ in range(5):
            apply_page(db, memory_repository(db), PreparedSituationSources(db), run_id=run.run_id, token=token, now=now)
            db.commit()
            if db.get(MemorySituationApplyRun, run.run_id).state == "completed":
                break
            token = claim_run(db, run.run_id, now=now)
            db.commit()
        assert receipt.state == "applied", receipt.error_code
        item = db.get(MemoryItem, receipt.applied_item_id)
        assert item.thread_id == "p-thread"
        packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(
            scope=scope, item_ids=(item.id,), now=now)
        assert len(packets) == 1 and packets[0].representation == "activity_situation_v1"
        candidate = MemoryRecallCandidate(f"memory-item:{item.id}", item.id, RecallDocumentKind.MEMORY_ITEM,
            item.id, 1.0, item.summary, thread_id=item.thread_id, metadata={"item_version": str(item.version)})
        ranked = RankedMemoryCandidate(candidate, item.version, sha256(item.summary.encode()).hexdigest())
        item_id = item.id
    factory = sessionmaker(engine)
    reader = SqlAlchemyEpisodeHybridReader(factory, detail_reader_factory=RuntimeEpisodeDetailReader)
    request = HybridRecallRequest("r", "c", "0"*64, scope, "today", "fixture",
        (RecallDocumentKind.MEMORY_ITEM,), thread_id="p-thread",
        episode_source_kinds=(RecallDocumentKind.THREAD_MESSAGE, RecallDocumentKind.SOCIAL_EVENT))
    records = reader.revalidate(request, (ranked,))
    assert len(records) == 1
    hydration = reader.hydrate(request, records)
    assert hydration.records
    delivered = SimpleNamespace(scope=scope, records=hydration.records, validation_snapshot=hydration.validation_snapshot)
    reader.assert_current(delivered, (item_id,))
    for altered in (replace(request, thread_id="another-thread"),
                    replace(request, scope=replace(scope, world_id="another-world")),
                    replace(request, scope=replace(scope, subject_world_character_id="p-requester"))):
        assert reader.revalidate(altered, (ranked,)) == ()
    with factory() as db:
        db.get(Post, post_id).report_hidden_at = datetime.now(UTC)
        db.commit()
    assert reader.revalidate(request, (ranked,))
    assert reader.hydrate(request, records).records
    reader.assert_current(delivered, (item_id,))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(MemoryItem)) == 1
        assert db.scalar(select(func.count()).select_from(MemorySituationReceipt)) == 1
