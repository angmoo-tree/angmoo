"""Hydrate selected situation cores, never the background/privacy manifest."""
from sqlalchemy import select

from app.contracts.activity_thought import ActivityThought
from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry
from app.domains.memory.contracts.episode_packet import EpisodePacket, EpisodePacketSource, EpisodePacketUnit
from app.domains.memory.models.activity_situation import MemoryActivitySituationSource
from app.domains.memory.repository.situation_reads import read_manifest, situation_accessible


def read_situation_packet(session, reader, scope, item, info, now):
    material = read_manifest(session, info)
    if material is None:
        return None
    manifest, _ = material
    if not situation_accessible(session, reader, scope, item, info, now, ancestors=frozenset()):
        # An owner can inspect the stored summary, but inspection never bypasses
        # any background input's current access boundary to disclose originals.
        return EpisodePacket(item.id, item.summary, "activity_situation_v1", ())
    rows = list(session.scalars(select(MemoryActivitySituationSource).where(
        MemoryActivitySituationSource.memory_item_id == info.memory_item_id).order_by(
            MemoryActivitySituationSource.ordinal).limit(101)))
    truncated = len(rows) > 100
    entries = [DeliveredSourceEntry.from_dict(row.source)
        for row in rows[:100]]
    access = {entry.ordinal: reader.validate_situation_source(manifest, entry, now=now) for entry in entries}
    identities = tuple(dict.fromkeys((entry.source_type, entry.source_id) for entry in entries
        if access[entry.ordinal].state == "available" and access[entry.ordinal].evidence is not None))
    source_reader = getattr(reader, "read_situation_sources", None)
    originals = (reader.read_sources(scope=scope, identities=identities) if source_reader is None else
        source_reader(scope=scope, identities=identities, context=manifest, entries=tuple(entries), now=now))
    sources = []
    for entry in entries:
        status = access[entry.ordinal].state
        original = originals.get((entry.source_type, entry.source_id))
        ranges = entry.ranges
        if status != "available" or original is None or not ranges:
            sources.append(EpisodePacketSource(f"{entry.source_type}:{entry.source_id}", entry.role, None,
                "missing" if status == "deleted" else "changed" if status == "changed" else "unavailable"))
            continue
        for start, end in ranges:
            valid = 0 <= start <= end <= len(original.text)
            sources.append(EpisodePacketSource(f"{entry.source_type}:{entry.source_id}", entry.role,
                original.text[start:end] if valid else None, "verified" if valid else "changed", start, end))
    thought = ActivityThought()
    if info.thought_reference and any(source.status == "verified" and source.role == "committed_result" for source in sources):
        thought = reader.read_thoughts(scope=scope, references=(info.thought_reference,)).get(info.thought_reference, thought)
    unit = EpisodePacketUnit(f"situation:{info.receipt_sequence}", tuple(sources), thought,
        info.thought_reference if thought.status != "missing" else None,
        "partial" if truncated or any(entry.partial for entry in entries) else "complete")
    return EpisodePacket(item.id, item.summary, "activity_situation_v1", (unit,), followup_truncated=truncated)
