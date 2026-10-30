"""Bounded row caches shared by access preparation and experience rights."""
from sqlalchemy import select
from app.domains.memory.models.activity_situation import MemoryActivitySituationInfo
from app.domains.memory.models.episode import MemoryEpisodeInfo

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
