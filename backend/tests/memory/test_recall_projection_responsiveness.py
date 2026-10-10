"""Slow canonical validation cannot run on startup or a committing request."""
from threading import Event, Thread
from time import monotonic

import pytest

from memory.test_p8_l_h_canonical_recall import runtime_factory, _accept_chat_memory, drain_projection
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, RecallDocumentKind
from app.domains.memory.models.items import MemoryItem
from app.runtime.memory.recall_projection import EmbeddedMemoryRecallProjection, MemoryRecallProjectionState
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath

pytestmark = pytest.mark.usefixtures("deny_external_network")


def test_background_start_and_commit_return_while_source_validation_is_blocked(runtime_factory, tmp_path, monkeypatch):
    scope, _, _, _, item_id = _accept_chat_memory(runtime_factory)
    index = SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path))
    projection = EmbeddedMemoryRecallProjection(index=index, session_factory=runtime_factory)
    entered, release, committed = Event(), Event(), Event()
    errors = []
    original = projection._source.documents_for_item_ids
    def slow(ids, **kwargs):
        entered.set()
        assert release.wait(5), "source validation blocked the caller"
        return original(ids, **kwargs)
    monkeypatch.setattr(projection._source, "documents_for_item_ids", slow)
    started = monotonic()
    projection.start()
    assert monotonic() - started < 1
    try:
        assert entered.wait(2)
        def edit():
            try:
                with runtime_factory() as db:
                    item = db.get(MemoryItem, item_id)
                    item.summary, item.version = "Updated while rebuilding", item.version + 1
                    db.commit()
            except BaseException as exc:
                errors.append(exc)
            finally:
                committed.set()
        writer = Thread(target=edit)
        writer.start()
        assert committed.wait(1), "canonical commit waited for the projection worker"
        assert not errors
    finally:
        release.set()
        projection.stop()
        if 'writer' in locals(): writer.join()
    # Queued work is disposable. Startup revalidation must recover even when the
    # first worker was stopped before draining its committed edit.
    resumed = EmbeddedMemoryRecallProjection(index=SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path)), session_factory=runtime_factory)
    resumed.start(background=False)
    try:
        drain_projection(resumed)
        hits = resumed.index.search(MemoryRecallSearchQuery(scope, "Updated", (RecallDocumentKind.MEMORY_ITEM,), 10))
        assert [hit.memory_item_id for hit in hits] == [item_id]
        assert hits[0].snippet == "Updated while rebuilding"
    finally:
        resumed.stop()


def test_queue_overflow_rebuilds_and_rollback_never_projects(runtime_factory, tmp_path):
    _, _, _, _, item_id = _accept_chat_memory(runtime_factory)
    projection = EmbeddedMemoryRecallProjection(index=SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path)), session_factory=runtime_factory)
    projection.start(background=False)
    try:
        drain_projection(projection)
        assert projection.is_caught_up
        with runtime_factory() as db:
            item = db.get(MemoryItem, item_id)
            item.summary = "Must not be indexed"
            db.flush()
            db.rollback()
        assert not projection._pending_items and not projection._full_sync
        projection._enqueue(tuple(f"deleted-{n}" for n in range(101)))
        assert not projection.is_caught_up
        assert not projection._pending_items and projection._full_sync
        drain_projection(projection)
        assert projection.state is MemoryRecallProjectionState.READY
        assert projection.index.doctor().healthy
        assert projection.is_caught_up
    finally:
        projection.stop()
