"""Hydrate selected situation cores, never the background/privacy manifest."""
from sqlalchemy import select

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry
from app.domains.memory.contracts.episode_packet import EpisodePacket, EpisodePacketSource, EpisodePacketUnit
from app.domains.memory.models.activity_situation import MemoryActivitySituationSource
from app.domains.memory.repository.situation_reads import read_manifest, situation_accessible


def exact_source_entries(session, info, manifest, rows, *, validation=None):
    """No other item, ordinal, source, digest or range can supply this proof."""
    from app.domains.memory.models.items import MemoryItemEvidence
    expected = {entry.ordinal: entry for entry in (*manifest.sources, *manifest.result_sources)}
    entries = []
    for row in rows:
        entry = DeliveredSourceEntry.from_dict(row.source)
        if (row.memory_item_id != info.memory_item_id or row.ordinal != entry.ordinal
                or expected.get(entry.ordinal) != entry):
            raise ValueError("situation_detail_source_binding_invalid")
        if row.evidence_id is not None:
            evidence = session.get(MemoryItemEvidence, row.evidence_id) if validation is None else validation.get(MemoryItemEvidence, row.evidence_id)
            if (evidence is None or evidence.memory_item_id != info.memory_item_id
                or (evidence.source_type, evidence.source_id, evidence.source_digest) !=
                   (entry.source_type, entry.source_id, entry.source_digest)):
                raise ValueError("situation_detail_evidence_binding_invalid")
        entries.append(entry)
    return entries


def read_situation_packet(session, reader, scope, item, info, now, *, validation=None):
    from app.domains.memory.repository.experience import accessible, packet
    if not accessible(session,scope,item,now,validation=validation):
        return None
    return packet(session,item,validation=validation)
