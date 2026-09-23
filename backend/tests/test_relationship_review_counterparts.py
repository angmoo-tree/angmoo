from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy.orm import Session
from p7_graph_support import sqlite_engine, seed_projection_fixture
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.runtime.relationships.review_memories import resolve_memory_batch


@pytest.mark.parametrize('case,reason', [('single',None),('multiple','counterpart_ambiguous_or_missing'),('unobserved','source_unavailable_or_changed'),('wrong_world','source_unavailable_or_changed')])
def test_null_representative_requires_verified_single_counterpart(monkeypatch, case, reason):
    with Session(sqlite_engine()) as db:
        f = seed_projection_fixture(db, suffix=case)
        now = datetime.now(UTC)
        scope = MemoryScope(f.owner.id, f.world.id, f.actor_world_character.id)
        item = MemoryItem(id='episode', owner_id=f.owner.id, world_id=f.world.id,
            subject_world_character_id=f.actor_world_character.id, memory_kind='AUTOBIOGRAPHICAL_EVENT',
            summary='상대가 격려하여 위로가 되었다.', confidence=1, salience=1)
        db.add(item)
        db.flush()
        sources = {}
        for index, counterpart in enumerate([None, f.target_world_character.id]):
            key = str(index)
            evidence = CanonicalMemoryEvidence(MemorySourceTypeV1.POST,key,f.world.id,'a'*64,now,'검증된 경험',True,True,True,True,False,
                counterpart_world_character_id=counterpart)
            if index == 0 and case == 'multiple':
                evidence=replace(evidence,counterpart_world_character_id='third-person')
            if index == 1 and case == 'unobserved':
                evidence=replace(evidence,observed_by_subject=False)
            if index == 1 and case == 'wrong_world':
                evidence=replace(evidence,source_world_id='different-world')
            sources[('POST',key)] = SimpleNamespace(evidence=evidence)
            db.add(MemoryItemEvidence(id='e'+key,memory_item_id=item.id,source_type='POST',source_id=key,
                source_world_id=f.world.id,source_created_at=now,source_digest='a'*64))
        db.flush()
        monkeypatch.setattr('app.runtime.relationships.review_memories.RuntimeEpisodeDetailReader.read_sources',lambda self,**kwargs:sources)
        target,payload,actual=resolve_memory_batch(db,scope=scope,items=[item],activation=now-timedelta(days=1),now=now)[0]
        assert actual == reason
        if reason is None:
            assert target == f.target_world_character.id
            assert payload['summary'] == item.summary
        assert item.counterpart_world_character_id is None
