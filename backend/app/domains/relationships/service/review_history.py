"""Keep historical failures while separating later request eligibility."""
from datetime import UTC, datetime
from sqlalchemy import select, update, or_
from app.domains.relationships.models.personalization import RelationshipReviewWork as Work, RelationshipReviewMemoryReceipt as Receipt
from app.domains.relationships.models.manual_review import RelationshipReviewRequest as Request


def active_snapshot(request):
    ignored = set((request.maintenance or {}).get("prior_failure_memory_ids", []))
    return [ref for ref in request.snapshot or [] if ref["memory_id"] not in ignored]


def active_work_ids(request):
    ignored = set((request.maintenance or {}).get("prior_failure_work_ids", []))
    return [identifier for identifier in request.work_ids if identifier not in ignored]


def pending_receipts(db, *, world_id, actor_id):
    # A failed result belongs to its original explicit recovery, never a new run.
    return db.scalars(select(Receipt).outerjoin(Work, Work.id == Receipt.work_id).where(
        Receipt.world_id == world_id, Receipt.actor_world_character_id == actor_id,
        Receipt.status == "pending", or_(Work.id.is_(None),
            (Work.status.in_(("pending", "running", "ready"))) &
            (Work.maintenance["hold"].as_string().is_(None))))).all()


def close_receipts(db, work_ids):
    if work_ids:
        db.execute(update(Receipt).where(Receipt.work_id.in_(work_ids), Receipt.status == "pending")
            .values(status="excluded", reason="owner_closed_failure"))


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def reconcile_closed_history(db):
    """One upgrade, no AI. Raw snapshots, results and failure evidence survive."""
    cursor = ""
    changed = 0
    while True:
        page = list(db.scalars(select(Request).where(Request.memory_request_id > cursor,
            Request.canonical_request_id.is_(None), Request.snapshot.is_not(None))
            .order_by(Request.memory_request_id).limit(100)))
        if not page:
            return changed
        for request in page:
            roots = list(db.scalars(select(Work).where(Work.id.in_(request.work_ids))))
            prior = []
            for work in roots:
                control = work.maintenance or {}
                if work.status != "failed" or control.get("hold") != "closed":
                    continue
                close_receipts(db, [work.id])
                try:
                    closed = _utc(datetime.fromisoformat(control["closed_at"]))
                except (KeyError, ValueError, TypeError):
                    continue  # Ambiguous historical ownership is never guessed.
                if closed <= _utc(request.accepted_at):
                    prior.append(work.id)
            if not prior:
                continue
            receipt_ids = set(db.scalars(select(Receipt.memory_id).where(Receipt.work_id.in_(prior))))
            ignored = sorted(ref["memory_id"] for ref in request.snapshot if ref["memory_id"] in receipt_ids)
            control = dict(request.maintenance or {})
            if control.get("prior_failure_memory_ids") == ignored and control.get("prior_failure_work_ids") == sorted(prior):
                continue
            control.update(prior_failure_memory_ids=ignored, prior_failure_work_ids=sorted(prior),
                prior_failure_reconciliation="postgresql-v5")
            request.maintenance = control
            remaining = [work for work in roots if work.id not in prior]
            # Only repair an automatically derived closed/no-work state. An
            # owner's command on this request remains authoritative.
            if request.state == "closed" and not control.get("last_command"):
                if any(work.status in {"pending", "running", "ready"} for work in remaining):
                    request.state, request.completed_at = "running", None
                elif any(work.status == "failed" for work in remaining):
                    request.state = "partial_failed"
                else:
                    request.state = "completed" if any(work.status == "applied" for work in remaining) else "no_relationship_work"
            changed += 1
        db.flush()
        cursor = page[-1].memory_request_id
