"""One current source decision for owner detail's episode and evidence cards."""
from app.domains.memory.contracts.inspector import (
    SituationDetailMaterial, MemoryEvidenceRead, MemoryEvidenceAvailability,
)
from app.domains.memory.contracts.provenance import MemorySourceTypeV1
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.repository.access_batch import prepare_access
from app.domains.memory.repository.situation_reads import situation_origin, read_manifest
from app.domains.memory.repository.episode_privacy import currently_accessible
from app.domains.memory.repository.episode_packets import SqlAlchemyEpisodePackets
from app.domains.memory.repository.situation_packets import exact_source_entries
from app.domains.memory.policies.retrievability import item_retrievable
from app.domains.memory.policies.episode_packets import bounded_episode_packets
from app.domains.memory.policies.episode_provider_view import episode_provider_view
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.episode_inspector import public_episode_packet


def situation_detail(db, scope, item_id, now):
    item = db.get(MemoryItem, item_id, populate_existing=True)
    if item is None or (item.owner_id, item.world_id, item.subject_world_character_id) != (
            scope.owner_id, scope.world_id, scope.subject_world_character_id):
        return SituationDetailMaterial((), None)
    reader = RuntimeEpisodeDetailReader(db)
    validation = prepare_access(db, (item,), now, reader=reader)
    try:
        info = situation_origin(db, item, validation=validation)
    except ValueError:
        return SituationDetailMaterial((), None)
    if info is None:
        return None  # Only genuine legacy memories use legacy evidence policy.
    material = read_manifest(db, info, validation=validation)
    if material is None:
        return SituationDetailMaterial((), None)
    context = material[0]
    rows = sorted(validation.collections[("situation_sources", info.memory_item_id)], key=lambda row: row.ordinal)[:50]
    try:
        entries = exact_source_entries(db, info, context, rows, validation=validation)
    except (ValueError, TypeError, KeyError):
        return SituationDetailMaterial((), None)
    allowed = item_retrievable(item, now) and currently_accessible(db, reader, scope, item, now, validation=validation)
    evidence = []
    for entry in entries:
        try:
            kind = MemorySourceTypeV1(entry.source_type)
        except ValueError:
            continue
        access = reader.validate_situation_source(context, entry, now=now, validation=validation) if allowed else None
        current = None if access is None else access.evidence
        accepted = access is not None and access.state == "available" and current is not None
        state = (MemoryEvidenceAvailability.AVAILABLE if accepted else
            MemoryEvidenceAvailability.DELETED if access is not None and access.state == "deleted" else MemoryEvidenceAvailability.UNAVAILABLE)
        originals = reader.read_situation_sources(scope=scope, identities=((entry.source_type, entry.source_id),),
            context=context, entries=(entry,), now=now, validation=validation) if accepted else {}
        original = originals.get((entry.source_type, entry.source_id))
        valid = original is not None and all(0 <= a <= b <= len(original.text) for a, b in entry.ranges)
        excerpt = " ".join(" ".join(original.text[a:b] for a, b in entry.ranges).split())[:500] if valid else None
        if accepted and not valid:
            accepted, state = False, MemoryEvidenceAvailability.UNAVAILABLE
        evidence.append(MemoryEvidenceRead(kind, current.source_created_at if current is not None else item.valid_from,
            state, excerpt, current.actor_world_character_id if accepted else None,
            current.target_world_character_id if accepted else None, current.counterpart_world_character_id if accepted else None,
            current.thread_id if accepted else None, current.source_id if accepted else None))
    packets = SqlAlchemyEpisodePackets(db, detail_reader=reader).read(scope=scope, item_ids=(item_id,),
        now=now, require_enabled=False, validation=validation)
    view = bounded_episode_packets(episode_provider_view(packets))
    return SituationDetailMaterial(tuple(evidence), public_episode_packet(view.packets[0]) if view.packets else None)
