"""Real overlapping writers retain transactional source-proof invalidation."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session,sessionmaker
from postgresql.test_activity_transactions import store
from social.test_l4_social_write_uow import _seed
from app.domains.social.models.posts import Post
from app.runtime.memory.vector_proof import revisions
from app.runtime.persistence import postgresql_schema,postgresql_triggers

SCOPE='world:social-uow-world'

def epoch(engine):
    with Session(engine) as session:return revisions(session,(SCOPE,))[0][1]

def post():
    return Post(id='epoch-'+uuid.uuid4().hex,author_user_id='social-uow-owner',
        author_character_id='social-uow-owner-character',world_id='social-uow-world',
        author_world_character_id='social-uow-owner-actor',author_name='Owner',title='Fixture',body='Fixture')

def overlapping(engine, *, simultaneous_flush=False):
    ready=Event();proceed=Event();flushed=Event();xids=[]
    def second():
        with Session(engine) as db:
            xids.append(int(db.execute(text('SELECT pg_current_xact_id()::text')).scalar_one()))
            ready.set();assert proceed.wait(5)
            try:
                db.add(post());db.flush();flushed.set();db.commit();return 'committed'
            except DBAPIError as exc:
                db.rollback();return exc.orig.sqlstate
    with Session(engine) as first,ThreadPoolExecutor(1) as workers:
        xids.append(int(first.execute(text('SELECT pg_current_xact_id()::text')).scalar_one()))
        future=workers.submit(second);assert ready.wait(5)
        assert len({x % 64 for x in xids})==2,'fixture must exercise distinct buckets'
        first.add(post());first.flush()
        if simultaneous_flush:
            proceed.set();assert flushed.wait(5),'independent source writer blocked on shared epoch'
        first.commit();proceed.set()
        return future.result(timeout=5)

def test_same_world_counter_reproduces_abort_and_buckets_allow_overlapping_writes(store):
    engine,_,_=store;_seed(sessionmaker(engine,expire_on_commit=False))
    with engine.begin() as c:
        c.execute(text('INSERT INTO memory_vector_validation_revisions VALUES(:scope,100) ON CONFLICT(scope_key) DO UPDATE SET revision=100'),{'scope':SCOPE})
        # The previous trigger used one shared MVCC row for unrelated writes.
        postgresql_triggers.trigger(c,'memory_vector_posts_insert','posts','INSERT',
            "INSERT INTO memory_vector_validation_revisions(scope_key,revision) VALUES('world:'||NEW.world_id,1) "
            "ON CONFLICT(scope_key) DO UPDATE SET revision=memory_vector_validation_revisions.revision+1;",timing='AFTER')
    before=epoch(engine)
    assert overlapping(engine)=='40001'
    assert epoch(engine)==before+1
    with engine.begin() as c:postgresql_triggers.vector_producers(c)
    before=epoch(engine)
    assert overlapping(engine)=='committed'
    assert epoch(engine)==before+2
    before=epoch(engine)
    assert overlapping(engine,simultaneous_flush=True)=='committed'
    assert epoch(engine)==before+2
    before=epoch(engine)
    with Session(engine) as db:
        db.add(post());db.flush();assert revisions(db,(SCOPE,))[0][1]==before+1
        db.rollback()
    assert epoch(engine)==before

def test_epoch_upgrade_is_atomic_preserves_legacy_value_and_requires_current_reader(store,monkeypatch):
    engine,_,_=store;_seed(sessionmaker(engine,expire_on_commit=False))
    with engine.begin() as c:
        c.execute(text('INSERT INTO memory_vector_validation_revisions VALUES(:scope,321) ON CONFLICT(scope_key) DO UPDATE SET revision=321'),{'scope':SCOPE})
        c.execute(text('UPDATE angmoo_postgresql_schema_version SET version=1'))
    before=epoch(engine)
    with pytest.raises(RuntimeError,match='requires_fences'),engine.begin() as c:
        postgresql_schema.initialize(c,fences=False)
    original=postgresql_triggers.install
    def fail_after_install(c,tables):
        original(c,tables);raise RuntimeError('injected_upgrade_abort')
    with monkeypatch.context() as patch:
        patch.setattr(postgresql_triggers,'install',fail_after_install)
        with pytest.raises(RuntimeError,match='injected_upgrade_abort'),engine.begin() as c:
            postgresql_schema.initialize(c)
    with engine.connect() as c:
        assert c.execute(text('SELECT version FROM angmoo_postgresql_schema_version')).scalar_one()==1
    for _ in range(2):
        with engine.begin() as c:postgresql_schema.initialize(c)
        assert epoch(engine)==before
    with engine.connect() as c:
        assert c.execute(text('SELECT version FROM angmoo_postgresql_schema_version')).scalar_one()==postgresql_schema.VERSION
        assert c.execute(text('SELECT revision FROM memory_vector_validation_revisions WHERE scope_key=:scope'),{'scope':SCOPE}).scalar_one()==321
    with Session(engine) as db:db.add(post());db.commit()
    assert epoch(engine)==before+1
