"""Erase one subject's private records on the caller's deletion transaction."""
from datetime import UTC, datetime
from sqlalchemy import delete, or_, select, update
from app.domains.memory.models.items import (MemoryScopeSettingModel, MemoryItem, MemoryItemEvidence,
    MemoryHotBrief, MemoryHotBriefItem, MemoryCandidate, MemoryMaintenanceJob)
from app.domains.memory.models.activity_configuration import MemorySubjectProfile, MemoryIndexPreparation, MemoryEpisodeRestriction


def erase_subject(db, *, owner_id, world_id, actor_id):
    scopes = select(MemoryScopeSettingModel.id).where(MemoryScopeSettingModel.owner_id == owner_id,
        MemoryScopeSettingModel.world_id == world_id, MemoryScopeSettingModel.subject_world_character_id == actor_id)
    items = select(MemoryItem.id).where(MemoryItem.owner_id == owner_id, MemoryItem.world_id == world_id,
        MemoryItem.subject_world_character_id == actor_id)
    identities = list(db.scalars(items))
    briefs = select(MemoryHotBrief.id).where(MemoryHotBrief.scope_setting_id.in_(scopes))
    db.execute(delete(MemoryHotBriefItem).where(or_(MemoryHotBriefItem.brief_id.in_(briefs), MemoryHotBriefItem.memory_item_id.in_(items))))
    db.execute(delete(MemoryHotBrief).where(MemoryHotBrief.id.in_(briefs)))
    db.execute(delete(MemoryEpisodeRestriction).where(MemoryEpisodeRestriction.memory_item_id.in_(items)))
    db.execute(delete(MemoryItemEvidence).where(MemoryItemEvidence.memory_item_id.in_(items)))
    db.execute(update(MemoryItem).where(MemoryItem.superseded_by_id.in_(items), MemoryItem.id.not_in(items))
        .values(status="deleted", superseded_by_id=None, deleted_at=datetime.now(UTC)))
    db.execute(delete(MemoryMaintenanceJob).where(MemoryMaintenanceJob.scope_setting_id.in_(scopes)))
    db.execute(delete(MemoryCandidate).where(MemoryCandidate.scope_setting_id.in_(scopes)))
    db.execute(delete(MemoryItem).where(MemoryItem.id.in_(items)))
    for model in (MemoryIndexPreparation, MemorySubjectProfile):
        db.execute(delete(model).where(model.scope_setting_id.in_(scopes)))
    db.execute(delete(MemoryScopeSettingModel).where(MemoryScopeSettingModel.id.in_(scopes)))
    return identities
