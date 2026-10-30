"""One-request reuse retains the same source proof, scope and freshness rules."""
from dataclasses import replace
import json

import pytest
from sqlalchemy import event

from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.policies.episode_provider_view import episode_provider_view
from app.runtime.chat import evidence_reads
from app.runtime.chat.memory_evidence import ChatMemoryEvidenceRead
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_inspector import episode_receipt_view
from app.runtime.memory.source_composition import source_evidence_reader
from memory.test_activity_situation_contract import stack, NOW
from memory.test_activity_situation_application import real_source, receipt, apply


def prepare(db, scope, setting, memory):
    post = real_source(db, scope)
    admitted = receipt(db, scope, post)
    apply(db, setting, memory)
    identifier = admitted.applied_item_id
    packets = SqlAlchemyEpisodePackets(db, detail_reader=RuntimeEpisodeDetailReader(db)).read(
        scope=scope, item_ids=(identifier,), now=NOW, require_enabled=False)
    text = json.dumps(bounded_episode_packets(episode_provider_view(packets)).packets[0])
    return post, identifier, text


def test_detail_and_receipt_reuse_facts_without_losing_proof_checks(stack):
    db, scope, setting, memory = stack
    post, identifier, text = prepare(db, scope, setting, memory)
    expected = episode_receipt_view(db, scope, identifier, NOW, text)
    reader = source_evidence_reader(db)
    counts = []
    def query(*_): counts.append(1)
    event.listen(db.get_bind(), 'before_cursor_execute', query)
    try:
        # Baseline repeats the two public read operations with fresh validation.
        from app.domains.memory.service.inspector import MemoryReadService
        from app.runtime.memory.composition import memory_repository
        from app.runtime.memory.situation_detail import situation_detail
        baseline = MemoryReadService(memory_repository(db), reader,
            situation_detail_reader=lambda scope,item_id,now:situation_detail(db,scope,item_id,now))
        before = len(counts)
        detail = baseline.detail(scope, item_id=identifier, now=NOW)
        episode_receipt_view(db, scope, identifier, NOW, text)
        separate = len(counts)-before
        before = len(counts)
        batch = ChatMemoryEvidenceRead(db, scope, (identifier,), reader, now=NOW)
        assert batch.detail(identifier) == detail
        assert batch.receipt(identifier, text) == expected
        batched = len(counts)-before
        assert batched < separate, (batched, separate)
        damaged = json.loads(text)
        damaged['situation'] = 'not the delivered situation'
        assert batch.receipt(identifier, json.dumps(damaged)) is None
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', query)


def test_batch_never_survives_commit_or_discloses_changed_or_foreign_sources(stack):
    db, scope, setting, memory = stack
    post, identifier, text = prepare(db, scope, setting, memory)
    batch = ChatMemoryEvidenceRead(db, scope, (identifier,), source_evidence_reader(db), now=NOW)
    assert batch.receipt(identifier, text) is not None
    post.body = 'changed after the first read'
    with pytest.raises(ValueError, match='has_changes'): batch.detail(identifier)
    db.commit()
    with pytest.raises(ValueError, match='operation_changed'): batch.receipt(identifier, text)
    fresh = ChatMemoryEvidenceRead(db, scope, (identifier,), source_evidence_reader(db), now=NOW)
    assert all(e.excerpt is None for e in fresh.detail(identifier).evidence)
    current = fresh.receipt(identifier, text)
    assert current is None or all(s['text'] is None for u in current[1]['units'] for s in u['sources'])
    foreign = ChatMemoryEvidenceRead(db, replace(scope, world_id='another'), (identifier,), source_evidence_reader(db), now=NOW)
    assert foreign.receipt(identifier, text) is None
    with pytest.raises(ValueError, match='operation_changed'): fresh.detail('not-requested')
