"""After-commit lifecycle for the private canonical Memory recall index."""

from __future__ import annotations

from app.core import work_observation as observation

from enum import StrEnum
from contextlib import contextmanager
import logging
import json
from threading import Event, Lock, RLock, Thread
from time import monotonic
from app.core.atomic_json import write_json

from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.items import MemoryItemEvidence
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.runtime.memory.recall_composition import recall_document_source as SqlAlchemyMemoryRecallDocumentSource
from app.runtime.memory.sqlite_fts5_recall import (
    MemoryRecallIndexError,
    SqliteMemoryRecallIndex,
)


logger = logging.getLogger(__name__)
_PENDING_ITEM_IDS = "angmoo_memory_recall_pending_item_ids"
_PENDING_SETTING_IDS = "angmoo_memory_recall_pending_setting_ids"
_PENDING_FULL_SYNC = "angmoo_memory_recall_pending_full_sync"
_PAGE_SIZE = 32
_QUEUE_LIMIT = 100


class MemoryRecallProjectionState(StrEnum):
    STOPPED = "stopped"
    REBUILDING = "rebuilding"
    READY = "ready"
    DEGRADED = "degraded"
    SCHEMA_MISMATCH = "schema_mismatch"


class EmbeddedMemoryRecallProjection:
    """Rebuild on startup and mirror only successfully committed Memory rows."""

    def __init__(
        self,
        *,
        index: SqliteMemoryRecallIndex,
        session_factory: sessionmaker[Session],
        episode_only: bool = False,
    ) -> None:
        self.index = index
        self._factory = session_factory
        self._source = SqlAlchemyMemoryRecallDocumentSource(session_factory, episode_only=episode_only)
        self._listening = False
        self._rebuild_lock = RLock()
        # Commit listeners never take the worker's I/O lock. Only bounded IDs
        # cross threads; Sessions and source validation stay in the worker.
        self._pending_lock = Lock()
        self._pending_items = set()
        self._pending_settings = set()
        self._full_sync = False
        self._wake = Event()
        self._working = Event()
        self._stopping = Event()
        self._thread = None
        self._writer = None
        self._retry_after = 0.0
        self._retry_delay = 1.0
        self._cursor_path = index.progress_path if getattr(index,'provider',None)=='postgresql' else index.database_path.with_name("rebuild-progress.json")
        self.state = MemoryRecallProjectionState.STOPPED

    def _read_progress(self):
        if hasattr(self.index, 'load_progress'):
            return self.index.load_progress()
        return json.loads(self._cursor_path.read_text(encoding='utf-8'))

    def _write_progress(self):
        if hasattr(self.index, 'save_progress'):
            self.index.save_progress(self._progress)
        else:
            write_json(self._cursor_path, self._progress)

    def _clear_progress(self):
        if hasattr(self.index, 'save_progress'):
            self.index.save_progress(None)
        else:
            self._cursor_path.unlink(missing_ok=True)

    @property
    def is_caught_up(self):
        """Shutdown must include queued commits, not just a promoted generation."""
        with self._pending_lock:
            return (self.state is MemoryRecallProjectionState.READY
                and not self._working.is_set() and not self._pending_items
                and not self._pending_settings and not self._full_sync)

    @contextmanager
    def _work(self):
        with self._rebuild_lock:
            self._working.set()
            try:
                yield
            finally:
                self._working.clear()

    def start(self, *, background: bool = True) -> None:
        self._stopping.clear()
        self.state = MemoryRecallProjectionState.REBUILDING
        try:
            self.index.open()
            self._writer = self.index.rebuild_writer()
            try:
                progress = self._read_progress()
                if progress["generation"] != self.index.settings.generation or progress["phase"] not in {"build", "validate", "orphans"}:
                    raise ValueError()
                # Resume the original cursor, then reconcile all authoritative
                # rows before promotion (including offline edits/deletions).
                self._progress = progress
            except (OSError, ValueError, KeyError, TypeError):
                self._progress = {"generation": self.index.settings.generation, "phase": "build", "cursor": ""}
            self._write_progress()
            self._listen()
            if background:
                self._thread = Thread(target=self._rebuild_loop, name="memory-fts-rebuild", daemon=True)
                self._thread.start()
        except Exception:
            logger.exception("memory_recall_projection_rebuild_failed")
            self.state = MemoryRecallProjectionState.DEGRADED

    def _rebuild_loop(self):
        while not self._stopping.is_set():
            self._wake.clear()
            self.advance_rebuild(max_pages=1)
            if self.state is MemoryRecallProjectionState.REBUILDING:
                self._stopping.wait(0.01)
            elif self.state is MemoryRecallProjectionState.DEGRADED:
                # A transient checkout/index failure must not wait forever for
                # another commit. Persistent failures retry at most every 30s.
                self._stopping.wait(max(0.01, self._retry_after - monotonic()))
            else:
                self._wake.wait()

    def request_rebuild(self):
        """Large committed changes schedule bounded work, not a request-time scan."""
        self._enqueue(full_sync=True)

    def erase_memory_items(self, identifiers):
        """Serialize erasure with source reads, delayed writes and promotion."""
        with self._work():
            if hasattr(self.index,'erase_retained'):
                self.index.erase_retained(tuple(identifiers))
                return
            self.index.erase_memory_items(identifiers)
            if self._writer is not None:
                self._writer.erase_memory_items(identifiers)
            # Retained disposable images are part of managed projection cleanup.
            for path in (self.index.rollback_path, self.index.staging_path):
                if not path.exists():
                    continue
                image = object.__new__(type(self.index))
                image.settings, image.database_path = self.index.settings, path
                image.staging_path, image.rollback_path = path.with_suffix(".unused-stage"), path.with_suffix(".unused-rollback")
                image._lock, image._opened = RLock(), False
                image.open()
                try:
                    image.erase_memory_items(identifiers)
                finally:
                    image.close()

    def _begin_rebuild(self):
        with self._rebuild_lock:
            if self._writer is None:
                self._writer = self.index.rebuild_writer()
            self._progress = {"generation": self.index.settings.generation, "phase": "build", "cursor": ""}
            self._write_progress()
            self.state = MemoryRecallProjectionState.REBUILDING

    def _enqueue(self, item_ids=(), setting_ids=(), *, full_sync=False):
        with self._pending_lock:
            if self._stopping.is_set():
                return  # Startup reconciliation recovers commits at shutdown.
            self._pending_items.update(item_ids)
            self._pending_settings.update(setting_ids)
            self._full_sync = self._full_sync or full_sync or (
                len(self._pending_items) + len(self._pending_settings) > _QUEUE_LIMIT)
            if self._full_sync:
                self._pending_items.clear()
                self._pending_settings.clear()
        self._wake.set()

    @observation.observed("fts_projection_apply")
    def _apply_pending(self):
        with self._pending_lock:
            item_ids, setting_ids, full_sync = self._pending_items, self._pending_settings, self._full_sync
            self._pending_items, self._pending_settings, self._full_sync = set(), set(), False
        if not item_ids and not setting_ids and not full_sync:
            return
        try:
            for identifier in setting_ids:
                item_ids.update(self._source.item_ids_for_scope_setting(identifier, limit=_QUEUE_LIMIT + 1))
                if len(item_ids) > _QUEUE_LIMIT:
                    full_sync = True
                    break
            if full_sync:
                self._begin_rebuild()
                return
            documents = self._source.documents_for_item_ids(item_ids)
            target = self._writer if self._writer is not None else self.index
            target.replace_memory_items({identifier: documents.get(identifier, ()) for identifier in sorted(item_ids)})
        except Exception:
            # Retain recovery intent after derived-index failure. A subsequent
            # wakeup retries a full rebuild; restart also reconciles canonical SQL.
            with self._pending_lock:
                self._full_sync = True
            raise

    def advance_rebuild(self, *, max_pages=1):
        if not 1 <= max_pages <= 3:
            raise ValueError("memory_recall_rebuild_page_budget_invalid")
        try:
            with self._work():
                if self.state is MemoryRecallProjectionState.DEGRADED:
                    if monotonic() < self._retry_after:
                        return
                    self.state = MemoryRecallProjectionState.REBUILDING
                for _ in range(max_pages):
                    if self._stopping.is_set():
                        return
                    self._apply_pending()
                    if self._stopping.is_set() or self.state is not MemoryRecallProjectionState.REBUILDING:
                        return
                    phase, cursor = self._progress["phase"], self._progress["cursor"]
                    ids = (self._writer.memory_item_id_page(after=cursor, limit=_PAGE_SIZE) if phase == "orphans"
                        else self._source.item_id_page(after=cursor, limit=_PAGE_SIZE))
                    if ids:
                        documents = self._source.documents_for_item_ids(ids)
                        self._writer.replace_memory_items({identifier: documents.get(identifier, ()) for identifier in ids})
                        self._progress["cursor"] = ids[-1]
                    elif phase == "build":
                        self._progress.update(phase="validate", cursor="")
                    elif phase == "validate":
                        self._progress.update(phase="orphans", cursor="")
                    else:
                        self.index.promote_rebuild(self._writer)
                        self._writer = None
                        self._clear_progress()
                        self.state = MemoryRecallProjectionState.READY
                        self._retry_delay = 1.0
                        return
                    self._write_progress()
                    self._retry_delay = 1.0
        except Exception:
            logger.exception("memory_recall_projection_page_failed")
            self.state = MemoryRecallProjectionState.DEGRADED
            self._retry_after = monotonic() + self._retry_delay
            self._retry_delay = min(self._retry_delay * 2, 30.0)

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            # Finish the owned page before closing its index or canonical engine.
            self._thread.join()
        with self._rebuild_lock:
            self._unlisten()
            if self._writer is not None:
                self._writer.close()
            self.index.close()
            self.state = MemoryRecallProjectionState.STOPPED

    def _listen(self) -> None:
        if self._listening:
            return
        event.listen(self._factory, "after_flush", self._after_flush)
        event.listen(self._factory, "do_orm_execute", self._do_orm_execute)
        event.listen(self._factory, "after_commit", self._after_commit)
        event.listen(self._factory, "after_rollback", self._after_rollback)
        self._listening = True

    def _unlisten(self) -> None:
        if not self._listening:
            return
        event.remove(self._factory, "after_flush", self._after_flush)
        event.remove(self._factory, "do_orm_execute", self._do_orm_execute)
        event.remove(self._factory, "after_commit", self._after_commit)
        event.remove(self._factory, "after_rollback", self._after_rollback)
        self._listening = False

    @staticmethod
    def _do_orm_execute(orm_execute_state: object) -> None:
        statement = getattr(orm_execute_state, "statement", None)
        table = getattr(statement, "table", None)
        session = getattr(orm_execute_state, "session")
        if (
            getattr(orm_execute_state, "is_delete", False)
            and getattr(table, "name", None) == MemoryItem.__tablename__
        ):
            # Account scrubbing uses a scoped bulk delete. Capture affected IDs
            # before deletion so the after-commit projection removes old text.
            query = select(MemoryItem.id)
            if statement.whereclause is not None:
                query = query.where(statement.whereclause)
            identifiers = tuple(session.connection().execute(query.limit(101)).scalars())
            if len(identifiers) > 100:
                session.info[_PENDING_FULL_SYNC] = True
            else:
                session.info.setdefault(_PENDING_ITEM_IDS, set()).update(identifiers)
        if (
            getattr(orm_execute_state, "is_update", False)
            and getattr(table, "name", None) == MemoryScopeSettingModel.__tablename__
            # Receipt admission serializes writers with id=id. That lock is
            # not a settings mutation and must not rebuild historical memory.
            and not orm_execute_state.execution_options.get("memory_scope_lock_only", False)
        ):
            query = select(MemoryScopeSettingModel.id)
            if statement.whereclause is not None:
                query = query.where(statement.whereclause)
            identifiers = tuple(session.connection().execute(query.limit(101)).scalars())
            if len(identifiers) > 100:
                session.info[_PENDING_FULL_SYNC] = True
            else:
                session.info.setdefault(_PENDING_SETTING_IDS, set()).update(identifiers)

    @staticmethod
    def _after_flush(session: Session, _flush_context: object) -> None:
        item_ids = session.info.setdefault(_PENDING_ITEM_IDS, set())
        setting_ids = session.info.setdefault(_PENDING_SETTING_IDS, set())
        for entity in session.new | session.dirty | session.deleted:
            if isinstance(entity, MemoryItem):
                item_ids.add(entity.id)
            elif isinstance(entity, MemoryItemEvidence):
                item_ids.add(entity.memory_item_id)
            elif isinstance(entity, MemoryScopeSettingModel):
                setting_ids.add(entity.id)

    def _after_commit(self, session: Session) -> None:
        if session.in_nested_transaction():
            return
        item_ids = set(session.info.pop(_PENDING_ITEM_IDS, ()))
        setting_ids = tuple(session.info.pop(_PENDING_SETTING_IDS, ()))
        full_sync = bool(session.info.pop(_PENDING_FULL_SYNC, False))
        if not item_ids and not setting_ids and not full_sync:
            return
        self._enqueue(item_ids, setting_ids, full_sync=full_sync)

    @staticmethod
    def _after_rollback(session: Session) -> None:
        if session.in_nested_transaction():
            # Keep the conservative dirty set for earlier successful writes in
            # the outer transaction; discarded IDs will resolve to no documents.
            return
        session.info.pop(_PENDING_ITEM_IDS, None)
        session.info.pop(_PENDING_SETTING_IDS, None)
        session.info.pop(_PENDING_FULL_SYNC, None)


__all__ = [
    "EmbeddedMemoryRecallProjection",
    "MemoryRecallProjectionState",
]
