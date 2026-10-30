"""One selected character's frozen review request, with short DB operations."""

from datetime import UTC, datetime, timedelta
from sqlalchemy import select, or_, case

from app.domains.relationships.models.personalization import RelationshipReviewWork
from app.domains.relationships.service.daily_review import run_review_step
from app.runtime.relationships.review_memories import ReviewMemoryReferences
from app.runtime.relationships.situation_ordering import scope_application_pending


class RelationshipReviewRuntime:
    def __init__(self, session_factory, provider_factory, *, canonical_work=None, media_root=None):
        self.session_factory = session_factory
        self.provider_factory = provider_factory
        self._next_discovery = None
        from app.runtime.received_results import result_journal
        self.journal = result_journal("relationship-review", media_root=media_root)
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
        now = datetime.now(UTC)
        deferred = await self._database_work(self._advance, now)
        if deferred:
            return deferred
        if self._next_discovery is None or now >= self._next_discovery:
            await self._database_work(self.prepare, now)
            self._next_discovery = now + timedelta(minutes=1)
        work_id, outcome = await self._database_work(self._next_work, now)
        if outcome != "prepared":
            return "relationship_" + outcome
        return await self._review(work_id)

    async def candidate(self):
        now = datetime.now(UTC)
        deferred = await self._database_work(self._advance, now)
        if deferred:
            return None
        if self._next_discovery is None or now >= self._next_discovery:
            await self._database_work(self.prepare, now)
            self._next_discovery = now + timedelta(minutes=1)
            await self._database_work(self._advance, now)
        return await self._database_work(self._candidate, now)

    def _candidate(self, now):
        from app.domains.relationships.models.manual_review import RelationshipReviewRequest as Request
        from app.domains.memory.models.items import MemoryScopeSettingModel
        from app.domains.memory.contracts.items import as_utc
        from app.domains.relationships.service.review_history import active_work_ids
        with self.session_factory() as db:
            query = select(Request, MemoryScopeSettingModel).join(MemoryScopeSettingModel,
                MemoryScopeSettingModel.id == Request.scope_setting_id).where(
                Request.canonical_request_id.is_(None), Request.state == "running",
                ~scope_application_pending(MemoryScopeSettingModel.world_id, MemoryScopeSettingModel.subject_world_character_id)
            ).order_by(Request.accepted_at, Request.memory_request_id)
            for request, setting in db.execute(query):
                if db.scalar(self._runnable(now, active_work_ids(request)).with_only_columns(RelationshipReviewWork.id).limit(1)):
                    return dict(kind="relationship", id=request.memory_request_id, accepted_at=as_utc(request.accepted_at),
                        world_id=setting.world_id, actor_id=setting.subject_world_character_id)
        return None

    async def run_round(self, request_id):
        """Normal steps stay contiguous; a future retry releases the slot."""
        import asyncio
        while True:
            now = datetime.now(UTC)
            await self._database_work(self._advance_request, now, request_id)
            work_id, outcome = await self._database_work(self._next_work, now, request_id)
            if outcome == "prepared":
                outcome = await self._review(work_id)
            if outcome not in {"ready", "applied", "stale", "rebased", "needs_attention", "validation_deferred", "split_pending"}:
                return "relationship_" + outcome
            await asyncio.sleep(0)

    def _advance_request(self, now, request_id):
        from app.runtime.relationships.manual_review_worker import advance_manual_requests
        from app.core.database_transactions import database_write
        with self.session_factory() as db:
            database_write(db, lambda: advance_manual_requests(db, now, request_id=request_id), require_clean=True)

    def _runnable(self, now, root_ids):
        # Descendants may form several levels after a provider-requested split.
        # Scope every step to this request's active roots, including ready ones.
        from sqlalchemy.orm import aliased
        from app.domains.relationships.models.personalization import RelationshipReviewWork as Work
        root = aliased(Work)
        tree = select(root.id).where(root.id.in_(root_ids), root.status.in_(("pending", "running", "ready")),
            root.maintenance["hold"].as_string().is_(None)).cte("selected_review_tree", recursive=True)
        child = aliased(Work)
        tree = tree.union_all(select(child.id).join(tree, child.parent_id == tree.c.id))
        return select(Work).where(Work.id.in_(select(tree.c.id)),
            Work.maintenance["hold"].as_string().is_(None),
            or_(Work.error_code.is_(None), Work.error_code != "relationship_review_outcome_unknown"),
            or_(Work.status == "ready", Work.status == "pending",
                (Work.status == "running") & (Work.lease_until <= now)),
            or_(Work.next_attempt_at.is_(None), Work.next_attempt_at <= now))

    async def _database_work(self, function, *args):
        # Share the existing bounded memory worker. Sessions and ORM rows stay
        # inside each synchronous operation; provider I/O stays on the event loop.
        if self.canonical_work is not None:
            return await self.canonical_work(function, *args)
        return function(*args)

    async def _review(self, work_id):
        return await run_review_step(self.session_factory, work_id=work_id,
            references_factory=ReviewMemoryReferences, provider_factory=self.provider_factory,
            journal=self.journal, received=self._received, database_work=self._database_work)

    def _advance(self, now):
        from app.runtime.memory.foreground_priority import chat_is_active
        with self.session_factory() as db:
            if chat_is_active(db, now=now):
                return "relationship_foreground_deferred"
        from app.runtime.relationships.manual_review_worker import advance_manual_requests
        from app.core.database_transactions import database_write
        with self.session_factory() as db:
            database_write(db, lambda: advance_manual_requests(db, now, limit=16), require_clean=True)
        # Code-only recovery never re-calls AI and waits for active writers.
        from app.runtime.relationships.experience_metrics import recover_pending_metrics
        recover_pending_metrics(self.session_factory, now=now)
        return None

    def _next_work(self, now, request_id=None):
        with self.session_factory() as db:
            if request_id is not None:
                from app.domains.relationships.models.manual_review import RelationshipReviewRequest as Request
                from app.domains.relationships.service.review_history import active_work_ids
                request = db.get(Request, request_id)
                if request is None or request.state != "running":
                    return None, "queue_empty"
                runnable = self._runnable(now, active_work_ids(request))
                ready = db.scalar(runnable.where(RelationshipReviewWork.parent_id.is_(None),
                    RelationshipReviewWork.status == "ready").order_by(RelationshipReviewWork.created_at).limit(1))
                if ready is not None:
                    work_id = ready.id
                    db.rollback()
                    from app.runtime.relationships.review_transitions import transition
                    return work_id, transition(self.session_factory, work_id, now, apply=True)
                work = db.scalar(runnable.where(RelationshipReviewWork.status != "ready").order_by(
                    case((RelationshipReviewWork.phase == "partial", 0), (RelationshipReviewWork.phase == "reduce", 1),
                         (RelationshipReviewWork.phase == "direct", 2), else_=3),
                    RelationshipReviewWork.created_at, RelationshipReviewWork.id).limit(1))
                if work is None:
                    return None, "queue_empty"
                work_id, world_id = work.id, work.world_id
                db.rollback()
                if self.journal.read(world_id, work_id) is not None:
                    return work_id, "prepared"
                from app.runtime.relationships.review_transitions import transition
                return work_id, transition(self.session_factory, work_id, now)
            ready = db.scalar(select(RelationshipReviewWork).where(RelationshipReviewWork.parent_id.is_(None),
                ~scope_application_pending(RelationshipReviewWork.world_id, RelationshipReviewWork.actor_world_character_id),
                RelationshipReviewWork.status == "ready").order_by(RelationshipReviewWork.created_at, RelationshipReviewWork.id).limit(1))
            if ready is not None:
                work_id = ready.id
                db.rollback()
                from app.runtime.relationships.review_transitions import transition
                return work_id, transition(self.session_factory, work_id, now, apply=True)
            work = db.scalar(select(RelationshipReviewWork).where(
                ~scope_application_pending(RelationshipReviewWork.world_id, RelationshipReviewWork.actor_world_character_id),
                or_(RelationshipReviewWork.error_code.is_(None), RelationshipReviewWork.error_code != "relationship_review_outcome_unknown"),
                or_(RelationshipReviewWork.status == "pending",
                    (RelationshipReviewWork.status == "running") & (RelationshipReviewWork.lease_until <= now)),
                or_(RelationshipReviewWork.next_attempt_at.is_(None), RelationshipReviewWork.next_attempt_at <= now)).order_by(
                    case((RelationshipReviewWork.phase == "partial", 0), (RelationshipReviewWork.phase == "reduce", 1),
                         (RelationshipReviewWork.phase == "direct", 2), else_=3),
                    RelationshipReviewWork.created_at, RelationshipReviewWork.id).limit(1))
            work_id = None if work is None else work.id
            world_id = None if work is None else work.world_id
        if work_id is None:
            return None, "queue_empty"
        if self.journal.read(world_id, work_id) is not None:
            return work_id, "prepared"
        from app.runtime.relationships.review_transitions import transition
        outcome = transition(self.session_factory, work_id, now)
        return work_id, outcome
