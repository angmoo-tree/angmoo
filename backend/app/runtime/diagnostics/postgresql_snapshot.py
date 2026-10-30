"""Bounded PostgreSQL diagnostic reads without SQL/text/credential exposure."""
from datetime import datetime
from time import monotonic
from psycopg.rows import dict_row
from app.core.postgresql_connections import serving_connection
from app.runtime.checkpoint_registry import bound_store


def scheduler_snapshot(root,manifest,*,dsn=None):
    started=monotonic()
    try:
        if dsn is None:
            store=bound_store(root)
            if store is None:raise ValueError('postgresql_runtime_unbound')
            dsn=store._dsn
        actors=manifest['actor_ids']
        if not actors or len(actors)>100:raise ValueError('postgresql_scope_invalid')
        with serving_connection(dsn.replace('postgresql+psycopg://','postgresql://',1),connect_timeout=2,row_factory=dict_row) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            db.execute("SET LOCAL statement_timeout='1500ms'")
            rows=db.execute('''SELECT s.agent_id,s.status,s.next_tick_at,s.locked_by_run_id FROM agent_slots s
                JOIN world_characters c ON c.character_id=s.assigned_character_id WHERE c.world_id=%s AND c.id=ANY(%s)''',(manifest['world_id'],actors)).fetchall()
            from app.runtime.diagnostics.identifiers import identifier,code
            slots=[{'agent_id':identifier(r['agent_id']),'status':code(r['status']),
                'next_tick_at':r['next_tick_at'].isoformat() if isinstance(r['next_tick_at'],datetime) else r['next_tick_at'],
                'locked':r['locked_by_run_id'] is not None} for r in rows]
            runs=db.execute("SELECT status,count(*) AS n FROM activity_graph_runs WHERE world_id=%s AND world_character_id=ANY(%s) AND status IN('running','waiting','interrupted') GROUP BY status",(manifest['world_id'],actors)).fetchall()
        return {'scheduler_snapshot':'ready','persistence':'postgresql','slots':slots,
            'unfinished_runs':{r['status']:r['n'] for r in runs},'duration_ms':int((monotonic()-started)*1000)}
    except Exception:
        return {'scheduler_snapshot':'unavailable','persistence':'postgresql','duration_ms':int((monotonic()-started)*1000)}


def memory_snapshot(root,manifest,*,dsn=None):
    """Canonical + keyword + vector metadata in one read-only MVCC snapshot."""
    from datetime import UTC
    result={'schema':'memory-pipeline-snapshot.v1','started_at':datetime.now(UTC).isoformat(),
        'persistence':'postgresql','atomic_across_databases':True,'status':'ok','truncated':False,
        'items':[],'receipts':[],'runs':[],'work':[],'maintenance':[],'changes':[],'brief':[],'projection':[],'fts':[]}
    actors=manifest['actor_ids']
    if not actors or len(actors)>100:raise ValueError('memory_snapshot_scope_invalid')
    started=monotonic();scope='s.world_id=%s AND s.subject_world_character_id=ANY(%s)'
    queries={
        'items':f'SELECT id,version,world_id,subject_world_character_id,created_at,updated_at,status,deleted_at FROM memory_items s WHERE {scope} ORDER BY updated_at DESC LIMIT 1001',
        'work':f'SELECT w.generation,w.item_id,w.desired_revision,w.applied_revision,w.last_change,w.state,w.due_at,w.last_code FROM memory_vector_work w JOIN memory_items s ON s.id=w.item_id WHERE {scope} ORDER BY w.item_id LIMIT 1001',
        'receipts':f'SELECT r.sequence,r.run_id,r.applied_item_id,r.state,r.state_version,r.captured_at,r.applied_at FROM memory_situation_receipts r JOIN memory_scope_settings s ON s.id=r.scope_setting_id WHERE {scope} ORDER BY r.sequence DESC LIMIT 1001',
        'runs':f'SELECT r.id,r.state,r.cursor,r.cutoff_sequence,r.created_at,r.work_kind FROM memory_situation_runs r JOIN memory_scope_settings s ON s.id=r.scope_setting_id WHERE {scope} ORDER BY r.created_at DESC LIMIT 1001',
        'brief':f'SELECT c.scope_setting_id,c.brief_dirty FROM memory_situation_settings c JOIN memory_scope_settings s ON s.id=c.scope_setting_id WHERE {scope} LIMIT 1001',
        'changes':f"SELECT c.sequence,c.root_sequence,c.state,c.cursor FROM memory_vector_changes c JOIN memory_items s ON c.source_kind='memory' AND c.source_key=s.id WHERE {scope} ORDER BY c.sequence LIMIT 1001",
        'eligibility':f'SELECT e.memory_item_id,e.content_hash,e.item_version,e.registered_at FROM memory_vector_eligibility e JOIN memory_items s ON s.id=e.memory_item_id WHERE {scope} LIMIT 1001',
        'projection':'SELECT v.memory_item_id AS item_id,v.version,v.content_hash,v.profile,v.generation FROM pg_memory_vectors v JOIN pg_vector_state g ON g.active=v.generation WHERE v.world_id=%s AND v.subject_id=ANY(%s) ORDER BY v.memory_item_id LIMIT 1001',
        'fts':'SELECT d.memory_item_id,d.kind,d.searchable,d.tombstoned_at FROM pg_recall_documents d JOIN pg_search_state s ON s.namespace=d.namespace AND s.active=d.generation WHERE d.world_id=%s AND d.subject_world_character_id=ANY(%s) LIMIT 1001'}
    try:
        if dsn is None:
            store=bound_store(root)
            if store is None:raise ValueError('postgresql_runtime_unbound')
            dsn=store._dsn
        with serving_connection(dsn.replace('postgresql+psycopg://','postgresql://',1),connect_timeout=2,row_factory=dict_row) as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for key,query in queries.items():
                remaining=int((2-(monotonic()-started))*1000)
                if remaining<=0:raise TimeoutError('postgresql_snapshot_deadline')
                db.execute("SELECT set_config('statement_timeout',%s,true)",(str(remaining),))
                rows=db.execute(query,(manifest['world_id'],actors)).fetchall()
                result[key]=rows[:1000];result['truncated']|=len(rows)>1000
            result['schema_version']=db.execute('SELECT version FROM angmoo_postgresql_schema_version').fetchone()['version']
            result['maintenance']=db.execute('SELECT generation,phase,cursor,upper_bound,cutoff,due_at FROM memory_vector_maintenance LIMIT 16').fetchall()
            result['projection_status']=result['fts_status']='ok';result['changed_during_snapshot']=False
    except Exception as exc:
        result['status']='partial_read_failed'
        sqlstate=getattr(exc,'sqlstate',None)
        if isinstance(sqlstate,str) and len(sqlstate)==5 and sqlstate.isalnum():result['sqlstate']=sqlstate
    result['elapsed_ms']=int((monotonic()-started)*1000)
    return result
