"""Bounded operation-local canonical rows; policies still validate every proof."""
import json
from sqlalchemy import select
from app.domains.memory.contracts.access_validation import MemoryAccessValidation
from app.domains.memory.models.items import MemoryItem, MemoryItemEvidence, MemoryScopeSettingModel
from app.domains.memory.models.activity_situation import (
    MemoryActivitySituationInfo, MemoryActivitySituationSource, MemorySituationReceipt, MemorySituationManifest,
)
from app.domains.memory.models.episode import MemoryEpisodeInfo
from app.domains.memory.models.activity_configuration import MemoryEpisodeRestriction
from app.domains.memory.models.situation_source_binding import MemorySituationSourceBinding
from app.domains.memory.models.situation_result_binding import MemorySituationResultBinding


def load_rows(context, model, column, identifiers):
    ids = tuple(dict.fromkeys(identifiers))
    rows = []
    for start in range(0, len(ids), 400):
        rows.extend(context.session.scalars(select(model).where(column.in_(ids[start:start + 400]))
            .execution_options(populate_existing=True)))
    return rows


def indexed(context, model, column, identifiers):
    ids = tuple(dict.fromkeys(identifiers))
    missing = tuple(identifier for identifier in ids if (model, identifier) not in context.rows)
    values = load_rows(context, model, column, missing)
    for identifier in missing:
        context.rows[(model, identifier)] = None
    for row in values:
        context.rows[(model, getattr(row, column.key))] = row
    return [context.rows[(model, identifier)] for identifier in ids if context.rows[(model, identifier)] is not None]


def collection(context, name, model, column, identifiers):
    ids = tuple(dict.fromkeys(identifiers))
    missing = tuple(identifier for identifier in ids if (name, identifier) not in context.collections)
    values = load_rows(context, model, column, missing)
    grouped = {identifier: [] for identifier in missing}
    for row in values:
        grouped[getattr(row, column.key)].append(row)
    context.collections.update(((name, identifier), tuple(rows)) for identifier, rows in grouped.items())
    return [row for identifier in ids for row in context.collections[(name, identifier)]]


def prepare_representation(context, items):
    """Only representation ancestry, not prior proofs or foreign source facts."""
    frontier, visited = {row.id for row in items}, set()
    while frontier:
        rows = indexed(context, MemoryItem, MemoryItem.id, frontier)
        ids = tuple(row.id for row in rows)
        indexed(context, MemoryActivitySituationInfo, MemoryActivitySituationInfo.memory_item_id, ids)
        indexed(context, MemoryEpisodeInfo, MemoryEpisodeInfo.memory_item_id, ids)
        collection(context, "situation_sources", MemoryActivitySituationSource, MemoryActivitySituationSource.memory_item_id, ids)
        parents = collection(context, "correction_parents", MemoryItem, MemoryItem.superseded_by_id, ids)
        visited.update(frontier)
        scopes = {row.id: (row.owner_id, row.world_id, row.subject_world_character_id) for row in rows}
        frontier = {row.id for row in parents if scopes.get(row.superseded_by_id)
            == (row.owner_id, row.world_id, row.subject_world_character_id)} - visited


def prepare_access(session, items, now, *, reader=None, validation=None):
    context = validation if validation is not None else MemoryAccessValidation(session, now)
    context.check_context(session, now)
    frontier = {row.id for row in items} - context.prepared_items
    # Follow unique nodes rather than paths. Policy recursion checks cycles before memo.
    while frontier:
        rows = indexed(context, MemoryItem, MemoryItem.id, frontier)
        ids = tuple(row.id for row in rows)
        infos = indexed(context, MemoryActivitySituationInfo, MemoryActivitySituationInfo.memory_item_id, ids)
        indexed(context, MemoryEpisodeInfo, MemoryEpisodeInfo.memory_item_id, ids)
        restrictions = indexed(context, MemoryEpisodeRestriction, MemoryEpisodeRestriction.memory_item_id, ids)
        collection(context, "situation_sources", MemoryActivitySituationSource, MemoryActivitySituationSource.memory_item_id, ids)
        evidences = load_rows(context, MemoryItemEvidence, MemoryItemEvidence.memory_item_id, ids)
        for evidence in evidences:
            context.rows[(MemoryItemEvidence, evidence.id)] = evidence
        receipts = indexed(context, MemorySituationReceipt, MemorySituationReceipt.sequence,
            (row.receipt_sequence for row in infos))
        manifests = indexed(context, MemorySituationManifest, MemorySituationManifest.id,
            (row.manifest_id for row in receipts if row.manifest_id))
        indexed(context, MemoryScopeSettingModel, MemoryScopeSettingModel.id, (row.scope_setting_id for row in receipts))
        collection(context, "source_bindings", MemorySituationSourceBinding, MemorySituationSourceBinding.manifest_id,
            (row.id for row in manifests))
        collection(context, "result_bindings", MemorySituationResultBinding, MemorySituationResultBinding.receipt_sequence,
            (row.sequence for row in receipts))
        parents = collection(context, "correction_parents", MemoryItem, MemoryItem.superseded_by_id, ids)
        prior_ids = {row.id for row in parents}
        for manifest in manifests:
            # Parse no proof here: malformed stored material must still fail in restore_context.
            payload = manifest.payload if isinstance(manifest.payload, dict) else {}
            source_rows = payload.get("sources", ())
            for source in source_rows if isinstance(source_rows, (list, tuple)) else ():
                if isinstance(source, dict) and source.get("source_type") == "MEMORY_ITEM":
                    prior_ids.add(source.get("source_id"))
        for row in restrictions:
            try:
                prior_ids.update(ref["id"] for ref in json.loads(row.priors_json))
            except (ValueError, TypeError, KeyError):
                pass
        context.prepared_items.update(frontier)
        frontier = {identifier for identifier in prior_ids if isinstance(identifier, str)} - context.prepared_items
    if reader is not None:
        from app.domains.memory.repository.situation_reads import read_manifest
        contexts = []
        for (model, _), info in tuple(context.rows.items()):
            if model is MemoryActivitySituationInfo and info is not None and info.memory_item_id in context.prepared_items and info.receipt_sequence not in context.prepared_manifests:
                material = read_manifest(session, info, validation=context)
                if material is not None:
                    contexts.append(material[0])
                context.prepared_manifests.add(info.receipt_sequence)
        prepare = getattr(reader, "prepare_situation_sources", None)
        if prepare is not None and contexts:
            prepare(tuple(contexts), validation=context)
    return context
