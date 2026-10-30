"""Bulk manifest loading; missing original material does not erase a situation."""

from dataclasses import asdict
from hashlib import sha256
import json

from sqlalchemy import select

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.contracts.episode_packet import EpisodePacket, EpisodePacketSource, EpisodePacketUnit
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.models.episode import MemoryEpisodeInfo, MemoryEpisodeUnit, MemoryEpisodeUnitEvidence, MemoryEpisodeLink
from app.domains.memory.repository.recall_records import _item_retrievable
from app.domains.memory.service.items import memory_evidence_blocked_code


class SqlAlchemyEpisodePackets:
    def __init__(self, session, *, detail_reader):
        self.session, self.reader = session, detail_reader

    def read(self, *, scope, item_ids, now, require_enabled=True, validation=None):
        ids = tuple(dict.fromkeys(item_ids))
        if len(ids) > 50:
            raise ValueError("episode_packet_candidate_limit")
        if not ids:
            return ()
        if validation is None:
            return self._read(scope=scope, item_ids=ids, now=now, require_enabled=require_enabled)
        validation.check_context(self.session, now)
        missing = tuple(identifier for identifier in ids if (scope, identifier, require_enabled) not in validation.packets)
        if missing:
            packets = self._read(scope=scope, item_ids=missing, now=now,
                require_enabled=require_enabled, validation=validation)
            found = {packet.reference: packet for packet in packets}
            validation.packets.update(((scope, identifier, require_enabled), found.get(identifier)) for identifier in missing)
        return tuple(validation.packets[(scope, identifier, require_enabled)] for identifier in ids
            if validation.packets[(scope, identifier, require_enabled)] is not None)

    def _read(self, *, scope, item_ids, now, require_enabled=True, validation=None):
        from app.domains.memory.repository.access_batch import prepare_access
        from app.domains.memory.repository.experience import accessible, packet
        from app.domains.memory.repository.situation_reads import representation
        rows = list(self.session.scalars(select(MemoryItem).where(
            MemoryItem.id.in_(item_ids), MemoryItem.owner_id == scope.owner_id,
            MemoryItem.world_id == scope.world_id,
            MemoryItem.subject_world_character_id == scope.subject_world_character_id)))
        validation = prepare_access(self.session, rows, now, validation=validation)
        by_id = {row.id:row for row in rows if accessible(self.session,scope,row,now,
            validation=validation,require_enabled=require_enabled)}
        return tuple(packet(self.session,by_id[identifier],validation=validation,
            representation=representation(self.session,by_id[identifier],validation=validation))
            for identifier in item_ids if identifier in by_id)
