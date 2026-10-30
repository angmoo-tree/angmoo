"""Replay the complete pure read, with a fresh snapshot and one deadline."""
import asyncio
from time import monotonic
import uuid
from threading import Event
import pytest
from sqlalchemy import text, event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from postgresql.test_canonical_contracts import engine
from app.runtime.memory.canonical_worker import CanonicalReadWorker, DeadlineSessionFactory


@pytest.mark.parametrize('stage',['assert_current','resolve','hydrate','revalidate'])
def test_guard_restarts_a_confirmed_abort_with_a_fresh_read_snapshot(engine,stage):
    key=uuid.uuid4().hex
    with engine.begin() as db:
        db.execute(text('INSERT INTO g2_test_counter VALUES(:key,0)'),{'key':key})
    sessions=DeadlineSessionFactory(sessionmaker(engine))
    seen=[];readonly=[]
    class Reader:
        def assert_current(self, _, rows):
            with sessions() as db:
                seen.append(db.scalar(text('SELECT value FROM g2_test_counter WHERE id=:key'),{'key':key}))
                readonly.append(db.scalar(text('SHOW transaction_read_only')))
                if len(seen)==1:
                    with engine.begin() as other:
                        other.execute(text('UPDATE g2_test_counter SET value=1 WHERE id=:key'),{'key':key})
                    db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'read abort probe' USING ERRCODE='40001'; END $$"))
                return seen[-1]
        resolve=hydrate=revalidate=assert_current
    worker=CanonicalReadWorker(sessions,Reader(),separate_guard=True)
    async def scenario():
        try:
            assert await getattr(worker,stage+'_async')(None,(),deadline=monotonic()+4)==1
            assert seen==[0,1] and readonly==['on','on']
        finally:await worker.stop()
        assert engine.pool.checkedout()==0
    asyncio.run(scenario())


@pytest.mark.parametrize('code,attempts',[('40001',4),('40P01',4),('55P03',4),('42P01',1),('53300',1)])
def test_only_confirmed_aborts_retry_with_finite_attempts(engine,code,attempts):
    from app.core.postgresql_reads import read_transaction
    calls=[]
    def read(db):
        calls.append(1)
        assert db.scalar(text('SHOW transaction_read_only'))=='on'
        assert db.scalar(text('SHOW lock_timeout'))=='50ms'
        db.exec_driver_sql("DO $$ BEGIN RAISE EXCEPTION 'read probe' USING ERRCODE='"+code+"'; END $$")
    with pytest.raises(DBAPIError) as raised:
        read_transaction(engine,read,deadline=monotonic()+4)
    assert raised.value.orig.sqlstate==code and len(calls)==attempts
    assert engine.pool.checkedout()==0


def test_cancel_after_abort_does_not_open_another_snapshot(engine):
    from app.core.postgresql_reads import read_transaction
    signal=Event();calls=[]
    def read(db):
        calls.append(1);signal.set()
        db.exec_driver_sql("DO $$ BEGIN RAISE EXCEPTION 'cancel probe' USING ERRCODE='40001'; END $$")
    with pytest.raises(TimeoutError):
        read_transaction(engine,read,deadline=monotonic()+4,cancelled=signal)
    assert calls==[1] and engine.pool.checkedout()==0


def test_read_boundary_rejects_writes_and_preserves_the_pool(engine):
    from app.core.postgresql_reads import read_transaction
    calls=[]
    def write(db):
        calls.append(1)
        db.exec_driver_sql('UPDATE g2_test_counter SET value=value+1')
    with pytest.raises(DBAPIError) as raised:
        read_transaction(engine,write,deadline=monotonic()+4)
    assert raised.value.orig.sqlstate=='25006' and calls==[1]
    assert engine.pool.checkedout()==0


def test_retries_share_the_original_deadline(engine):
    from app.core.postgresql_reads import read_transaction
    calls=[]
    def read(db):
        calls.append(1)
        db.exec_driver_sql('SELECT pg_sleep(0.04)')
        db.exec_driver_sql("DO $$ BEGIN RAISE EXCEPTION 'deadline probe' USING ERRCODE='40001'; END $$")
    started=monotonic()
    with pytest.raises(TimeoutError):
        read_transaction(engine,read,deadline=started+.12)
    assert 1<=len(calls)<=3 and monotonic()-started<1
    assert engine.pool.checkedout()==0


def test_vector_search_retries_read_without_repeating_projection_writes(engine):
    from postgresql.test_vector_contracts import document
    from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex,PostgresSearchCancellation
    from app.domains.memory.contracts.vector_projection import MemoryVectorQuery
    index=PostgresMemoryVectorIndex(engine,generation='retry-'+uuid.uuid4().hex)
    index.open();doc=document();index.upsert((doc,));attempts=[]
    def fault(connection,cursor,statement,parameters,context,many):
        if statement.startswith('SELECT document_id,memory_item_id,version,content_hash,embedding'):
            attempts.append(1)
            cursor.execute('SHOW transaction_read_only');assert cursor.fetchone()[0]=='on'
            if len(attempts)==1:
                return "DO $$ BEGIN RAISE EXCEPTION 'vector read probe' USING ERRCODE='40001'; END $$",{}
        return statement,parameters
    event.listen(engine,'before_cursor_execute',fault,retval=True)
    try:
        result=index.search(MemoryVectorQuery(doc.scope,doc.profile,doc.vector),
            cancellation=PostgresSearchCancellation(monotonic()+4))
    finally:event.remove(engine,'before_cursor_execute',fault)
    assert attempts==[1,1] and len(result.hits)==1
    assert result.hits[0].document_id==doc.document_id and result.allowed_count==1
    assert index.matches(doc) and engine.pool.checkedout()==0


def test_fts_abort_discards_candidates_but_keeps_materialization_accounting(engine):
    from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
    from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
    from memory.test_korean_memory_recall_quality import document
    from memory.test_grouped_fts_index import query
    index=PostgresMemoryRecallIndex(engine,settings=MemoryRecallIndexSettings(generation='retry-'+uuid.uuid4().hex))
    index.open();index.rebuild([document('retry-memory','축제 약속')]);attempts=[]
    def fault(connection,cursor,statement,parameters,context,many):
        if statement.startswith('SELECT d.*') and 'pg_recall_documents' in statement:
            attempts.append(1)
            cursor.execute('SHOW transaction_read_only');assert cursor.fetchone()[0]=='on'
            if len(attempts)==1:
                return "DO $$ BEGIN RAISE EXCEPTION 'fts read probe' USING ERRCODE='40001'; END $$",{}
        return statement,parameters
    event.listen(engine,'before_cursor_execute',fault,retval=True)
    try:result=index.search_grouped(query('축제 약속'),deadline=monotonic()+4)
    finally:event.remove(engine,'before_cursor_execute',fault)
    assert attempts==[1,1] and result.status.value=='ready'
    assert [r.memory_item_id for r in result.candidates]==['retry-memory']
    assert result.stats['read_attempts']==2 and result.stats['scanned']==2
    assert engine.pool.checkedout()==0


def test_resolve_retry_reports_cost_for_all_attempts(engine):
    from app.contracts.retrieval_observation import Observation,current
    from app.contracts.search_diagnostics import trace_payload
    sessions=DeadlineSessionFactory(sessionmaker(engine));calls=[]
    class Reader:
        def resolve(self,*_):
            calls.append(1)
            with sessions() as db:
                with sessions.phase('revalidate'):db.scalar(text('SELECT 1'))
                with sessions.phase('hydrate'):
                    if len(calls)==1:
                        db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'metrics probe' USING ERRCODE='40001'; END $$"))
                    return db.scalar(text('SELECT 2'))
    worker=CanonicalReadWorker(sessions,Reader(),separate_guard=True)
    async def scenario():
        token=current.set(Observation(request_id='read-retry',detailed=True))
        try:
            assert await worker.resolve_async(None,(),deadline=monotonic()+4)==2
            row,=trace_payload()['canonical_reads']
            assert row['status']=='completed' and row['cleaned'] and row['metrics_complete']
            assert [p['stage'] for p in row['phases']]==['revalidate','hydrate']
            assert all(p['completed'] and p['sql_count']==2 for p in row['phases'])
            assert row['sql_count']>=6
        finally:
            current.reset(token);await worker.stop()
    asyncio.run(scenario())
