"""One fresh, bounded writer for a review refresh or final relationship apply."""
from datetime import timedelta
from app.core.sqlite_concurrency import run_sqlite_session_immediate
from app.domains.relationships.models.personalization import RelationshipReviewWork
from app.domains.relationships.service.daily_review import apply_review
from app.runtime.relationships.review_memories import ReviewMemoryReferences
from app.runtime.relationships.review_refresh import refresh_review_inputs
from app.runtime.relationships.situation_ordering import application_pending


def transition(sessions, work_id, now, *, apply=False):
    with sessions() as db:
        def write():
            work = db.get(RelationshipReviewWork, work_id, populate_existing=True)
            if work is None:
                return "lease_lost"
            root = work
            while root.parent_id:
                root = db.get(RelationshipReviewWork, root.parent_id)
                if root is None:
                    return "lease_lost"
            if application_pending(db, root.manifest["base"]["setting_id"]):
                return "memory_application_deferred"
            try:
                refresh_review_inputs(db, root)
                if root.status == "stale":
                    return "stale"
                return apply_review(db, work_id=work_id, references=ReviewMemoryReferences(db), now=now) if apply else "prepared"
            except ValueError as exc:
                if str(exc) == "relationship_memory_application_pending":
                    return "memory_application_deferred"
                work.status = "failed"
                work.error_code = str(exc) if str(exc).startswith("relationship_") else "relationship_review_validation_failed"
                work.next_attempt_at = now + timedelta(minutes=5)
                return "validation_deferred"
        return run_sqlite_session_immediate(db, write, require_clean=True)
