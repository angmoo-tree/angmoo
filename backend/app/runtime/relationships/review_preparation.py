"""Read the complete cutoff first; commit one counterpart with fresh guards."""
from datetime import UTC
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.core.ids import uuid7_string
from app.core.database_transactions import database_write
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.models.items import MemoryScopeSettingModel, MemoryItem
from app.domains.memory.models.batch import MemoryBatchSetting
from app.domains.memory.models.activity_configuration import MemorySubjectProfile
from app.domains.relationships.models.personalization import RelationshipReviewWork, RelationshipReviewMemoryReceipt, RelationshipPolicy
from app.domains.relationships.service.daily_review import plan_review
from app.domains.identity.service.environment import snapshot
from app.runtime.relationships.review_credentials import snapshot as credential_snapshot
from app.runtime.relationships.review_identity import review_identity_context
from app.runtime.relationships.review_memories import collect_new_review_memories, resolve_memory_batch, ReviewMemoryReferences
from app.runtime.relationships.situation_ordering import application_pending


def _context(db, setting_id, now):
    setting = db.get(MemoryScopeSettingModel, setting_id, populate_existing=True)
    batch = db.get(MemoryBatchSetting, setting_id, populate_existing=True)
    profile = db.get(MemorySubjectProfile, setting_id, populate_existing=True)
    if (not setting or not setting.enabled or not batch or not batch.ai_enabled or not batch.consent_version
        or not batch.schedule_enabled or profile is None or application_pending(db, setting_id)):
        return None
    policy = db.get(RelationshipPolicy, setting.world_id, populate_existing=True)
    if policy is None:
        return None
    scope = MemoryScope(setting.owner_id, setting.world_id, setting.subject_world_character_id)
    credential = credential_snapshot(db, scope, profile)
    environment = snapshot(db, setting.owner_id)
    local = now.astimezone(ZoneInfo(environment.timezone))
    if local.strftime("%H:%M") < batch.local_time:
        return None
    base = {**credential, "environment": environment.to_dict(), "owner_id": setting.owner_id,
        "setting_id": setting.id, "profile_version": profile.version, "model_id": profile.model_id,
        "thinking_level": profile.thinking_level}
    guard = (setting.version, batch.version, profile.version, policy.version, base)
    return setting, scope, local.date().isoformat(), base, guard


def prepare_due_reviews(sessions, now):
    """Automatic and manual triggers enter the same durable request queue."""
    from app.domains.memory.repository.consolidation_requests import admit
    from app.runtime.relationships.manual_review import ManualRelationshipFollowup
    with sessions() as db:
        ids = tuple(db.scalars(select(MemoryScopeSettingModel.id).where(MemoryScopeSettingModel.enabled.is_(True))
            .order_by(MemoryScopeSettingModel.id)))
    for setting_id in ids:
        with sessions() as db:
            def write():
                try:
                    context = _context(db, setting_id, now)
                except ValueError:
                    return
                if context is None:
                    return
                setting, scope, period, base, guard = context
                row, disposition = admit(db, setting=setting, kind="scheduled",
                    key="relationship-daily:"+period, now=now, digest=period)
                if disposition != "accepted":
                    return
                row.state, row.completed_at, row.cutoff_sequence = "completed", now, 0
                ManualRelationshipFollowup(db).admit(scope, row)
            database_write(db, write, require_clean=True)
