import math,time,uuid
from dataclasses import replace
from datetime import UTC,datetime,timedelta
import pytest
from sqlalchemy import text
from postgresql.test_canonical_contracts import engine,no_sqlite
from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex,PostgresSearchCancellation
from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError
from app.domains.memory.contracts.vector_projection import MemoryVectorDocument,MemoryVectorQuery
from app.domains.memory.contracts.scope import MemoryScope

@pytest.fixture
def index(engine):
    value=PostgresMemoryVectorIndex(engine,generation='test-'+uuid.uuid4().hex)
    assert 'exact cosine 768' in value.open()
    return value

def document(**overrides):
    scope=MemoryScope('social-uow-owner','social-uow-world','social-uow-owner-actor')
    data=dict(document_id='memory-item:'+uuid.uuid4().hex,memory_item_id=uuid.uuid4().hex,scope=scope,version=1,
        content_hash='a'*64,profile='gemini-768-v1',vector=(1.,)+(0.,)*767,occurred_at=datetime.now(UTC))
    data.update(overrides)
    return MemoryVectorDocument(**data)

def query(index,doc,**kwargs):
    return index.search(MemoryVectorQuery(doc.scope,doc.profile,doc.vector,**kwargs),cancellation=PostgresSearchCancellation(time.monotonic()+3))

def test_exact_cosine_ranking_and_scope_filters(index):
    d=document();a=replace(d,document_id=d.document_id+'a',vector=(.8,.6)+(0.,)*766)
    b=replace(d,document_id=d.document_id+'b',vector=(0.,1.)+(0.,)*766)
    other=replace(d,document_id=d.document_id+'other',scope=replace(d.scope,subject_world_character_id='other'))
    other_profile=replace(d,document_id=d.document_id+'profile',profile='other-model')
    index.upsert((b,other,a,d,other_profile))
    result=query(index,d)
    assert [h.document_id for h in result.hits]==[d.document_id,a.document_id,b.document_id]
    assert result.allowed_count==3 and result.index_kind=='flat'
    assert [h.distance for h in result.hits]==pytest.approx([0,.2,1],abs=1e-6)

def test_no_lower_version_and_metadata_update_preserves_vector(index):
    d=document(version=3);index.upsert((d,))
    index.upsert((replace(d,version=2,content_hash='b'*64,vector=(0.,1.)+(0.,)*766),))
    assert index.matches(d) and index.identity(d.document_id)==(3,'a'*64,d.profile)
    at=d.occurred_at+timedelta(seconds=1)
    index.refresh_version(d.document_id,content_hash='a'*64,version=4,scope=d.scope,occurred_at=at,counterpart_world_character_id='peer',thread_id='thread')
    current=replace(d,version=4,occurred_at=at,counterpart_world_character_id='peer',thread_id='thread')
    assert index.matches(current)
    assert query(index,current,counterpart_world_character_id='peer',thread_id='thread').hits[0].distance==pytest.approx(0)
    assert not query(index,current,counterpart_world_character_id='different').hits
    assert not query(index,current,occurred_to=at).hits


def test_private_thread_boundary_keeps_public_memories_before_top_k(index):
    public=document()
    current=replace(public,document_id=public.document_id+'current',thread_id='current')
    foreign=replace(public,document_id=public.document_id+'foreign',thread_id='foreign')
    index.upsert((public,current,foreign))
    result=query(index,public,allowed_thread_ids=('current',))
    assert {row.document_id for row in result.hits}=={public.document_id,current.document_id}
    assert result.allowed_count==2
    assert [row.document_id for row in query(index,public,allowed_thread_ids=()).hits]==[public.document_id]

def test_erasure_includes_all_generations(index,engine):
    other=PostgresMemoryVectorIndex(engine,generation='retained-'+uuid.uuid4().hex);other.open()
    d=document();index.upsert((d,));other.upsert((d,))
    index.erase_items([d.memory_item_id])
    assert index.identity(d.document_id) is None and other.identity(d.document_id) is None

def test_cancel_invalid_vector_and_no_approximate_index(index,engine):
    d=document()
    for vec in [(0.,)*768,(float('nan'),)+(0.,)*767,(1.,)*767,(True,)+(0.,)*767]:
        with pytest.raises(ValueError):index.upsert((replace(d,vector=vec),))
    token=PostgresSearchCancellation(time.monotonic()+5);token.cancel()
    with pytest.raises(MemoryVectorProjectionError,match='cancelled'):
        index.search(MemoryVectorQuery(d.scope,d.profile,d.vector),cancellation=token)
    with engine.connect() as c:
        assert not c.execute(text("SELECT 1 FROM pg_indexes WHERE tablename='pg_memory_vectors' AND (indexdef LIKE '%hnsw%' OR indexdef LIKE '%ivfflat%')")).first()
