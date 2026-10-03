"""Bounded, durable rebuild against authoritative SQLite rather than fake cursors."""
from datetime import UTC, datetime
import json

import pytest
from sqlalchemy import select, update

from memory.test_p8_l_h_canonical_recall import runtime_factory, _accept_chat_memory
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.contracts.recall import MemoryRecallPreparing, MemoryRecallSearchQuery, RecallDocumentKind
from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection, MemoryRecallProjectionState
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath

pytestmark = pytest.mark.usefixtures("deny_external_network")


def fill(factory, original_id, count):
    with factory() as db:
        original = db.get(MemoryItem, original_id)
        values = {column.name: getattr(original, column.name) for column in MemoryItem.__table__.columns}
        # Original evidence remains authoritative; padding rows only exercise
        # paging and are deliberately not used as source-return assertions.
        for number in range(count):
            db.add(MemoryItem(**{**values, "id": f"padding-{number:05d}", "summary": "Padding record"}))
        db.commit()


def complete(projection):
    pages = 0
    while projection.state is MemoryRecallProjectionState.REBUILDING and pages < 100:
        projection.advance_rebuild(max_pages=1)
        pages += 1
    assert projection.state is MemoryRecallProjectionState.READY
    return pages


def test_cancel_restart_reconciles_offline_correction_and_deletion_before_search(runtime_factory, tmp_path):
    scope, _, _, _, original_id = _accept_chat_memory(runtime_factory)
    fill(runtime_factory, original_id, 1001)
    root = StaticRuntimeDataPath(tmp_path / "projection")
    index = SqliteMemoryRecallIndex(root)
    first = EmbeddedMemoryRecallProjection(index=index, session_factory=runtime_factory)
    first.start(background=False)
    try:
        assert first.state is MemoryRecallProjectionState.REBUILDING
        cursor = json.loads(first._cursor_path.read_text())
        assert cursor["phase"] == "build" and cursor["cursor"]
        with pytest.raises(MemoryRecallPreparing):
            index.search(MemoryRecallSearchQuery(scope, "약속", (RecallDocumentKind.MEMORY_ITEM,), 10))
    finally:
        first.stop()
    assert first._cursor_path.exists()
    with runtime_factory() as db:
        original = db.get(MemoryItem, original_id)
        original.summary = "The coffee meeting for A-17 was cancelled."
        original.version += 1
        deleted = db.get(MemoryItem, "padding-00000")
        deleted.status = "deleted"
        deleted.deleted_at = datetime.now(UTC)
        db.commit()
    second_index = SqliteMemoryRecallIndex(root)
    resumed = EmbeddedMemoryRecallProjection(index=second_index, session_factory=runtime_factory)
    resumed.start(background=False)
    try:
        complete(resumed)
        assert not resumed._cursor_path.exists()
        hits = second_index.search(MemoryRecallSearchQuery(scope, "coffee", (RecallDocumentKind.MEMORY_ITEM,), 10))
        assert [hit.memory_item_id for hit in hits] == [original_id]
        assert hits[0].snippet == "The coffee meeting for A-17 was cancelled."
        assert not second_index.search(MemoryRecallSearchQuery(scope, "약속", (RecallDocumentKind.MEMORY_ITEM,), 10))
        with second_index._connect(second_index.database_path) as connection:
            assert connection.execute("SELECT searchable FROM memory_recall_documents WHERE memory_item_id=?", ("padding-00000",)).fetchone() in (None, (0,))
        assert second_index.doctor().healthy
    finally:
        resumed.stop()


def test_committed_edit_during_rebuild_uses_same_fence_and_small_transaction(runtime_factory, tmp_path, monkeypatch):
    scope, _, _, _, identifier = _accept_chat_memory(runtime_factory)
    fill(runtime_factory, identifier, 1001)
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path / "projection"))
    projection = EmbeddedMemoryRecallProjection(index=index, session_factory=runtime_factory)
    monkeypatch.setattr(projection._source, "all_documents", lambda: pytest.fail("unbounded source scan"))
    pages = []
    original_page = projection._source.item_id_page
    def bounded(**kwargs):
        pages.append(kwargs["limit"])
        return original_page(**kwargs)
    monkeypatch.setattr(projection._source, "item_id_page", bounded)
    projection.start(background=False)
    try:
        with runtime_factory() as db:
            item = db.get(MemoryItem, identifier)
            item.summary = "New art. No party agreement for A-17."
            item.version += 1
            db.commit()
        complete(projection)
        assert pages and max(pages) == 100
        hits = index.search(MemoryRecallSearchQuery(scope, "art", (RecallDocumentKind.MEMORY_ITEM,), 10))
        assert [hit.memory_item_id for hit in hits] == [identifier]
        assert hits[0].snippet == "New art. No party agreement for A-17."
        assert not index.search(MemoryRecallSearchQuery(scope, "tea", (RecallDocumentKind.MEMORY_ITEM,), 10))
    finally:
        projection.stop()


def test_old_generation_files_are_preserved_and_wrong_profile_is_rejected(tmp_path):
    from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings, MemoryRecallIndexSchemaError
    root = StaticRuntimeDataPath(tmp_path)
    old = SqliteMemoryRecallIndex(root, settings=MemoryRecallIndexSettings(generation="v1"))
    old.open()
    original = old.database_path.read_bytes()
    old.close()
    current = SqliteMemoryRecallIndex(root)
    current.open()
    assert current.database_path != old.database_path and old.database_path.read_bytes() == original
    with pytest.raises(MemoryRecallIndexSchemaError):
        SqliteMemoryRecallIndex.reader(old.database_path)
    current.close()
