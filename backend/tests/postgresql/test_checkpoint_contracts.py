import asyncio,os,uuid,sqlite3,sys
from typing import TypedDict
import pytest
import psycopg
from postgresql.test_canonical_contracts import engine
from app.runtime.autonomous_activity.postgresql_checkpoints import initialize,PostgresCheckpointStore,register,unregister
from app.runtime.autonomous_activity.checkpoints import activity_checkpointer,erase_activity_checkpoint
from langgraph.graph import StateGraph,START,END
from langgraph.checkpoint.base import empty_checkpoint

@pytest.fixture
def store(engine,tmp_path,monkeypatch):
    dsn=os.environ['ANGMOO_EXPERIMENT_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
    initialize(dsn)
    value=PostgresCheckpointStore(dsn);register(tmp_path,value)
    def forbidden(*a,**k):raise AssertionError('PostgreSQL checkpoint opened SQLite')
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    yield value,tmp_path
    unregister(tmp_path,value)

def test_graph_resume_never_replays_completed_node_and_pending_writes_survive(store):
    value,root=store
    class State(TypedDict):number:int
    calls=[]
    def first(s):calls.append('first');return {'number':s['number']+1}
    def second(s):calls.append('second');return {'number':s['number']+1}
    graph=StateGraph(State);graph.add_node('first',first);graph.add_node('second',second)
    graph.add_edge(START,'first');graph.add_edge('first','second');graph.add_edge('second',END)
    thread='activity:pg-resume-'+uuid.uuid4().hex;config={'configurable':{'thread_id':thread,'checkpoint_ns':''}}
    async def execute():
        try:
            async with activity_checkpointer(root) as saver:
                app=graph.compile(checkpointer=saver,interrupt_after=['first'])
                assert (await app.ainvoke({'number':0},config))['number']==1
                snapshot=await app.aget_state(config)
                assert snapshot.next==('second',)
            async with activity_checkpointer(root) as saver:
                app=graph.compile(checkpointer=saver,interrupt_after=['first'])
                assert (await app.ainvoke(None,config))['number']==2
                checkpoint=await saver.aget_tuple(config)
                await saver.aput_writes(checkpoint.config,[('fixture',{'한글':'보존'})],'task-fixture','path-fixture')
            async with activity_checkpointer(root) as saver:
                checkpoint=await saver.aget_tuple(config)
                assert ('task-fixture','fixture',{'한글':'보존'}) in checkpoint.pending_writes
                assert len([c async for c in saver.alist(config)])>=3
        finally:await value.close()
    asyncio.run(execute(),loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else None)
    assert calls==['first','second']

def test_thread_erasure_is_scoped_idempotent_and_fences_late_writes(store):
    value,root=store;token=uuid.uuid4().hex
    ids=['pg-erased-'+token,'pg-kept-'+token]
    async def execute():
        try:
            configs=[]
            async with activity_checkpointer(root) as saver:
                for identifier in ids:
                    checkpoint=empty_checkpoint();checkpoint['channel_values']={'data':{'secret':'synthetic'}};checkpoint['channel_versions']={'data':1}
                    config=await saver.aput({'configurable':{'thread_id':'activity:'+identifier,'checkpoint_ns':''}},checkpoint,{'source':'input','step':0,'parents':{}},{'data':1})
                    await saver.aput_writes(config,[('result',{'pending':True})],'task')
                    configs.append(config)
            erase_activity_checkpoint(root,ids[0]);erase_activity_checkpoint(root,ids[0])
            async with activity_checkpointer(root) as saver:
                assert await saver.aget_tuple(configs[0]) is None
                assert (await saver.aget_tuple(configs[1])).checkpoint['channel_values']['data']=={'secret':'synthetic'}
                with pytest.raises(psycopg.errors.CheckViolation,match='world_deleting'):
                    await saver.aput_writes(configs[0],[('late',{'reappeared':True})],'late-task')
        finally:await value.close()
    asyncio.run(execute(),loop_factory=asyncio.SelectorEventLoop if sys.platform=='win32' else None)
