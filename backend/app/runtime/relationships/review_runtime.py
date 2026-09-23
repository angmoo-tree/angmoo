"""Lower-priority daily relationship work, called only after memory queue idle."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, or_, case, update

from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.models.batch import MemoryBatchSetting, MemoryBatchProfile
from app.domains.relationships.models.personalization import RelationshipReviewWork, RelationshipPolicy
from app.domains.relationships.service.daily_review import plan_review, run_review_step, apply_review
from app.runtime.relationships.review_memories import collect_new_review_memories, ReviewMemoryReferences
from app.runtime.relationships.review_refresh import refresh_review_inputs
from app.runtime.relationships.review_identity import review_identity_context


class RelationshipReviewRuntime:
    def __init__(self, session_factory, provider_factory):
        self.session_factory = session_factory
        self.provider_factory = provider_factory
        self._next_discovery = None

    def prepare(self, now):
        with self.session_factory() as db:
            settings = db.execute(select(MemoryScopeSettingModel, MemoryBatchSetting, MemoryBatchProfile).join(
                MemoryBatchSetting, MemoryBatchSetting.scope_setting_id == MemoryScopeSettingModel.id).join(
                MemoryBatchProfile, MemoryBatchProfile.owner_id == MemoryScopeSettingModel.owner_id).where(
                MemoryScopeSettingModel.enabled.is_(True), MemoryBatchSetting.ai_enabled.is_(True),
                MemoryBatchSetting.consent_version.is_not(None), MemoryBatchSetting.schedule_enabled.is_(True))).all()
            for setting, batch, profile in settings:
                local = now.astimezone(ZoneInfo(batch.timezone))
                if local.strftime("%H:%M") < batch.local_time:
                    continue
                period = local.date().isoformat()
                db.execute(update(RelationshipPolicy).where(RelationshipPolicy.world_id == setting.world_id).values(version=RelationshipPolicy.version))
                for target, memories in collect_new_review_memories(db, setting=setting, now=now).items():
                    existing = db.scalar(select(RelationshipReviewWork.id).where(
                        RelationshipReviewWork.world_id == setting.world_id,
                        RelationshipReviewWork.actor_world_character_id == setting.subject_world_character_id,
                        RelationshipReviewWork.target_world_character_id == target,
                        RelationshipReviewWork.period_key == period, RelationshipReviewWork.part_key == "root"))
                    if existing:
                        continue  # Late memories remain unclaimed for the next daily period.
                    try:
                        identity = review_identity_context(db, owner_id=setting.owner_id, world_id=setting.world_id,
                            actor_id=setting.subject_world_character_id, target_id=target)
                    except ValueError:
                        continue
                    plan_review(db, world_id=setting.world_id, actor_id=setting.subject_world_character_id,
                        target_id=target, period_key=period, memories=memories,
                        base={"identity": identity,
                              "owner_id": setting.owner_id, "setting_id": setting.id, "profile_version": profile.version,
                              "model_id": profile.model_id, "thinking_level": profile.thinking_level})
            db.commit()

    async def tick(self):
        from app.runtime.memory.foreground_priority import chat_is_active
        now = datetime.now(UTC)
        with self.session_factory() as db:
            if chat_is_active(db, now=now):
                return "relationship_foreground_deferred"
        from app.runtime.relationships.manual_review_worker import advance_manual_requests
        with self.session_factory() as db:
            advance_manual_requests(db, now)
            db.commit()
        # Code-only recovery never re-calls AI and waits for active writers.
        from app.runtime.relationships.experience_metrics import recover_pending_metrics
        recover_pending_metrics(self.session_factory, now=now)
        if self._next_discovery is None or now >= self._next_discovery:
            self.prepare(now)
            self._next_discovery = now + timedelta(minutes=1)
        with self.session_factory() as db:
            ready = db.scalar(select(RelationshipReviewWork).where(RelationshipReviewWork.parent_id.is_(None),
                RelationshipReviewWork.status == "ready").order_by(RelationshipReviewWork.created_at, RelationshipReviewWork.id).limit(1))
            if ready is not None:
                try:
                    refresh_review_inputs(db, ready)
                    result = apply_review(db, work_id=ready.id, references=ReviewMemoryReferences(db), now=now)
                except ValueError as exc:
                    ready.status = "failed"
                    ready.error_code = str(exc) if str(exc).startswith("relationship_") else "relationship_review_validation_failed"
                    ready.next_attempt_at = now + timedelta(minutes=5)
                    result = "validation_deferred"
                db.commit()
                return "relationship_" + result
            work = db.scalar(select(RelationshipReviewWork).where(
                or_(RelationshipReviewWork.status.in_(("pending", "failed")),
                    (RelationshipReviewWork.status == "running") & (RelationshipReviewWork.lease_until <= now)),
                or_(RelationshipReviewWork.next_attempt_at.is_(None), RelationshipReviewWork.next_attempt_at <= now)).order_by(
                    case((RelationshipReviewWork.phase == "partial", 0), (RelationshipReviewWork.phase == "reduce", 1),
                         (RelationshipReviewWork.phase == "direct", 2), else_=3),
                    RelationshipReviewWork.created_at, RelationshipReviewWork.id).limit(1))
            if work is not None:
                root = work
                while root.parent_id:
                    root = db.get(RelationshipReviewWork, root.parent_id)
                try:
                    refresh_review_inputs(db, root)
                except ValueError:
                    work.status, work.error_code = "failed", "relationship_review_identity_unavailable"
                    work.next_attempt_at = now + timedelta(minutes=5)
                    db.commit()
                    return "relationship_identity_deferred"
                if root.status == "stale":
                    work = None
                db.commit()
            work_id = None if work is None else work.id
        if work_id is None:
            return "relationship_queue_empty"
        return await run_review_step(self.session_factory, work_id=work_id,
            references_factory=ReviewMemoryReferences, provider_factory=self.provider_factory)
