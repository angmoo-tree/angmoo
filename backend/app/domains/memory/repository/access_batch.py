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
    ids = tuple(row.id for row in items)
    indexed(context, MemoryActivitySituationInfo, MemoryActivitySituationInfo.memory_item_id, ids)
    indexed(context, MemoryEpisodeInfo, MemoryEpisodeInfo.memory_item_id, ids)


def prepare_access(session, items, now, *, reader=None, validation=None):
    context = validation if validation is not None else MemoryAccessValidation(session, now)
    context.check_context(session, now)
    pending = tuple(row for row in items if row.id not in context.prepared_items)
    if pending:
        prepare_representation(context, pending)
        from app.domains.memory.repository.experience import prepare
        prepare(session, pending, now, validation=context)
    return context

def prepare_packet_sources(context, infos):
    """Materialize only selected origins, including corrected-item origins."""
    ids = tuple(dict.fromkeys(info.memory_item_id for info in infos if info is not None))
    sources = collection(context, "situation_sources", MemoryActivitySituationSource,
        MemoryActivitySituationSource.memory_item_id, ids)
    # Fetch by the exact referenced evidence identity. The packet boundary still
    # checks memory owner, ordinal, source, digest and range before disclosure.
    indexed(context, MemoryItemEvidence, MemoryItemEvidence.id,
        (row.evidence_id for row in sources if row.evidence_id is not None))
