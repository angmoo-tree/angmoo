"""Lower-priority daily relationship work, called only after memory queue idle."""

from datetime import UTC, datetime, timedelta
from sqlalchemy import select, or_, case

from app.domains.relationships.models.personalization import RelationshipReviewWork
from app.domains.relationships.service.daily_review import run_review_step
from app.runtime.relationships.review_memories import ReviewMemoryReferences
from app.runtime.relationships.situation_ordering import scope_application_pending


class RelationshipReviewRuntime:
    def __init__(self, session_factory, provider_factory, *, canonical_work=None):
        self.session_factory = session_factory
        self.provider_factory = provider_factory
        self._next_discovery = None
        from app.runtime.received_results import result_journal
        self.journal = result_journal("relationship-review")
        self._received = {}
        self.canonical_work = canonical_work

    def prepare(self, now):
        from app.runtime.relationships.review_preparation import prepare_due_reviews
        prepare_due_reviews(self.session_factory, now)

    async def tick(self):
        from app.core.sqlite_concurrency import is_sqlite_contention
        try:
            return await self._tick()
        except Exception as exc:
            if is_sqlite_contention(exc):
                return "relationship_storage_busy"
            raise

    async def _tick(self):
        from app.runtime.memory.foreground_priority import chat_is_active
        now = datetime.now(UTC)
        if self._received:
            return await run_review_step(self.session_factory, work_id=next(iter(self._received)),
                references_factory=ReviewMemoryReferences, provider_factory=self.provider_factory,
                journal=self.journal, received=self._received)
        with self.session_factory() as db:
            if chat_is_active(db, now=now):
                return "relationship_foreground_deferred"
        from app.runtime.relationships.manual_review_worker import advance_manual_requests
        from app.core.sqlite_concurrency import run_sqlite_session_immediate
        with self.session_factory() as db:
            run_sqlite_session_immediate(db, lambda: advance_manual_requests(db, now, limit=1), require_clean=True)
        # Code-only recovery never re-calls AI and waits for active writers.
        from app.runtime.relationships.experience_metrics import recover_pending_metrics
        recover_pending_metrics(self.session_factory, now=now)
        if self._next_discovery is None or now >= self._next_discovery:
            if self.canonical_work is None:
                self.prepare(now)
            else:
                await self.canonical_work(self.prepare, now)
            self._next_discovery = now + timedelta(minutes=1)
        with self.session_factory() as db:
            ready = db.scalar(select(RelationshipReviewWork).where(RelationshipReviewWork.parent_id.is_(None),
                ~scope_application_pending(RelationshipReviewWork.world_id, RelationshipReviewWork.actor_world_character_id),
                RelationshipReviewWork.status == "ready").order_by(RelationshipReviewWork.created_at, RelationshipReviewWork.id).limit(1))
            if ready is not None:
                work_id = ready.id
                db.rollback()
                from app.runtime.relationships.review_transitions import transition
                return "relationship_" + transition(self.session_factory, work_id, now, apply=True)
            work = db.scalar(select(RelationshipReviewWork).where(
                ~scope_application_pending(RelationshipReviewWork.world_id, RelationshipReviewWork.actor_world_character_id),
                or_(RelationshipReviewWork.error_code.is_(None), RelationshipReviewWork.error_code != "relationship_review_outcome_unknown"),
                or_(RelationshipReviewWork.status.in_(("pending", "failed")),
                    (RelationshipReviewWork.status == "running") & (RelationshipReviewWork.lease_until <= now)),
                or_(RelationshipReviewWork.next_attempt_at.is_(None), RelationshipReviewWork.next_attempt_at <= now)).order_by(
                    case((RelationshipReviewWork.phase == "partial", 0), (RelationshipReviewWork.phase == "reduce", 1),
                         (RelationshipReviewWork.phase == "direct", 2), else_=3),
                    RelationshipReviewWork.created_at, RelationshipReviewWork.id).limit(1))
            work_id = None if work is None else work.id
        if work_id is None:
            return "relationship_queue_empty"
        from app.runtime.relationships.review_transitions import transition
        outcome = transition(self.session_factory, work_id, now)
        if outcome != "prepared":
            return "relationship_" + outcome
        return await run_review_step(self.session_factory, work_id=work_id,
            references_factory=ReviewMemoryReferences, provider_factory=self.provider_factory,
            journal=self.journal, received=self._received)
