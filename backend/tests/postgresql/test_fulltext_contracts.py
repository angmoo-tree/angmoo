import json,pathlib,uuid,time,sqlite3
from dataclasses import replace
import pytest
from postgresql.test_canonical_contracts import engine
from app.runtime.memory.postgresql_recall import PostgresMemoryRecallIndex
from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
from app.runtime.search.postgresql_fts import PostgresFtsSearchIndex
from app.runtime.search.sqlite_fts5 import SqliteFts5Settings
from app.domains.runtime.contracts.search import SearchIndexDocument,SearchIndexQuery
from memory import test_grouped_fts_index as contracts
from memory.test_korean_memory_recall_quality import document

@pytest.fixture
def index(engine,monkeypatch):
    def forbidden(*a,**k):raise AssertionError('PostgreSQL search opened SQLite')
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    value=PostgresMemoryRecallIndex(engine,settings=MemoryRecallIndexSettings(generation='pg-'+uuid.uuid4().hex))
    assert value.open().healthy
    def build(_path,docs):value.rebuild(docs);return value
    monkeypatch.setattr(contracts,'build_index',build)
    return value

def test_natural_language_collision(index,tmp_path):contracts.test_natural_language_and_collision(tmp_path)

@pytest.mark.parametrize('field,value',[('owner_id','foreign'),('world_id','foreign'),('subject_world_character_id','foreign'),('searchable',False),('kind',contracts.RecallDocumentKind.POST)])
def test_scope_filters_before_limit(index,tmp_path,field,value):contracts.test_scope_before_candidate_limit(tmp_path,field,value)

def test_time_scope_before_limit(index,tmp_path):contracts.test_time_window_is_applied_before_candidate_window(tmp_path)


def test_private_thread_boundary_preserves_public_and_current_before_limit(index):
    public=document('public-thread-scope','축제 약속')
    current=replace(document('current-thread-scope','축제 약속'),thread_id='current')
    foreign=replace(document('foreign-thread-scope','축제 약속'),thread_id='foreign')
    index.rebuild((public,current,foreign))
    batch=index.search_grouped(replace(contracts.query('축제 약속'),allowed_thread_ids=('current',)),deadline=time.monotonic()+5)
    assert {row.memory_item_id for row in batch.candidates}=={'public-thread-scope','current-thread-scope'}
    batch=index.search_grouped(replace(contracts.query('축제 약속'),allowed_thread_ids=()),deadline=time.monotonic()+5)
    assert [row.memory_item_id for row in batch.candidates]==['public-thread-scope']

def test_truncation_and_hash(index,tmp_path):
    contracts.test_input_truncated_never_ready(tmp_path)
    contracts.test_source_hash_uses_full_raw_document(tmp_path)

def test_candidate_window_exhaustion(index,tmp_path):contracts.test_window_exhaustion_is_not_absence(tmp_path)

def test_frozen_korean_corpus_and_retained_erasure(index):
    rows=json.loads((pathlib.Path(__file__).parents[1]/'memory/fixtures/grouped_fts_frozen.json').read_text(encoding='utf-8'))
    docs={r['expected']:document(r['expected'],r['text']) for r in rows}
    index.rebuild(docs.values())
    for split in ['development','heldout']:
        selected=[r for r in rows if r['split']==split];hits=0
        for r in selected:
            result=index.search_grouped(contracts.query(r['query']),deadline=time.monotonic()+5)
            assert result.status.value=='ready'
            hits+=r['expected'] in [c.memory_item_id for c in result.candidates[:10]]
        assert hits/len(selected)>=.9
    original=list(docs)[0]
    index.rebuild([document('replacement','새로운 기록')])
    assert index.doctor().rollback_available
    index.erase_memory_items([original])
    index.rollback()
    assert original not in index.memory_item_id_page(limit=1000)
    assert index.doctor().healthy

def test_budget_deadline_and_preparation_are_explicit(index,monkeypatch,tmp_path):
    from app.runtime.memory import postgresql_recall as adapter
    index.rebuild([document('large','축제 '+'x'*2000)])
    monkeypatch.setattr(adapter,'MAX_BYTES',20)
    result=index.search_grouped(contracts.query('축제'),deadline=time.monotonic()+5)
    assert result.status.value=='partial' and not result.candidates and result.stats['bytes_scanned']==0
    assert index.search_grouped(contracts.query('축제'),deadline=time.monotonic()-1).reason_code=='fts_deadline_exceeded'
    index.progress_path=tmp_path/'progress.json';index.progress_path.write_text('{}')
    with pytest.raises(adapter.MemoryRecallPreparing):index.search_grouped(contracts.query('축제'),deadline=time.monotonic()+5)

def test_sns_fulltext_scope_rebuild_rollback(engine):
    index=PostgresFtsSearchIndex(engine,settings=SqliteFts5Settings(generation='pg-'+uuid.uuid4().hex))
    assert index.open().healthy
    index.rebuild([SearchIndexDocument(document_id='a',world_id='one',text='메이와 도서관에서 보낸 시간',kind='post',metadata={}),
                   SearchIndexDocument(document_id='b',world_id='two',text='메이와 도서관에서 보낸 시간',kind='post',metadata={})])
    assert [h.document_id for h in index.search(world_id='one',query='도서관',limit=10)]==['a']
    index.rebuild([SearchIndexDocument(document_id='new',world_id='one',text='새로운 기록',kind='post',metadata={})])
    assert not index.search(world_id='one',query='도서관',limit=10)
    index.rollback()
    assert [h.document_id for h in index.search(world_id='one',query='도서관',limit=10)]==['a']
    assert index.erase_world('one')
    assert not index.search(world_id='one',query='도서관',limit=10)
    assert index.doctor().healthy and index.doctor().full_text_available and not index.doctor().fts5_available
