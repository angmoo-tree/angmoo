"""Batch canonical source facts for one owner's frozen Chat evidence read."""
from datetime import UTC, datetime

from sqlalchemy import select

from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.access_batch import prepare_access
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.service.inspector import MemoryReadService
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_inspector import episode_receipt_view
from app.runtime.memory.situation_detail import situation_detail


class ChatMemoryEvidenceRead:
    def __init__(self, db, scope, item_ids, source_reader, *, now=None):
        ids = tuple(dict.fromkeys(item_ids))
        if len(ids) > 24:
            raise ValueError("chat_evidence_memory_limit")
        if db.new or db.dirty or db.deleted:
            raise ValueError("chat_evidence_memory_read_has_changes")
        self.db, self.scope, self.now = db, scope, now or datetime.now(UTC)
        self.transaction = db.get_transaction()
        self.ids = frozenset(ids)
        self.reader = RuntimeEpisodeDetailReader(db)
        rows = list(db.scalars(select(MemoryItem).where(
            MemoryItem.id.in_(ids), MemoryItem.owner_id == scope.owner_id,
            MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id,
        ).execution_options(populate_existing=True))) if ids else []
        self.validation = prepare_access(db, rows, self.now, reader=self.reader)
        # Read packet bodies/thoughts once as a bounded batch. Detail cards and
        # historical delivery comparison use the same freshly validated facts.
        SqlAlchemyEpisodePackets(db, detail_reader=self.reader).read(scope=scope,
            item_ids=ids, now=self.now, require_enabled=False, validation=self.validation)
        self.transaction = db.get_transaction()
        self.service = MemoryReadService(memory_repository(db), source_reader,
            situation_detail_reader=lambda scope, item_id, now: situation_detail(
                db, scope, item_id, now, validation=self.validation, reader=self.reader))

    def _check(self, item_id):
        if item_id not in self.ids or self.db.get_transaction() is not self.transaction:
            raise ValueError("chat_evidence_memory_operation_changed")
        if self.db.new or self.db.dirty or self.db.deleted:
            raise ValueError("chat_evidence_memory_read_has_changes")

    def detail(self, item_id):
        self._check(item_id)
        return self.service.detail(self.scope, item_id=item_id, now=self.now)

    def receipt(self, item_id, text):
        self._check(item_id)
        return episode_receipt_view(self.db, self.scope, item_id, self.now, text,
            validation=self.validation, reader=self.reader)
