"""Durable review failure budgets; no provider, filesystem or process I/O."""
from datetime import UTC, datetime, timedelta
from random import uniform
from sqlalchemy import select
from app.core.database_transactions import database_write
from app.domains.relationships.models.personalization import RelationshipReviewWork as Work
from app.domains.relationships.service.review_payloads import root_work


def stopped(work):
    return (work.maintenance or {}).get("hold") in {"manual", "cancelled", "closed"}


def fail(db, work, code, *, now, hold="manual"):
    root = root_work(db, work)
    rows = [root]
    for parent in rows:
        rows.extend(db.scalars(select(Work).where(Work.parent_id == parent.id)))
    for row in rows:
        if row.status in {"ready", "applied", "stale"} and row.id != root.id:
            continue
        control = dict(row.maintenance or {})
        control.update(hold=hold, failed_at=now.isoformat(), failure_code=code)
        row.maintenance = control
        row.status, row.error_code = "failed", code
        row.lease_token = row.lease_until = None


def storage_deferred(sessions, work_id, *, now=None):
    instant = now or datetime.now(UTC)
    with sessions() as db:
        def write():
            work = db.get(Work, work_id, populate_existing=True)
            if work is None or stopped(work):
                return "needs_attention"
            if work.status in {"ready", "applied", "stale"}:
                return work.status
            control = dict(work.maintenance or {})
            first = datetime.fromisoformat(control.get("storage_first", instant.isoformat()))
            rounds = control.get("storage_rounds", 0) + 1
            control.update(storage_first=first.isoformat(), storage_rounds=rounds)
            control["received_lease"] = work.lease_token or control.get("received_lease")
            work.maintenance = control
            if rounds >= 3 or (instant-first).total_seconds() >= 120:
                fail(db, work, "relationship_storage_retry_exhausted", now=instant)
                return "needs_attention"
            # The original received attempt remains bound to its token. Only
            # its local storage can resume; claim_work must not call AI again.
            work.next_attempt_at = min(first+timedelta(seconds=120), instant+timedelta(seconds=(5, 15)[rounds-1]+uniform(0, 1)))
            work.lease_until = instant
            work.error_code = "relationship_storage_retry_wait"
            return "storage_retry_wait"
        return database_write(db, write, require_clean=True)


def mark_failed(sessions, work_id, code):
    with sessions() as db:
        def write():
            work = db.get(Work, work_id, populate_existing=True)
            if work is not None and work.status != "applied":
                fail(db, work, code, now=datetime.now(UTC))
        database_write(db, write, require_clean=True)
