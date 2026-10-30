"""Use shipped PostgreSQL search code on an owned migrated data copy.

No AI/embedding requests. Existing vectors check preservation and exact search;
they are not evidence of natural-language relevance or new provider behavior.
Only opaque identifiers, counts and timings enter the support result.
"""
import argparse,json,os,re,time,uuid
from pathlib import Path
from sqlalchemy import text
from app.database import create_database_engine
from app.runtime.postgresql_installation import read_dsn
from app.runtime.persistence.postgresql_schema import metadata
from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex,PostgresSearchCancellation
from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery,RecallDocumentKind
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.contracts.vector_projection import MemoryVectorQuery

p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,default=Path('/var/lib/angmoo'))
p.add_argument('--source',default=os.environ.get('ANGMOO_SOURCE_SHA'));a=p.parse_args()
from app.runtime.product_identity import runtime_identity
assert runtime_identity()['source_sha']==a.source
metadata();engine=create_database_engine(read_dsn(a.data_root/'secrets/postgresql-runtime-dsn'))
report={'source_sha':a.source,'provider_transmissions':0,'scope':'Existing migrated keyword/vector search; no natural-language embedding call'}
try:
    with engine.connect() as db:
        report['counts']={name:db.execute(text('SELECT count(*) FROM '+name)).scalar_one() for name in (
            'users','worlds','world_characters','posts','memory_items','relationship_states')}
        docs=db.execute(text('SELECT document_id,memory_item_id,owner_id,world_id,subject_world_character_id,kind,text,thread_id '
            "FROM pg_recall_documents WHERE searchable=1 AND namespace='recall:memory-episode-v1' AND generation="
            "(SELECT active FROM pg_search_state WHERE namespace='recall:memory-episode-v1') "
            'ORDER BY document_id LIMIT 200')).mappings().all()
        vectors=db.execute(text('SELECT * FROM pg_memory_vectors WHERE generation=(SELECT active FROM pg_vector_state WHERE singleton=true) '
            'ORDER BY document_id LIMIT 3')).mappings().all()
        vector_generation=db.execute(text('SELECT active FROM pg_vector_state WHERE singleton=true')).scalar_one()
    keyword=PostgresMemoryRecallIndex(engine,settings=MemoryRecallIndexSettings.for_representation('episode_v1'))
    doctor=keyword.open();assert doctor.healthy
    report['keyword_doctor']={'healthy':doctor.healthy,'documents':doctor.document_count,'provider':doctor.provider}
    hits=[]
    # A rare literal copied from saved text checks that the actual migrated
    # document can be found; neither the literal nor body is written to results.
    for row in docs[:30]:
        terms=sorted(set(re.findall(r'[A-Za-z]{4,}|[가-힣]{2,}',row['text'])),key=lambda v:(-len(v),v))[:12]
        for term in terms:
            start=time.monotonic()
            found=keyword.search(MemoryRecallSearchQuery(
                MemoryScope(row['owner_id'],row['world_id'],row['subject_world_character_id']),term,
                (RecallDocumentKind(row['kind']),),50,
                allowed_thread_ids=(row['thread_id'],) if row['thread_id'] else ()),deadline=time.monotonic()+10)
            if any(h.document_id==row['document_id'] for h in found):
                hits.append({'document_id':row['document_id'],'memory_id':row['memory_item_id'],
                    'results':len(found),'milliseconds':round((time.monotonic()-start)*1000,2)})
                break
        if len(hits)>=3:break
    assert hits or not docs,'migrated_keyword_document_not_found'
    report['keyword_hits']=hits
    vector=PostgresMemoryVectorIndex(engine,generation=vector_generation)
    report['vector_contract']=vector.open();exact=[]
    for row in vectors:
        # psycopg without a vector adapter returns the validated vector text.
        embedding=json.loads(row['embedding']) if isinstance(row['embedding'],str) else list(row['embedding'])
        scope=MemoryScope(row['owner_id'],row['world_id'],row['subject_id'])
        result=vector.search(MemoryVectorQuery(scope,row['profile'],embedding,limit=50,
            allowed_thread_ids=(row['thread_id'],) if row['thread_id'] else ()),
            cancellation=PostgresSearchCancellation(time.monotonic()+10))
        hit=next(h for h in result.hits if h.document_id==row['document_id'])
        assert abs(hit.distance)<=0.00001
        # The same existing vector must never cross the owner boundary.
        foreign=vector.search(MemoryVectorQuery(MemoryScope('qa-'+uuid.uuid4().hex,scope.world_id,
            scope.subject_world_character_id),row['profile'],embedding),
            cancellation=PostgresSearchCancellation(time.monotonic()+10))
        assert not foreign.hits and foreign.allowed_count==0
        exact.append({'document_id':row['document_id'],'memory_id':row['memory_item_id'],
            'self_distance':hit.distance,'allowed_count':result.allowed_count,'wrong_owner_results':0})
    report['existing_vector_hits']=exact
    report['vector_fixture_available']=bool(vectors)
    report['status']='PASS'
finally:engine.dispose()
print(json.dumps(report,ensure_ascii=False))
