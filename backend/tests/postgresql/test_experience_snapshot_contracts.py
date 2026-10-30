"""Real PostgreSQL immutable snapshots, rollback and incremental upgrade."""
from datetime import UTC,datetime
import pytest
from sqlalchemy import text,select,delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from postgresql.test_activity_transactions import store
from memory.test_p8_l_o_memory_consolidation import _stack
from memory.test_activity_situation_application import real_source,receipt,apply,NOW
from app.domains.memory.models.experience import MemoryExperienceSnapshot
from app.runtime.persistence.postgresql_schema import initialize, VERSION
from app.runtime.memory.vector_proof import revisions
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader


def saved(engine):
    with Session(engine,expire_on_commit=False) as db:
        scope,setting,_,memory,*_=_stack(db)
        post=real_source(db,scope);row=receipt(db,scope,post);apply(db,setting,memory)
        return row.applied_item_id,post.id,scope.world_id


def test_snapshot_update_rejected_source_edit_does_not_invalidate_memory_epoch(store):
    engine,_,_=store
    item_id,post_id,world=saved(engine)
    key='experience:world:'+world
    with Session(engine) as db:before=revisions(db,(key,))
    with engine.begin() as c:
        c.execute(text("UPDATE posts SET body='later text' WHERE id=:id"),{'id':post_id})
    with Session(engine) as db:assert revisions(db,(key,))==before
    with pytest.raises(IntegrityError,match='memory_snapshot_immutable'):
        with engine.begin() as c:
            c.execute(text("UPDATE memory_experience_snapshots SET content_digest=repeat('f',64) WHERE memory_item_id=:id"),{'id':item_id})
    with engine.begin() as c:
        c.execute(text('UPDATE memory_items SET version=version+1 WHERE id=:id'),{'id':item_id})
    with Session(engine) as db:assert revisions(db,(key,))!=before


def test_schema_upgrade_failure_rolls_back_marker_and_backfill_then_resumes(store,monkeypatch):
    engine,_,_=store
    item_id,_,_=saved(engine)
    with engine.begin() as c:
        c.execute(delete(MemoryExperienceSnapshot))
        c.execute(text('UPDATE angmoo_postgresql_schema_version SET version=2'))
    from app.runtime.persistence import experience_migration
    original=experience_migration.migrate
    def interrupted(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('injected_upgrade_interruption')
    monkeypatch.setattr(experience_migration,'migrate',interrupted)
    with pytest.raises(RuntimeError,match='injected_upgrade_interruption'):
        with engine.begin() as c:initialize(c, experience_sources=lambda db: RuntimeEpisodeDetailReader(db).read_sources)
    with engine.connect() as c:
        assert c.execute(text('SELECT version FROM angmoo_postgresql_schema_version')).scalar_one()==2
        assert c.execute(select(MemoryExperienceSnapshot.memory_item_id)).first() is None
    monkeypatch.setattr(experience_migration,'migrate',original)
    with engine.begin() as c:initialize(c, experience_sources=lambda db: RuntimeEpisodeDetailReader(db).read_sources)
    with engine.begin() as c:initialize(c, experience_sources=lambda db: RuntimeEpisodeDetailReader(db).read_sources)
    with Session(engine) as db:
        assert db.execute(text('SELECT version FROM angmoo_postgresql_schema_version')).scalar_one()==VERSION
        assert db.get(MemoryExperienceSnapshot,item_id).status=='historical_snapshot'
