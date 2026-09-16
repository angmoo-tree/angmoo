from dataclasses import replace

import pytest

from memory.test_korean_memory_recall_quality import document, build_index
from memory.test_korean_memory_recall import query


def test_batch_replacement_recomputes_once_and_removes_old_terms(tmp_path, monkeypatch):
    index = build_index(tmp_path, [document("a", "oldalpha"), document("b", "oldbeta")])
    refresh = index._refresh_state
    calls = []
    def count(connection):
        calls.append(1)
        return refresh(connection)
    monkeypatch.setattr(index, "_refresh_state", count)
    index.replace_memory_items({"a": [document("a", "newalpha")], "b": []})
    assert len(calls) == 1
    assert not index.search(query("oldalpha"))
    assert not index.search(query("oldbeta"))
    assert index.search(query("newalpha"))
    assert index.doctor().healthy
    index.close()


def test_batch_mutation_rolls_back_all_items_on_failure(tmp_path, monkeypatch):
    index = build_index(tmp_path, [document("a", "oldalpha"), document("b", "oldbeta")])
    original = index._upsert_document
    def fail(connection, item):
        if item.memory_item_id == "b":
            raise RuntimeError("injected_write_failure")
        return original(connection, item)
    monkeypatch.setattr(index, "_upsert_document", fail)
    with pytest.raises(RuntimeError):
        index.replace_memory_items({"a": [document("a", "newalpha")], "b": [document("b", "newbeta")]})
    assert index.search(query("oldalpha"))
    assert index.search(query("oldbeta"))
    assert not index.search(query("newalpha"))
    assert index.doctor().healthy
    index.close()


def test_materialized_doctor_still_detects_missing_and_mismatched_fts(tmp_path):
    index = build_index(tmp_path, [document("a", "원문 하나"), document("b", "원문 둘")])
    assert index.doctor().healthy
    with index._connect(index.database_path) as connection:
        connection.execute("UPDATE memory_recall_fts SET text='잘못된 내용' WHERE document_id='a'")
        connection.commit()
    assert not index.doctor().healthy
    index.rebuild([document("a", "원문 하나"), document("b", "원문 둘")])
    with index._connect(index.database_path) as connection:
        connection.execute("DELETE FROM memory_recall_fts WHERE document_id='b'")
        connection.commit()
    assert not index.doctor().healthy
    index.close()
