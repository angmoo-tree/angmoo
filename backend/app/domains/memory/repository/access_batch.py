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
    values = load_rows(context, model, column, ids)
    for identifier in ids:
        context.rows[(model, identifier)] = None
    for row in values:
        context.rows[(model, getattr(row, column.key))] = row
    return values


def prepare_access(session, items, now, *, reader=None, validation=None):
    context = validation if validation is not None else MemoryAccessValidation(session, now)
    context.check_context(session, now)
    frontier = {row.id for row in items if (MemoryItem, row.id) not in context.rows}
    # Follow unique nodes rather than paths. Policy recursion checks cycles before memo.
    while frontier:
        rows = indexed(context, MemoryItem, MemoryItem.id, frontier)
        ids = tuple(row.id for row in rows)
        infos = indexed(context, MemoryActivitySituationInfo, MemoryActivitySituationInfo.memory_item_id, ids)
        indexed(context, MemoryEpisodeInfo, MemoryEpisodeInfo.memory_item_id, ids)
        restrictions = indexed(context, MemoryEpisodeRestriction, MemoryEpisodeRestriction.memory_item_id, ids)
        sources = load_rows(context, MemoryActivitySituationSource, MemoryActivitySituationSource.memory_item_id, ids)
        evidences = load_rows(context, MemoryItemEvidence, MemoryItemEvidence.memory_item_id, ids)
        for evidence in evidences:
            context.rows[(MemoryItemEvidence, evidence.id)] = evidence
        for identifier in ids:
            context.collections[("situation_sources", identifier)] = tuple(row for row in sources if row.memory_item_id == identifier)
        receipts = indexed(context, MemorySituationReceipt, MemorySituationReceipt.sequence,
            (row.receipt_sequence for row in infos))
        manifests = indexed(context, MemorySituationManifest, MemorySituationManifest.id,
            (row.manifest_id for row in receipts if row.manifest_id))
        indexed(context, MemoryScopeSettingModel, MemoryScopeSettingModel.id, (row.scope_setting_id for row in receipts))
        bindings = load_rows(context, MemorySituationSourceBinding, MemorySituationSourceBinding.manifest_id,
            (row.id for row in manifests))
        for manifest in manifests:
            context.collections[("source_bindings", manifest.id)] = tuple(row for row in bindings if row.manifest_id == manifest.id)
        result_bindings = load_rows(context, MemorySituationResultBinding, MemorySituationResultBinding.receipt_sequence,
            (row.sequence for row in receipts))
        for receipt in receipts:
            context.collections[("result_bindings", receipt.sequence)] = tuple(row for row in result_bindings if row.receipt_sequence == receipt.sequence)
        parents = load_rows(context, MemoryItem, MemoryItem.superseded_by_id, ids)
        for identifier in ids:
            context.collections[("correction_parents", identifier)] = tuple(row for row in parents if row.superseded_by_id == identifier)
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
        frontier = {identifier for identifier in prior_ids if isinstance(identifier, str)
            and (MemoryItem, identifier) not in context.rows}
    if reader is not None:
        from app.domains.memory.repository.situation_reads import read_manifest
        contexts = []
        for (model, _), info in tuple(context.rows.items()):
            if model is MemoryActivitySituationInfo and info is not None:
                material = read_manifest(session, info, validation=context)
                if material is not None:
                    contexts.append(material[0])
        prepare = getattr(reader, "prepare_situation_sources", None)
        if prepare is not None:
            prepare(tuple(contexts), validation=context)
    return context
