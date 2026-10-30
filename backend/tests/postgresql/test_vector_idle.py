"""Real PG idle admission, with rollback-scoped temporary queue tables."""
from time import time
from types import SimpleNamespace
import asyncio
from uuid import uuid4
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker
from postgresql.test_canonical_contracts import engine, no_sqlite
from app.runtime.memory.vector_queue_worker import postgres_idle
from app.domains.memory.repository.vector_queue import enqueue


@pytest.fixture
def projection(engine):
    # Session savepoints preserve the outer transaction; rollback drops only
    # these connection-local temporary tables and leaves shared fixtures intact.
    with engine.connect() as connection, connection.begin():
        for table in ('memory_vector_maintenance', 'memory_vector_changes',
                      'memory_vector_work', 'memory_index_preparations'):
            connection.exec_driver_sql(f'CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL) ON COMMIT DROP')
        connection.execute(text("INSERT INTO memory_vector_maintenance (generation,phase,cursor,upper_bound,cutoff,due_at) VALUES ('idle-test','ready','','',0,:due)"), {'due':time()+3600})
        yield SimpleNamespace(_factory=sessionmaker(bind=connection,join_transaction_mode='create_savepoint'),
            generation='idle-test',connection=connection)


def test_empty_probe_uses_one_query_and_detects_enqueued_work(projection):
    statements=[]
    def observed(conn,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(projection.connection,'before_cursor_execute',observed)
    assert postgres_idle(projection) is True
    assert len(statements)==1
    with projection._factory() as session:
        enqueue(session,projection.generation,'new-item','world')
        session.commit()
    assert postgres_idle(projection) is False
    projection.connection.execute(text("UPDATE memory_vector_work SET state='done'"))
    assert postgres_idle(projection) is True


def test_new_sessions_observe_external_commits(engine):
    from app.domains.memory.models.vector_work import MemoryVectorMaintenance,MemoryVectorWork
    schema='idle_'+uuid4().hex
    tables=('memory_vector_maintenance','memory_vector_changes','memory_vector_work','memory_index_preparations')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE SCHEMA '+schema)
        for table in tables:connection.exec_driver_sql(f'CREATE TABLE {schema}.{table} (LIKE public.{table} INCLUDING ALL)')
    local=engine.execution_options(schema_translate_map={None:schema})
    factory=sessionmaker(bind=local)
    projection=SimpleNamespace(_factory=factory,generation='external')
    try:
        with factory.begin() as session:
            session.add(MemoryVectorMaintenance(generation='external',phase='ready',due_at=time()+3600))
        assert postgres_idle(projection) is True
        with factory.begin() as session:
            session.add(MemoryVectorWork(generation='external',item_id='new',world_id='world'))
        assert postgres_idle(projection) is False
    finally:
        with engine.begin() as connection:connection.exec_driver_sql('DROP SCHEMA '+schema+' CASCADE')


@pytest.mark.parametrize('phase', ['bootstrap','settling','audit_work','audit_index','retired'])
def test_nonready_maintenance_never_shortcuts(projection,phase):
    projection.connection.execute(text('UPDATE memory_vector_maintenance SET phase=:phase'),{'phase':phase})
    assert postgres_idle(projection) is False


@pytest.mark.parametrize('state,due,expected', [
    ('pending',3600,False),('running',3600,False),('retry',3600,False),('blocked',3600,False),
    ('scheduled',-1,False),('scheduled',3600,True),('done',-1,True)])
def test_pending_recovery_and_scheduled_boundaries(projection,state,due,expected):
    with projection._factory() as session:
        enqueue(session,projection.generation,'item','world')
        session.execute(text('UPDATE memory_vector_work SET state=:state,due_at=:due'),{'state':state,'due':time()+due})
        session.commit()
    assert postgres_idle(projection) is expected


@pytest.mark.parametrize('kind',['missing_marker','audit_due','change','preparation','retirement'])
def test_durable_maintenance_obligations_never_shortcut(projection,kind):
    c=projection.connection
    if kind=='missing_marker':c.execute(text('DELETE FROM memory_vector_maintenance'))
    elif kind=='audit_due':c.execute(text('UPDATE memory_vector_maintenance SET due_at=0'))
    elif kind=='change':c.execute(text("INSERT INTO memory_vector_changes(source_kind,source_key,cursor,state) VALUES ('test','test','','pending')"))
    elif kind=='preparation':c.execute(text("INSERT INTO memory_index_preparations(scope_setting_id,state,revision,profile,source_generation) VALUES ('scope','running',1,'profile','source')"))
    else:
        c.execute(text("INSERT INTO memory_vector_maintenance(generation,phase,cursor,upper_bound,cutoff,due_at) VALUES ('old','retired','','',0,0)"))
        with projection._factory() as session:
            enqueue(session,'old','old-item','world');session.commit()
    assert postgres_idle(projection) is False


def test_tick_returns_early_only_for_ready_idle_projection(projection):
    from app.runtime.memory.vector_queue_worker import tick
    class EnteredFullCycle(Exception):pass
    async def call(fn,*args):return fn(*args)
    async def preparation():raise EnteredFullCycle()
    projection.status='ready';projection._on_clean_cycle=None
    projection._canonical=SimpleNamespace(call=call);projection._prepare_page=preparation
    assert asyncio.run(tick(projection)) is False
    projection._on_clean_cycle=lambda index:None
    with pytest.raises(EnteredFullCycle):asyncio.run(tick(projection))
    projection._on_clean_cycle=None;projection.status='degraded'
    with pytest.raises(EnteredFullCycle):asyncio.run(tick(projection))
    projection.status='ready'
    projection.connection.execute(text('UPDATE memory_vector_maintenance SET due_at=0'))
    with pytest.raises(EnteredFullCycle):asyncio.run(tick(projection))
