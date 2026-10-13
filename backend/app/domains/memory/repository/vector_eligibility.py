"""Register accepted content atomically with canonical Memory persistence."""
import hashlib
from app.domains.memory.models.embedding import MemoryVectorEligibility


def register_content(session, item, *, now):
    row = session.get(MemoryVectorEligibility, item.id)
    digest = hashlib.sha256(item.summary.encode("utf-8")).hexdigest()
    if row is None:
        row = MemoryVectorEligibility(memory_item_id=item.id, item_version=item.version,
            content_hash=digest, registration_revision="memory-vector.v1", registered_at=now)
        session.add(row)
    else:
        row.item_version, row.content_hash = item.version, digest
    from sqlalchemy import select
    from app.domains.memory.models.items import MemoryScopeSettingModel
    from app.domains.memory.models.embedding import MemoryEmbeddingSetting
    setting_id = session.scalar(select(MemoryScopeSettingModel.id).where(
        MemoryScopeSettingModel.owner_id == item.owner_id, MemoryScopeSettingModel.world_id == item.world_id,
        MemoryScopeSettingModel.subject_world_character_id == item.subject_world_character_id))
    config = session.get(MemoryEmbeddingSetting, setting_id) if setting_id else None
    if config is not None and config.enabled:
        row.registration_revision, row.registered_at = "memory-vector.incremental.v2", now
    return row
