"""After-commit lifecycle for the private canonical Memory recall index."""

from __future__ import annotations

from enum import StrEnum
import logging

from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.domains.memory.infrastructure import (
    MemoryItem,
    MemoryItemEvidence,
    MemoryScopeSettingModel,
)
from app.runtime.memory.sqlalchemy_recall import (
    SqlAlchemyMemoryRecallDocumentSource,
)
from app.runtime.memory.sqlite_fts5_recall import (
    MemoryRecallIndexError,
    MemoryRecallIndexSchemaError,
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
    ) -> None:
        self.index = index
        self._factory = session_factory
        self._source = SqlAlchemyMemoryRecallDocumentSource(session_factory)
        self._listening = False
        self.state = MemoryRecallProjectionState.STOPPED

    def start(self) -> None:
        self.state = MemoryRecallProjectionState.REBUILDING
        try:
            try:
                self.index.open()
            except MemoryRecallIndexSchemaError:
                # A projection schema mismatch is recoverable because canonical
                # SQLite is authoritative and the new file is built in staging.
                logger.warning("memory_recall_projection_schema_rebuild")
            doctor = self.index.rebuild(self._source.all_documents())
            if not doctor.healthy:
                self.state = MemoryRecallProjectionState.DEGRADED
                return
            self._listen()
            self.state = MemoryRecallProjectionState.READY
        except MemoryRecallIndexSchemaError:
            logger.exception("memory_recall_projection_schema_mismatch")
            self.state = MemoryRecallProjectionState.SCHEMA_MISMATCH
        except (MemoryRecallIndexError, OSError, ValueError):
            logger.exception("memory_recall_projection_unavailable")
            self.state = MemoryRecallProjectionState.DEGRADED
        except Exception:
            # Never fail canonical startup because a disposable projection
            # cannot be constructed. Recall remains explicitly degraded.
            logger.exception("memory_recall_projection_rebuild_failed")
            self.state = MemoryRecallProjectionState.DEGRADED

    def stop(self) -> None:
        self._unlisten()
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
        if not getattr(orm_execute_state, "is_update", False):
            return
        statement = getattr(orm_execute_state, "statement", None)
        table = getattr(statement, "table", None)
        if getattr(table, "name", None) == MemoryScopeSettingModel.__tablename__:
            getattr(orm_execute_state, "session").info[_PENDING_FULL_SYNC] = True

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
        item_ids = set(session.info.pop(_PENDING_ITEM_IDS, ()))
        setting_ids = tuple(session.info.pop(_PENDING_SETTING_IDS, ()))
        full_sync = bool(session.info.pop(_PENDING_FULL_SYNC, False))
        if not item_ids and not setting_ids and not full_sync:
            return
        try:
            if full_sync:
                item_ids.update(self._source.all_item_ids())
            for setting_id in sorted(setting_ids):
                resolved = self._source.scope_setting(setting_id)
                if resolved is None:
                    continue
                scope, enabled = resolved
                if not enabled:
                    self.index.tombstone_scope(
                        owner_id=scope.owner_id,
                        world_id=scope.world_id,
                        subject_world_character_id=(
                            scope.subject_world_character_id
                        ),
                    )
                    continue
                item_ids.update(self._source.item_ids_for_scope_setting(setting_id))

            documents = self._source.documents_for_item_ids(item_ids)
            for item_id in sorted(item_ids):
                item_documents = documents.get(item_id, ())
                if item_documents:
                    self.index.replace_memory_item(
                        memory_item_id=item_id,
                        documents=item_documents,
                    )
                else:
                    self.index.tombstone_memory_item(memory_item_id=item_id)
            self.state = (
                MemoryRecallProjectionState.READY
                if self.index.doctor().healthy
                else MemoryRecallProjectionState.DEGRADED
            )
        except Exception:
            # This listener executes after canonical commit. Projection failure
            # cannot roll back the already successful Memory transaction.
            logger.exception("memory_recall_projection_commit_sync_failed")
            self.state = MemoryRecallProjectionState.DEGRADED

    @staticmethod
    def _after_rollback(session: Session) -> None:
        session.info.pop(_PENDING_ITEM_IDS, None)
        session.info.pop(_PENDING_SETTING_IDS, None)
        session.info.pop(_PENDING_FULL_SYNC, None)


__all__ = [
    "EmbeddedMemoryRecallProjection",
    "MemoryRecallProjectionState",
]
