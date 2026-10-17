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
    material = read_manifest(session, info, validation=validation)
    if material is None:
        return None
    manifest, _ = material
    if not situation_accessible(session, reader, scope, item, info, now, ancestors=frozenset(), validation=validation):
        # An owner can inspect the stored summary, but inspection never bypasses
        # any background input's current access boundary to disclose originals.
        return EpisodePacket(item.id, item.summary, "activity_situation_v1", ())
    rows = (list(validation.collections[("situation_sources", info.memory_item_id)])
        if validation is not None and ("situation_sources", info.memory_item_id) in validation.collections
        else list(session.scalars(select(MemoryActivitySituationSource).where(
        MemoryActivitySituationSource.memory_item_id == info.memory_item_id).order_by(
            MemoryActivitySituationSource.ordinal).limit(101))))
    rows.sort(key=lambda row: row.ordinal)
    truncated = len(rows) > 100
    try:
        entries = exact_source_entries(session, info, manifest, rows[:100], validation=validation)
    except (ValueError, TypeError, KeyError):
        return EpisodePacket(item.id, item.summary, "activity_situation_v1", ())
    access = {entry.ordinal: reader.validate_situation_source(manifest, entry, now=now, validation=validation) for entry in entries}
    identities = tuple(dict.fromkeys((entry.source_type, entry.source_id) for entry in entries
        if access[entry.ordinal].state == "available" and access[entry.ordinal].evidence is not None))
    source_reader = getattr(reader, "read_situation_sources", None)
    originals = (reader.read_sources(scope=scope, identities=identities) if source_reader is None else
        source_reader(scope=scope, identities=identities, context=manifest, entries=tuple(entries), now=now, validation=validation))
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
                original.text[start:end] if valid else None, "verified" if valid else "changed", start, end,
                original.author_id if valid else None,
                original.evidence.source_created_at if valid else None))
    thought = ActivityThought()
    if info.thought_reference and any(source.status == "verified" and source.role == "committed_result" for source in sources):
        thought = reader.read_thoughts(scope=scope, references=(info.thought_reference,)).get(info.thought_reference, thought)
    unit = EpisodePacketUnit(f"situation:{info.receipt_sequence}", tuple(sources), thought,
        info.thought_reference if thought.status != "missing" else None,
        "partial" if truncated or any(entry.partial for entry in entries) else "complete")
    return EpisodePacket(item.id, item.summary, "activity_situation_v1", (unit,), followup_truncated=truncated)
