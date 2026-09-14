"""Recovery iterates durable eligibility only, never pre-existing stored memories."""
from datetime import UTC, datetime
from sqlalchemy import select
from app.domains.memory.models.embedding import MemoryVectorEligibility, MemoryEmbeddingSetting
from app.domains.memory.models.items import MemoryItem, MemoryScopeSettingModel
from app.domains.memory.contracts.embedding import MemoryEmbeddingConfiguration
from app.domains.memory.repository.recall_records import _item_scope, _item_retrievable


def eligible_page(session, *, after="", limit=64):
    if not 1 <= limit <= 256:
        raise ValueError("memory_vector_work_limit")
    return tuple(session.scalars(select(MemoryVectorEligibility.memory_item_id).where(
        MemoryVectorEligibility.memory_item_id > after).order_by(MemoryVectorEligibility.memory_item_id).limit(limit)))


def read_work(session, item_id):
    registration = session.get(MemoryVectorEligibility, item_id)
    item = session.get(MemoryItem, item_id)
    if registration is None or item is None or not _item_retrievable(item, datetime.now(UTC)):
        return None
    scope = _item_scope(item)
    setting = session.scalar(select(MemoryScopeSettingModel).where(
        MemoryScopeSettingModel.owner_id == scope.owner_id, MemoryScopeSettingModel.world_id == scope.world_id,
        MemoryScopeSettingModel.subject_world_character_id == scope.subject_world_character_id))
    config = None if setting is None else session.get(MemoryEmbeddingSetting, setting.id)
    if setting is None or not setting.enabled or config is None or not config.enabled:
        return None
    return (scope, MemoryEmbeddingConfiguration(config.enabled, config.provider, config.model, config.credential_id,
        config.profile, config.version), registration.content_hash, item.version)


def retained_registration(session, item_id):
    item = session.get(MemoryItem, item_id)
    return (item is not None and _item_retrievable(item, datetime.now(UTC))
            and session.get(MemoryVectorEligibility, item_id) is not None)
