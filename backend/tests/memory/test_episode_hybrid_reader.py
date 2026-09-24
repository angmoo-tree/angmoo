from dataclasses import replace
from hashlib import sha256
import json

from sqlalchemy.orm import sessionmaker

from app.domains.memory.contracts.embedding import EMBEDDING_PROFILE
from app.domains.memory.contracts.episode import EpisodeSelection, EpisodeProposal
from app.domains.memory.contracts.hybrid_recall import HybridRecallRequest, RankedMemoryCandidate, RecallAxisStatus
from app.domains.memory.contracts.recall import MemoryRecallCandidate, RecallDocumentKind
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.episode_hybrid_recall import SqlAlchemyEpisodeHybridReader
from memory.test_episode_apply import preparation
from memory.test_episode_packet_repository import Details
from memory.test_p8_l_g_memory_write_lifecycle import memory_session, NOW


def fixture(db):
    apply, setting, bundle, values = preparation(db)
    ids = apply.apply(bundle=bundle, selection=EpisodeSelection((EpisodeProposal("연습을 돕기로 했지만 취소됐다.", ("S1", "S2")),), ()),
        setting=setting, now=NOW, revalidate=lambda _: values, job_fence=lambda: None)
    db.commit()
    item = db.get(MemoryItem, ids[0])
    candidate = RankedMemoryCandidate(MemoryRecallCandidate(f"memory-item:{item.id}", item.id,
        RecallDocumentKind.MEMORY_ITEM, item.id, 1.0, "", item.counterpart_world_character_id, item.thread_id),
        item.version, sha256(item.summary.encode()).hexdigest())
    request = HybridRecallRequest("request", "call", "a" * 64, setting.scope, "연습 취소", EMBEDDING_PROFILE,
                                 (RecallDocumentKind.MEMORY_ITEM,))
    details = Details(values)
    reader = SqlAlchemyEpisodeHybridReader(sessionmaker(db.bind), detail_reader_factory=lambda _: details, clock=lambda: NOW)
    return reader, request, candidate, details


def test_episode_validation_hydration_preserves_missing_summary_with_partial_status(memory_session):
    reader, request, candidate, details = fixture(memory_session)
    validated = reader.revalidate(request, (candidate,))
    assert len(validated) == 1
    details.values = {}
    hydration = reader.hydrate(request, validated)
    hydrated, receipts = hydration.records, hydration.sources
    assert len(hydrated) == 1
    payload = json.loads(hydrated[0].text)
    assert payload["partial"]
    assert payload["situation"] == validated[0].text
    assert payload["source_statuses"]["missing"] == 2
    assert receipts[0].status is RecallAxisStatus.PARTIAL
    assert candidate.candidate.memory_item_id not in hydrated[0].text
    assert "POST:0" not in hydrated[0].text


def test_candidate_version_hash_and_scope_are_not_granted_by_projection(memory_session):
    reader, request, candidate, _ = fixture(memory_session)
    assert not reader.revalidate(request, (replace(candidate, version=999),))
    assert not reader.revalidate(request, (replace(candidate, content_hash="f" * 64),))
    assert not reader.revalidate(replace(request, scope=replace(request.scope, owner_id="other")), (candidate,))
    accepted = reader.revalidate(request, (candidate,))
    row = memory_session.get(MemoryItem, candidate.candidate.memory_item_id)
    row.version += 1
    row.summary = "이후 수정된 상황"
    memory_session.commit()
    assert reader.hydrate(request, accepted) == ((), ())
    hydration = reader.hydrate(request, accepted)
    assert hydration.records == () and hydration.sources == ()


def test_episode_interval_and_participants_use_all_linked_sources(memory_session):
    from datetime import timedelta
    from sqlalchemy import select
    from app.domains.memory.models.items import MemoryItemEvidence
    reader, request, candidate, _ = fixture(memory_session)
    sources = memory_session.scalars(select(MemoryItemEvidence).where(
        MemoryItemEvidence.memory_item_id == candidate.candidate.memory_item_id)).all()
    sources[0].source_created_at = NOW - timedelta(days=3)
    sources[1].source_created_at = NOW - timedelta(days=1)
    memory_session.commit()
    within = replace(request, occurred_from=NOW - timedelta(days=2), occurred_to=NOW)
    assert len(reader.revalidate(within, (candidate,))) == 1
    outside = replace(request, occurred_from=NOW + timedelta(days=1))
    assert reader.revalidate(outside, (candidate,)) == ()
    axis = reader.axis_request(within)
    assert axis.occurred_from is None and axis.occurred_to is None
    assert axis.scope == request.scope and axis.kinds == request.kinds
    assert reader.revalidate(replace(request, counterpart_world_character_id="absent"), (candidate,)) == ()


def test_packet_survives_evidence_assembly_without_prefix_cutting(memory_session):
    from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
    from app.domains.chat.service.hybrid_canonical import HybridCanonicalResult
    from app.domains.chat.service.canonical_retrieval import CanonicalPlanningMetrics
    from app.domains.memory.contracts.hybrid_recall import HybridRecallResult, RecallAxisReceipt, HybridEmbeddingUsage
    reader, request, candidate, details = fixture(memory_session)
    # Full originals are bounded as complete units, not cut at 2,000 chars by
    # the legacy evidence assembler.
    original = details.read_sources
    def lengthy(**kwargs):
        return {key: replace(value, text="문맥" * 1200 + " 끝은 취소") for key, value in original(**kwargs).items()}
    details.read_sources = lengthy
    # Stored ranges in this fixture are short; use a complete packet payload
    # to exercise the assembler's transport boundary separately.
    hydration = reader.hydrate(request, reader.revalidate(request, (candidate,)))
    records, receipts = hydration.records, hydration.sources
    packet = json.loads(records[0].text)
    packet["units"][0]["sources"][0]["text"] = "문맥" * 1200 + " 끝은 취소"
    text = json.dumps(packet, ensure_ascii=False)
    records = (replace(records[0], text=text),)
    recall = HybridRecallResult(request.request_id, request.call_id, request.envelope_hash, request.scope,
        RecallAxisStatus.READY, records, tuple(RecallAxisReceipt(axis, RecallAxisStatus.READY, True, 1, 1) for axis in ("fts", "vector")),
        receipts, HybridEmbeddingUsage(), 1, 0, 1)
    result = HybridCanonicalResult(request.request_id, recall,
        CanonicalPlanningMetrics(True, False, False, None, 0, 0, 0, 0, 1, None, None), {})
    evidence = EvidenceBundleAssembler().canonical(request_scope_hash="b" * 64, result=result)
    assert evidence.items[0].kind.value == "episode_memory"
    assert json.loads(evidence.items[0].text)["units"][0]["sources"][0]["text"].endswith("끝은 취소")
    assert len(evidence.items[0].text) > 2000
