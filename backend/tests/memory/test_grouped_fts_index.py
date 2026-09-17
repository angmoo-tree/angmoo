from dataclasses import replace
from time import monotonic
import pytest
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, MemoryRecallLexicalPolicy, RecallDocumentKind
from app.runtime.memory import grouped_fts_search as grouped
from memory.test_korean_memory_recall_quality import SCOPE, document, build_index


def query(text, **kwargs):
    return MemoryRecallSearchQuery(SCOPE,text,(RecallDocumentKind.MEMORY_ITEM,),50,
        lexical_policy=MemoryRecallLexicalPolicy.GROUP_OR_V1,**kwargs)


def test_natural_language_and_collision(tmp_path):
    index=build_index(tmp_path,[document('m24','아시도와 9월 10일 축제 공연을 연습했고 9월 13일 공연은 취소됐다.'),
        document('collision','아버지 가방에 편지가 있었다')])
    result=index.search_grouped(query('아시도와 축제 공연을 진행했는지 확인'),deadline=monotonic()+5)
    assert [r.memory_item_id for r in result.candidates]==['m24']
    assert result.status.value=='ready'
    assert not index.search_grouped(query('아버지가'),deadline=monotonic()+5).candidates
    with pytest.raises(ValueError): index.search(query('축제'))


@pytest.mark.parametrize('field,value',[('owner_id','foreign'),('world_id','foreign'),('subject_world_character_id','foreign'),('searchable',False),('kind',RecallDocumentKind.POST)])
def test_scope_before_candidate_limit(tmp_path,field,value):
    docs=[replace(document(str(n),'별빛 축제'),**{field:value}) for n in range(210)]
    docs.append(document('allowed','별빛 축제'))
    index=build_index(tmp_path,docs)
    result=index.search_grouped(query('별빛 축제 언제'),deadline=monotonic()+5)
    assert [r.memory_item_id for r in result.candidates]==['allowed']


def test_budget_deadline_and_sql_error(tmp_path,monkeypatch):
    index=build_index(tmp_path,[document('large','축제 '+ 'x'*2000)])
    monkeypatch.setattr(grouped,'MAX_BYTES',20)
    result=index.search_grouped(query('축제'),deadline=monotonic()+5)
    assert result.status.value=='partial' and not result.candidates
    assert result.stats['bytes_scanned']==0
    assert index.search_grouped(query('축제'),deadline=monotonic()-1).reason_code=='fts_deadline_exceeded'
    with index._connect(index.database_path) as c: c.execute('DROP TABLE memory_recall_fts')
    assert index.search_grouped(query('축제'),deadline=monotonic()+5).reason_code=='fts_sql_error'


def test_input_truncated_never_ready(tmp_path):
    index=build_index(tmp_path,[document('a','축제')])
    result=index.search_grouped(query('축제 '+ '가'*1100),deadline=monotonic()+5)
    assert result.status.value=='partial' and result.candidates


def test_window_exhaustion_is_not_absence(tmp_path):
    index=build_index(tmp_path,[document(str(n),'아버지 가방에 편지가 있었다') for n in range(201)])
    result=index.search_grouped(query('아버지가'),deadline=monotonic()+5)
    assert not result.candidates and result.reason_code=='fts_candidate_window_exhausted'
    assert result.status.value=='partial' and result.stats['scanned']==200


def test_source_hash_uses_full_raw_document(tmp_path):
    import hashlib
    text='축제 '+ '내용 '*150
    index=build_index(tmp_path,[document('a',text,metadata={'item_version':'7'})])
    result=index.search_grouped(query('축제'),deadline=monotonic()+5)
    row=result.candidates[0]
    assert row.metadata['item_version']=='7'
    assert row.metadata['document_content_hash']==hashlib.sha256(text.strip().encode()).hexdigest()
    assert len(row.snippet)==240


def test_read_transaction_keeps_candidate_snapshot(tmp_path,monkeypatch):
    from app.runtime.memory import sqlite_fts5_recall as adapter
    index=build_index(tmp_path,[document('a','축제 옛 기록'),document('b','축제 옛 기록')])
    original=adapter._row_to_candidate
    changed=False
    def convert(row):
        nonlocal changed
        if not changed:
            changed=True
            with index._connect(index.database_path) as writer:
                writer.execute("UPDATE memory_recall_documents SET text='새 기록' WHERE document_id='b'")
        return original(row)
    monkeypatch.setattr(adapter,'_row_to_candidate',convert)
    result=index.search_grouped(query('축제'),deadline=monotonic()+5)
    assert len(result.candidates)==2
    assert all(c.snippet=='축제 옛 기록' for c in result.candidates)


def test_time_window_is_applied_before_candidate_window(tmp_path):
    from datetime import UTC,datetime
    old=datetime(2026,9,10,tzinfo=UTC)
    wanted=datetime(2026,9,13,tzinfo=UTC)
    docs=[replace(document(str(n),'별빛 축제'),occurred_at=old) for n in range(210)]
    docs.append(replace(document('allowed','별빛 축제'),occurred_at=wanted))
    index=build_index(tmp_path,docs)
    result=index.search_grouped(query('별빛 축제 언제',occurred_from=wanted,
        occurred_to=datetime(2026,9,14,tzinfo=UTC)),deadline=monotonic()+5)
    assert [r.memory_item_id for r in result.candidates]==['allowed']
