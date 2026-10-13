"""Slow canonical validation cannot run on startup or a committing request."""
from threading import Event, Thread
from time import monotonic

import pytest

from memory.test_p8_l_h_canonical_recall import runtime_factory, _accept_chat_memory, drain_projection
from app.domains.memory.contracts.recall import MemoryRecallSearchQuery, RecallDocumentKind
from app.domains.memory.contracts.recall import MemoryRecallPreparing
from sqlalchemy.exc import TimeoutError as PoolCheckoutTimeout
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


def test_transient_checkout_retries_without_a_commit_and_retains_search_fence(runtime_factory, tmp_path, monkeypatch):
    scope, _, _, _, item_id = _accept_chat_memory(runtime_factory)
    projection = EmbeddedMemoryRecallProjection(index=SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path)),
        session_factory=runtime_factory)
    failed, promoted = Event(), Event()
    original_page, original_promote = projection._source.item_id_page, projection.index.promote_rebuild
    attempts = []
    def page(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            failed.set()
            raise PoolCheckoutTimeout("synthetic pool exhaustion")
        return original_page(**kwargs)
    def promote(writer):
        original_promote(writer)
        promoted.set()
    monkeypatch.setattr(projection._source, "item_id_page", page)
    monkeypatch.setattr(projection.index, "promote_rebuild", promote)
    projection.start()
    try:
        assert failed.wait(2)
        with pytest.raises(MemoryRecallPreparing):
            projection.index.search(MemoryRecallSearchQuery(scope, "약속", (RecallDocumentKind.MEMORY_ITEM,), 10))
        assert promoted.wait(5), "degraded worker waited forever for another commit"
        assert all(request["limit"] == 32 for request in attempts)
        assert projection.index.doctor().healthy
        assert projection.state is MemoryRecallProjectionState.READY
    finally:
        projection.stop()


def test_persistent_failure_obeys_deadline_and_stop_interrupts_backoff(runtime_factory, tmp_path, monkeypatch):
    projection = EmbeddedMemoryRecallProjection(index=SqliteMemoryRecallIndex(StaticRuntimeDataPath(tmp_path)),
        session_factory=runtime_factory)
    clock, calls = [0.0], []
    monkeypatch.setattr("app.runtime.memory.recall_projection.monotonic", lambda: clock[0])
    def unavailable(**kwargs):
        calls.append(1)
        raise PoolCheckoutTimeout("synthetic pool exhaustion")
    monkeypatch.setattr(projection._source, "item_id_page", unavailable)
    projection.start(background=False)
    try:
        deadlines = []
        for expected in (1, 2, 4, 8, 16, 30, 30):
            projection.advance_rebuild()
            assert projection.state is MemoryRecallProjectionState.DEGRADED
            deadlines.append(projection._retry_after - clock[0])
            before = len(calls)
            projection.advance_rebuild()
            assert len(calls) == before
            clock[0] = projection._retry_after
        assert deadlines == [1, 2, 4, 8, 16, 30, 30]
        started = monotonic()
        projection.stop()
        assert monotonic() - started < 1
    finally:
        if projection.state is not MemoryRecallProjectionState.STOPPED:
            projection.stop()
