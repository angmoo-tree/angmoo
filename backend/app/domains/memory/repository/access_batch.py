"""Bounded operation-local canonical rows; policies still validate every proof."""
import json
from app.domains.memory.repository.access_rows import load_rows, indexed, collection, prepare_representation
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










def prepare_access(session, items, now, *, reader=None, validation=None):
    context = validation if validation is not None else MemoryAccessValidation(session, now)
    context.check_context(session, now)
    if context.experience_access is None and reader is not None:
        context.experience_access = getattr(reader, "experience_access", None)
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
