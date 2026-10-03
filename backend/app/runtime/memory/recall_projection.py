"""After-commit lifecycle for the private canonical Memory recall index."""

from __future__ import annotations

from enum import StrEnum
import logging
import json
from threading import Event, RLock, Thread
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
        self._stopping = Event()
        self._thread = None
        self._writer = None
        self._cursor_path = index.database_path.with_name("rebuild-progress.json")
        self.state = MemoryRecallProjectionState.STOPPED

    def start(self, *, background: bool = True) -> None:
        self._stopping.clear()
        self.state = MemoryRecallProjectionState.REBUILDING
        try:
            self.index.open()
            self._writer = self.index.rebuild_writer()
            try:
                progress = json.loads(self._cursor_path.read_text(encoding="utf-8"))
                if progress["generation"] != self.index.settings.generation or progress["phase"] not in {"build", "validate", "orphans"}:
                    raise ValueError()
                # Resume the original cursor, then reconcile all authoritative
                # rows before promotion (including offline edits/deletions).
                self._progress = progress
            except (OSError, ValueError, KeyError, TypeError):
                self._progress = {"generation": self.index.settings.generation, "phase": "build", "cursor": ""}
            write_json(self._cursor_path, self._progress)
            self._listen()
            for _ in range(3):
                self.advance_rebuild(max_pages=3)
            if background and self.state is MemoryRecallProjectionState.REBUILDING:
                self._thread = Thread(target=self._rebuild_loop, name="memory-fts-rebuild", daemon=True)
                self._thread.start()
        except Exception:
            logger.exception("memory_recall_projection_rebuild_failed")
            self.state = MemoryRecallProjectionState.DEGRADED

    def _rebuild_loop(self):
        while not self._stopping.is_set() and self.state is MemoryRecallProjectionState.REBUILDING:
            self.advance_rebuild(max_pages=1)
            self._stopping.wait(0.01)

    def request_rebuild(self):
        """Large committed changes schedule bounded work, not a request-time scan."""
        with self._rebuild_lock:
            if self._writer is None:
                self._writer = self.index.rebuild_writer()
            self._progress = {"generation": self.index.settings.generation, "phase": "build", "cursor": ""}
            write_json(self._cursor_path, self._progress)
            self.state = MemoryRecallProjectionState.REBUILDING
            if self._thread is None or not self._thread.is_alive():
                self._thread = Thread(target=self._rebuild_loop, name="memory-fts-rebuild", daemon=True)
                self._thread.start()

    def advance_rebuild(self, *, max_pages=1):
        if not 1 <= max_pages <= 3:
            raise ValueError("memory_recall_rebuild_page_budget_invalid")
        try:
            with self._rebuild_lock:
                for _ in range(max_pages):
                    if self._stopping.is_set() or self.state is not MemoryRecallProjectionState.REBUILDING:
                        return
                    phase, cursor = self._progress["phase"], self._progress["cursor"]
                    ids = (self._writer.memory_item_id_page(after=cursor, limit=100) if phase == "orphans"
                        else self._source.item_id_page(after=cursor, limit=100))
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
                        self._cursor_path.unlink(missing_ok=True)
                        self.state = MemoryRecallProjectionState.READY
                        return
                    write_json(self._cursor_path, self._progress)
        except Exception:
            logger.exception("memory_recall_projection_page_failed")
            self.state = MemoryRecallProjectionState.DEGRADED

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
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
        try:
            for identifier in setting_ids:
                item_ids.update(self._source.item_ids_for_scope_setting(identifier, limit=101))
                if len(item_ids) > 100:
                    break
            if full_sync or len(item_ids) > 100:
                self.request_rebuild()
                return

            with self._rebuild_lock:
                documents = self._source.documents_for_item_ids(item_ids)
                target = self._writer if self._writer is not None else self.index
                target.replace_memory_items({item_id: documents.get(item_id, ()) for item_id in sorted(item_ids)})
            # One transactional mutation already recomputed the full digest.
            # Full doctor remains available at startup and explicit diagnosis.
            if self._writer is None:
                self.state = MemoryRecallProjectionState.READY
        except Exception:
            # This listener executes after canonical commit. Projection failure
            # cannot roll back the already successful Memory transaction.
            logger.exception("memory_recall_projection_commit_sync_failed")
            self.state = MemoryRecallProjectionState.DEGRADED

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
