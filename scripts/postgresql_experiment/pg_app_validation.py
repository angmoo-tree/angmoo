"""No provider calls or content output: actual migrated PG validation on ARM64."""
import argparse,asyncio,json,math,time,uuid
from pathlib import Path
from typing import TypedDict
from sqlalchemy import text
from app.runtime.postgresql_backend import install_validation_guards
from app.database import create_database_engine
from app.core.security import SecretScope,decrypt_local_secret


def probe(engine,root):
    from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex,PostgresSearchCancellation
    from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
    from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
    from app.domains.memory.contracts.scope import MemoryScope
    from app.domains.memory.contracts.vector_projection import MemoryVectorQuery
    from app.domains.memory.contracts.recall import MemoryRecallSearchQuery,MemoryRecallLexicalPolicy,RecallDocumentKind
    secret=(root/'secrets/app-secret').read_text().strip();counts={}
    mappings=[('llm_credentials','encrypted_api_key','owner_id','character_id','purpose'),
        ('media_credentials','encrypted_secret','owner_id','character_scope','purpose'),
        ('world_credentials','encrypted_secret','owner_id','aad_character_id','aad_purpose'),
        ('world_image_provider_credentials','encrypted_secret','owner_id','aad_character_id','aad_purpose'),
        ('agent_creation_drafts','encrypted_api_key','user_id',None,None)]
    with engine.connect() as conn:
        for table,column,owner,character,purpose in mappings:
            rows=conn.execute(text(f'SELECT * FROM {table} WHERE {column} IS NOT NULL')).mappings().all();n=0
            for row in rows:
                if not row[column]:continue
                scope=SecretScope(owner_id=row[owner] or '',character_id=(row[character] or '') if character else '',
                    provider=row['provider'],purpose=row[purpose] if purpose else 'creation_draft')
                plaintext=decrypt_local_secret(row[column],scope=scope,app_secret=secret)
                if not plaintext:raise ValueError('validation_empty_credential')
                n+=1
            counts[table]=n
        rows=conn.execute(text('SELECT r.*,c.owner_id FROM world_credential_revisions r JOIN world_credentials c ON c.id=r.credential_id WHERE r.encrypted_secret IS NOT NULL')).mappings().all()
        for row in rows:
            if row['encrypted_secret']:decrypt_local_secret(row['encrypted_secret'],scope=SecretScope(owner_id=row['owner_id'],character_id=row['aad_character_id'],provider=row['provider'],purpose=row['aad_purpose']),app_secret=secret)
        counts['world_credential_revisions']=len(rows)
        vectors=conn.execute(text('SELECT *,embedding::text AS coordinates FROM pg_memory_vectors ORDER BY document_id')).mappings().all()
        scopes=[dict(r) for r in conn.execute(text('SELECT id,world_id,character_id FROM world_characters WHERE character_id IS NOT NULL')).mappings()]
        threads=[dict(r) for r in conn.execute(text("SELECT id,world_id,requester_world_character_id,responding_world_character_id FROM message_threads WHERE world_scope_status='resolved'")).mappings()]
        (root/'runtime/validation-api-scopes.json').write_text(json.dumps({'actors':scopes,'threads':threads}))
    checked=0
    for sample in vectors[::max(1,len(vectors)//12)]:
        vector=json.loads(sample['coordinates']);qnorm=math.sqrt(sum(v*v for v in vector))
        scope=MemoryScope(sample['owner_id'],sample['world_id'],sample['subject_id'])
        eligible=[r for r in vectors if all(r[k]==sample[k] for k in ('generation','owner_id','world_id','subject_id','profile'))]
        expected={}
        for row in eligible:
            x=json.loads(row['coordinates']);expected[row['document_id']]=1-sum(a*b for a,b in zip(vector,x))/(qnorm*math.sqrt(sum(a*a for a in x)))
        result=PostgresMemoryVectorIndex(engine,generation=sample['generation']).search(MemoryVectorQuery(scope,sample['profile'],vector,limit=10),cancellation=PostgresSearchCancellation(time.monotonic()+10))
        cutoff=sorted(expected.values())[min(10,len(expected))-1]
        if result.allowed_count!=len(eligible) or len(result.hits)!=min(10,len(eligible)):raise ValueError('validation_vector_scope_count')
        for hit in result.hits:
            if abs(hit.distance-expected[hit.document_id])>1e-5 or expected[hit.document_id]>cutoff+1e-5:raise ValueError('validation_exact_vector_mismatch')
        checked+=1
    index=PostgresMemoryRecallIndex(engine,settings=MemoryRecallIndexSettings.for_representation('episode_v1'))
    index.open()
    ready_deadline=time.monotonic()+120
    while index.load_progress() is not None and time.monotonic()<ready_deadline:time.sleep(.25)
    if index.load_progress() is not None:raise ValueError('validation_fts_preparation_timeout')
    if not index.doctor().healthy:raise ValueError('validation_fts_unhealthy')
    with engine.connect() as conn:
        samples=conn.execute(text("SELECT owner_id,world_id,subject_world_character_id,text,memory_item_id FROM pg_recall_documents WHERE kind='memory_item' AND searchable=1 ORDER BY document_id LIMIT 12")).mappings().all()
    hits=0
    for row in samples:
        query=MemoryRecallSearchQuery(MemoryScope(row['owner_id'],row['world_id'],row['subject_world_character_id']),row['text'][:80],(RecallDocumentKind.MEMORY_ITEM,),50,lexical_policy=MemoryRecallLexicalPolicy.GROUP_OR_V1)
        result=index.search_grouped(query,deadline=time.monotonic()+10)
        hits+=row['memory_item_id'] in {r.memory_item_id for r in result.candidates}
    if samples and hits!=len(samples):raise ValueError('validation_fts_self_recall_mismatch')
    return {'credentials_decrypted':counts,'credential_values_output':False,'exact_vector_queries':checked,
        'distance_tolerance':1e-5,'fts_queries':len(samples),'fts_hits':hits,'provider_calls':0,'sqlite_access':'denied'}


async def checkpoint(engine,dsn,root,mode):
    from app.runtime.autonomous_activity.postgresql_checkpoints import PostgresCheckpointStore
    from langgraph.graph import StateGraph,START,END
    class State(TypedDict):number:int
    with engine.begin() as c:c.exec_driver_sql('CREATE TABLE IF NOT EXISTS pg_validation_effects(thread_id text,node text,PRIMARY KEY(thread_id,node))')
    path=root/'runtime/validation-checkpoint.json'
    if mode=='interrupt':
        if path.exists():raise ValueError('validation_checkpoint_exists')
        config={'configurable':{'thread_id':'validation:'+uuid.uuid4().hex,'checkpoint_ns':''}}
        path.write_text(json.dumps(config))
    else:config=json.loads(path.read_text())
    def effect(node):
        def step(s):
            with engine.begin() as c:c.execute(text('INSERT INTO pg_validation_effects VALUES(:t,:n)'),{'t':config['configurable']['thread_id'],'n':node})
            return {'number':s['number']+1}
        return step
    graph=StateGraph(State);graph.add_node('first',effect('first'));graph.add_node('second',effect('second'))
    graph.add_edge(START,'first');graph.add_edge('first','second');graph.add_edge('second',END)
    store=PostgresCheckpointStore(dsn)
    try:
        async with store.saver() as saver:
            app=graph.compile(checkpointer=saver,interrupt_after=['first'])
            result=await app.ainvoke({'number':0} if mode=='interrupt' else None,config)
            state=await app.aget_state(config)
            if result['number']!=(1 if mode=='interrupt' else 2):raise ValueError('validation_checkpoint_result')
            with engine.connect() as c:effects=list(c.execute(text('SELECT node FROM pg_validation_effects WHERE thread_id=:t ORDER BY node'),{'t':config['configurable']['thread_id']}).scalars())
            if effects!=(['first'] if mode=='interrupt' else ['first','second']):raise ValueError('validation_checkpoint_duplicate')
            return {'state':mode,'effects':effects,'next_nodes':list(state.next),'completed_effects_replayed':False}
    finally:await store.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['probe','interrupt','resume']);p.add_argument('--dsn-file',type=Path,default=Path('/experiment/secrets/app-dsn'));p.add_argument('--data-root',type=Path,default=Path('/experiment/appdata'));a=p.parse_args()
    install_validation_guards();dsn=a.dsn_file.read_text().strip();engine=create_database_engine(dsn)
    try:result=probe(engine,a.data_root) if a.action=='probe' else asyncio.run(checkpoint(engine,dsn,a.data_root,a.action));print(json.dumps(result))
    except Exception as exc:
        import traceback
        print(json.dumps({'state':'FAILED','reason':str(exc) if isinstance(exc,ValueError) and str(exc).startswith('validation_') else type(exc).__name__,
            'frames':[{'file':Path(x.filename).name,'line':x.lineno,'function':x.name} for x in traceback.extract_tb(exc.__traceback__)]}))
        raise SystemExit(2) from None
    finally:engine.dispose()
