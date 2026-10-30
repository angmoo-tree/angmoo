"""Group summaries by stored participant metadata, never original snapshots."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from sqlalchemy.orm import Session

from p7_graph_support import sqlite_engine, seed_projection_fixture
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel, MemoryItemEvidence
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.repository.experience import store
from app.runtime.relationships.review_memories import resolve_memory_batch


@pytest.mark.parametrize('case,reason', [
    ('single', None),
    ('snapshot_only', 'counterpart_ambiguous_or_missing'),
    ('multiple', 'counterpart_ambiguous_or_missing'),
    ('unavailable', 'counterpart_ambiguous_or_missing'),
    ('no_snapshot', 'counterpart_ambiguous_or_missing'),
    ('saved_representative_without_snapshot', None),
    ('wrong_world', 'memory_unavailable_or_changed'),
    ('disabled_scope', 'memory_unavailable_or_changed'),
])
def test_counterpart_uses_saved_experience_and_current_scope(monkeypatch, case, reason):
    with Session(sqlite_engine()) as db:
        f = seed_projection_fixture(db, suffix=case)
        now = datetime.now(UTC)
        scope = MemoryScope(f.owner.id, f.world.id, f.actor_world_character.id)
        setting = MemoryScopeSettingModel(id='scope', owner_id=scope.owner_id, world_id=scope.world_id,
            subject_world_character_id=scope.subject_world_character_id, enabled=case != 'disabled_scope')
        db.add(setting)
        item = MemoryItem(id='episode', owner_id=scope.owner_id, world_id=scope.world_id,
            subject_world_character_id=scope.subject_world_character_id, memory_kind='AUTOBIOGRAPHICAL_EVENT',
            summary='상대가 격려하여 위로가 되었다.', confidence=1, salience=1,
            valid_from=now-timedelta(seconds=1))
        if case == 'saved_representative_without_snapshot':
            item.counterpart_world_character_id=f.target_world_character.id
        db.add(item); db.flush()
        sources=[]
        for index, counterpart in enumerate([None, f.target_world_character.id]):
            if index == 0 and case == 'multiple':counterpart='third-person'
            if case == 'unavailable':counterpart=None
            text=None if case == 'unavailable' else '당시 전달받은 원문'
            sources.append({'reference':f'POST:{index}', 'source_type':'POST', 'source_id':str(index),
                'author_id':counterpart, 'counterpart_id':counterpart, 'text':text,
                'text_digest':sha256(text.encode()).hexdigest() if text else None,
                'status':'historical_snapshot' if text else 'snapshot_unavailable',
                'role':'observed', 'occurred_at':now.isoformat()})
        if case not in {'no_snapshot','saved_representative_without_snapshot'}:
            store(db,item,setting.id,sources,now=now)
        if case in {'single','multiple','wrong_world','disabled_scope'}:
            targets=[f.target_world_character.id]
            if case=='multiple':
                from app.domains.characters.models import Character
                from app.domains.world_characters.models import WorldCharacter
                fields={c.key:getattr(f.target,c.key) for c in Character.__table__.columns}
                fields.update(id='third-character',handle='third-character')
                db.add(Character(**fields));db.flush()
                fields={c.key:getattr(f.target_world_character,c.key) for c in WorldCharacter.__table__.columns}
                fields.update(id='third-world-character',character_id='third-character')
                db.add(WorldCharacter(**fields));db.flush();targets.append('third-world-character')
            for index,target_id in enumerate(targets):
                db.add(MemoryItemEvidence(id=f'evidence-{index}',memory_item_id=item.id,
                    source_type='POST',source_id=f'never-query-{index}',source_world_id=scope.world_id,
                    actor_world_character_id=target_id,source_created_at=now,source_digest='a'*64))
        db.flush()
        if case == 'wrong_world':scope=replace(scope,world_id='different-world')
        def forbidden(*args,**kwargs):
            raise AssertionError('historical_original_read')
        monkeypatch.setattr('app.runtime.memory.episode_details.RuntimeEpisodeDetailReader.read_sources',forbidden)
        monkeypatch.setattr('app.domains.memory.repository.experience.read_snapshot',forbidden)
        from sqlalchemy import event
        def deny_snapshot(conn,cursor,statement,*args):
            assert 'memory_experience_snapshots' not in statement.lower()
        event.listen(db.bind,'before_cursor_execute',deny_snapshot)
        target,payload,actual=resolve_memory_batch(db,scope=scope,items=[item],activation=now-timedelta(days=1),now=now)[0]
        event.remove(db.bind,'before_cursor_execute',deny_snapshot)
        assert actual == reason
        assert set(payload)=={'memory_id','summary','digest','occurred_at'}
        if reason is None:
            assert target == f.target_world_character.id
            assert payload['summary'] == item.summary
        if case != 'saved_representative_without_snapshot':
            assert item.counterpart_world_character_id is None
