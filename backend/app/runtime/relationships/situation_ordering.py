"""Same-scope canonical application precedes relationship snapshot boundaries."""
from sqlalchemy import select, update, exists

from app.domains.memory.models.activity_situation import MemorySituationApplyRun
from app.domains.memory.models.items import MemoryScopeSettingModel


def scope_application_pending(world_id, actor_id):
    """Select other scopes while one scope waits for its canonical cutoff."""
    return exists(select(MemorySituationApplyRun.id).join(MemoryScopeSettingModel,
        MemoryScopeSettingModel.id == MemorySituationApplyRun.scope_setting_id).where(
        MemoryScopeSettingModel.world_id == world_id,
        MemoryScopeSettingModel.subject_world_character_id == actor_id,
        MemorySituationApplyRun.state != "completed"))


def application_pending(db, setting_id, *, lock=False):
    if lock:
        db.execute(update(MemoryScopeSettingModel).where(
            MemoryScopeSettingModel.id == setting_id,
        ).values(id=MemoryScopeSettingModel.id, updated_at=MemoryScopeSettingModel.updated_at).execution_options(memory_scope_lock_only=True))
    return db.scalar(select(MemorySituationApplyRun.id).where(
        MemorySituationApplyRun.scope_setting_id == setting_id,
        MemorySituationApplyRun.state != "completed",
    ).limit(1)) is not None


def require_application_complete(db, setting_id):
    # The final caller owns its writer; read-only preparation must stay read-only.
    if application_pending(db, setting_id):
        raise ValueError("relationship_memory_application_pending")
