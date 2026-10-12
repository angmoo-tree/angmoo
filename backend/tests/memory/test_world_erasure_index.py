"""Physical private-text erasure is distinct from ordinary index tombstoning."""
from dataclasses import replace
from datetime import UTC, datetime
from app.domains.memory.contracts.recall import MemoryRecallDocument, RecallDocumentKind
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath


def test_exact_erasure_removes_searchable_and_tombstoned_text_and_keeps_other_items(tmp_path):
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path))
    index.open()
    target = MemoryRecallDocument(document_id="target", memory_item_id="item-a", owner_id="owner",
        world_id="a", subject_world_character_id="actor-a", kind=RecallDocumentKind.MEMORY_ITEM,
        canonical_source_id="item-a", text="private target memory", occurred_at=datetime.now(UTC))
    survivor = replace(target, document_id="survivor", memory_item_id="item-b", canonical_source_id="item-b", world_id="b", text="surviving memory")
    index.rebuild((target, survivor))
    index.tombstone_memory_item(memory_item_id="item-a")
    with index._connect(index.database_path) as db:
        assert db.execute("SELECT count(*) FROM memory_recall_documents WHERE memory_item_id='item-a'").fetchone()[0] == 1
    index.erase_memory_items(("item-a",))
    with index._connect(index.database_path) as db:
        assert db.execute("SELECT count(*) FROM memory_recall_documents WHERE memory_item_id='item-a'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM memory_recall_documents WHERE memory_item_id='item-b'").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM memory_recall_fts WHERE document_id='target'").fetchone()[0] == 0
    assert index.doctor().healthy
    index.erase_memory_items(("item-a",))
    index.close()


def test_social_index_erasure_pages_remove_private_text_and_keep_other_world(tmp_path):
    from app.runtime.search.sqlite_fts5 import SqliteFts5SearchIndex
    from app.domains.runtime.contracts.search import SearchIndexDocument
    index = SqliteFts5SearchIndex(StaticRuntimeDataPath(tmp_path))
    index.open()
    index.rebuild(tuple(SearchIndexDocument(document_id=f"a-{i}", world_id="a", kind="world_post", text="target private text", metadata={}) for i in range(105)) +
        (SearchIndexDocument(document_id="b", world_id="b", kind="world_post", text="surviving searchable text", metadata={}),))
    assert not index.erase_world("a", limit=100)
    assert index.erase_world("a", limit=100)
    assert index.search(world_id="a", query="private", limit=10) == ()
    assert [hit.document_id for hit in index.search(world_id="b", query="surviving", limit=10)] == ["b"]
    assert index.doctor().document_count == 1
    index.close()


def test_rebuild_and_rollback_images_cannot_restore_erased_memory(runtime_factory, tmp_path):
    from memory.test_p8_l_h_canonical_recall import _accept_chat_memory, drain_projection
    from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection
    from app.domains.memory.models.items import MemoryItem
    from sqlalchemy import delete
    scope, _, _, _, item = _accept_chat_memory(runtime_factory)
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "projection"))
    projection = EmbeddedMemoryRecallProjection(index=index, session_factory=runtime_factory)
    projection.start(background=False)
    drain_projection(projection)
    # Keep a managed rollback copy of the old text, then begin another rebuild.
    index.rebuild(tuple(projection._source.documents_for_item_ids((item,)).get(item, ())))
    projection.request_rebuild()
    projection.advance_rebuild(max_pages=1)
    with runtime_factory() as db:
        db.get(MemoryItem, item).status = "deleted"
        db.get(MemoryItem, item).deleted_at = datetime.now(UTC)
        db.commit()
    projection.erase_memory_items((item,))
    drain_projection(projection)
    for path in (index.database_path, index.rollback_path, index.staging_path):
        if path.exists():
            import sqlite3
            with sqlite3.connect(path) as db:
                assert db.execute("SELECT count(*) FROM memory_recall_documents WHERE memory_item_id=?", (item,)).fetchone()[0] == 0
    projection.stop()


# These fixtures require the actual Vec1 build; the isolated Docker run supplies
# the image's shipped extension rather than substituting a fake vector store.
from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.test_sqlite_vec1 import index as vector_index, document


def test_real_vec1_erasure_clears_vectors_documents_and_failed_attempts(vector_index):
    vector_index.upsert((document("target"), document("survivor")))
    with vector_index._connect() as db:
        db.execute("CREATE TABLE embedding_attempts_v2(document_id TEXT, attempts INTEGER)")
        db.executemany("INSERT INTO embedding_attempts_v2 VALUES(?,1)", [("target",), ("memory-item:never-indexed",), ("survivor",)])
        db.commit()
    vector_index.erase_items(("target", "never-indexed"))
    assert vector_index.identity("target") is None
    assert vector_index.identity("survivor") is not None
    with vector_index._connect() as db:
        assert db.execute("SELECT document_id FROM embedding_attempts_v2").fetchall() == [("survivor",)]


def test_real_retained_vector_generations_are_all_acknowledged(tmp_path, vector_index):
    from memory.test_vector_generations import generations
    from app.runtime.memory.hybrid_runtime import MemoryHybridRuntime
    manager = generations(tmp_path / "retained", vector_index)
    active, _ = manager.open()
    active.upsert((document("target"), document("survivor")))
    manager.state["staging"] = "g-" + "c" * 32
    staging = manager._index(manager.state["staging"])
    staging.open()
    staging.upsert((document("target"), document("survivor")))
    manager.promote(staging)
    runtime = object.__new__(MemoryHybridRuntime)
    runtime._generations = manager
    runtime.erase_items(("target",))
    for generation in (active, staging):
        assert generation.identity("target") is None and generation.identity("survivor") is not None
