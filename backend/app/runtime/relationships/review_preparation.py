"""Read the complete cutoff first; commit one counterpart with fresh guards."""
from datetime import UTC
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.core.ids import uuid7_string
from app.core.sqlite_concurrency import run_sqlite_session_immediate
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
    with sessions() as db:
        ids = tuple(db.scalars(select(MemoryScopeSettingModel.id).where(MemoryScopeSettingModel.enabled.is_(True))
            .order_by(MemoryScopeSettingModel.id)))
    for setting_id in ids:
        with sessions() as db:
            try:
                context = _context(db, setting_id, now)
            except ValueError:
                continue
            if context is None:
                continue
            setting, scope, period, base, guard = context
            excluded = []
            grouped = collect_new_review_memories(db, setting=setting, now=now, excluded=excluded)
        # Values above are preparation, never authorization across Sessions.
        for target, memories in grouped.items():
            with sessions() as db:
                def commit_target():
                    current = _context(db, setting_id, now)
                    if current is None or current[4] != guard:
                        return
                    existing = db.scalar(select(RelationshipReviewWork.id).where(RelationshipReviewWork.world_id == scope.world_id,
                        RelationshipReviewWork.actor_world_character_id == scope.subject_world_character_id,
                        RelationshipReviewWork.target_world_character_id == target,
                        RelationshipReviewWork.period_key == period, RelationshipReviewWork.part_key == "root"))
                    if existing:
                        return  # Later input belongs to the next daily period.
                    identity = review_identity_context(db, owner_id=scope.owner_id, world_id=scope.world_id,
                        actor_id=scope.subject_world_character_id, target_id=target)
                    fresh_base = {**base, "identity": identity}
                    prepared = SimpleNamespace(world_id=scope.world_id, actor_world_character_id=scope.subject_world_character_id,
                        target_world_character_id=target, manifest={"base": fresh_base, "memories": memories})
                    ReviewMemoryReferences(db).revalidate(prepared)
                    plan_review(db, world_id=scope.world_id, actor_id=scope.subject_world_character_id,
                        target_id=target, period_key=period, base=fresh_base, memories=memories)
                try:
                    run_sqlite_session_immediate(db, commit_target, require_clean=True)
                except ValueError:
                    continue  # Re-prepare changed input next discovery; no stale root.
        for start in range(0, len(excluded), 100):
            page = excluded[start:start+100]
            with sessions() as db:
                def commit_exclusions():
                    context = _context(db, setting_id, now)
                    if context is None or context[4] != guard:
                        return
                    policy = db.get(RelationshipPolicy, scope.world_id)
                    items = list(db.scalars(select(MemoryItem).where(MemoryItem.id.in_([p[1]["memory_id"] for p in page]),
                        MemoryItem.world_id == scope.world_id, MemoryItem.owner_id == scope.owner_id,
                        MemoryItem.subject_world_character_id == scope.subject_world_character_id)))
                    expected = {p[1]["memory_id"]: (p[1]["digest"], p[2]) for p in page}
                    values = resolve_memory_batch(db, scope=scope, items=items, activation=policy.activated_at, now=now)
                    # Validation is over before receipt writes begin.
                    for target, payload, reason in values:
                        if not reason or expected.get(payload["memory_id"]) != (payload["digest"], reason):
                            continue
                        found = db.scalar(select(RelationshipReviewMemoryReceipt.id).where(
                            RelationshipReviewMemoryReceipt.world_id == scope.world_id,
                            RelationshipReviewMemoryReceipt.actor_world_character_id == scope.subject_world_character_id,
                            RelationshipReviewMemoryReceipt.memory_id == payload["memory_id"]))
                        if found is None:
                            db.add(RelationshipReviewMemoryReceipt(id=uuid7_string(), world_id=scope.world_id,
                                actor_world_character_id=scope.subject_world_character_id, target_world_character_id=target,
                                memory_id=payload["memory_id"], memory_digest=payload["digest"], status="excluded", reason=reason))
                run_sqlite_session_immediate(db, commit_exclusions, require_clean=True)
