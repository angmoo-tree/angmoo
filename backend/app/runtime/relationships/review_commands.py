"""Scoped recovery commands on the caller's transaction; no provider calls."""
from datetime import UTC, datetime, timedelta
from sqlalchemy import select
from app.domains.memory.exceptions import MemoryConflictError
from app.domains.relationships.models.personalization import RelationshipReviewWork as Work


def revision(request):
    return (request.maintenance or {}).get("revision", 0)


def allowed(request, works):
    if request.state in {"closed", "completed", "no_relationship_work", "not_applicable"}:
        return []
    if request.state == "cancelled":
        return ["resume_remaining"]
    failures = [w for w in works if w.status == "failed" and (w.maintenance or {}).get("hold") != "closed"]
    if failures or request.state in {"paused", "partial_failed", "failed"}:
        actions = []
        if any(w.error_code == "relationship_storage_retry_exhausted" for w in failures):
            actions.append("resume_storage")
        if not failures or any(w.error_code != "relationship_storage_retry_exhausted" for w in failures):
            actions.append("regenerate_failed")
        actions.append("close_without_retry")
        if any(w.status in {"pending", "running", "ready"} for w in works):
            actions.append("cancel_remaining")
        return actions
    return ["cancel_remaining"]


def command(db, request, *, mode, key, expected_revision):
    db.refresh(request, with_for_update=True)
    control = dict(request.maintenance or {})
    previous = control.get("last_command", {})
    if previous.get("key") == key:
        if previous.get("mode") != mode:
            raise MemoryConflictError("memory_request_replay_conflict")
        return
    if revision(request) != expected_revision:
        raise MemoryConflictError("memory_workflow_revision_conflict")
    roots = list(db.scalars(select(Work).where(Work.id.in_(request.work_ids))))
    if mode not in allowed(request, roots):
        raise MemoryConflictError("memory_workflow_action_unavailable")
    now = datetime.now(UTC)
    pending = [w for w in roots if w.status not in {"applied", "stale"} and (w.maintenance or {}).get("hold") != "closed"]
    for root in pending:
        if mode in {"regenerate_failed", "resume_storage", "close_without_retry"} and root.status != "failed":
            continue
        storage_failure = root.error_code == "relationship_storage_retry_exhausted"
        if mode == "resume_storage" and not storage_failure or mode == "regenerate_failed" and storage_failure:
            continue
        rows = [root]
        for parent in rows:
            rows.extend(db.scalars(select(Work).where(Work.parent_id == parent.id)))
        for work in rows:
            if work.status == "applied" or (work.maintenance or {}).get("hold") == "closed" or (mode in {"regenerate_failed", "resume_storage"} and work.status == "ready"):
                continue
            current = dict(work.maintenance or {})
            history = list(current.get("history", []))
            history.append({"at": now.isoformat(), "status": work.status, "code": work.error_code,
                            "attempts": work.attempts, "command": mode})
            current["history"] = history
            if mode in {"close_without_retry", "cancel_remaining"}:
                if mode == "cancel_remaining":
                    current["cancelled_status"] = work.status
                current.update(hold="closed" if mode == "close_without_retry" else "cancelled", closed_at=now.isoformat())
                work.status = "failed"
                work.lease_token = work.lease_until = work.next_attempt_at = None
            else:
                current["hold"] = None
                if mode == "resume_remaining" and current.get("cancelled_status") == "ready" and work.result is not None:
                    work.status = "ready"
                    work.lease_token = work.lease_until = None
                elif mode == "resume_storage" or mode == "resume_remaining" and current.get("received_lease"):
                    work.status = "running" if current.get("received_lease") else "pending"
                    work.lease_token = current.get("received_lease")
                    work.lease_until = now - timedelta(seconds=1) if work.lease_token else None
                    current["storage_rounds"] = 0
                    current["storage_revision"] = current.get("storage_revision", 0)+1
                    current.pop("storage_first", None)
                else:
                    current["provider_base"] = work.attempts
                    work.status, work.result = "pending", None
                    work.lease_token = work.lease_until = None
                work.next_attempt_at = work.next_attempt_at if mode == "regenerate_failed" else None
                work.error_code = None
            work.maintenance = current
    control.update(revision=revision(request)+1, last_command={"key": key, "mode": mode, "at": now.isoformat()})
    if mode == "close_without_retry":
        from app.domains.relationships.service.review_history import close_receipts
        close_receipts(db, [w.id for w in roots if (w.maintenance or {}).get("hold") == "closed"])
    request.maintenance = control
    if mode in {"close_without_retry", "cancel_remaining"}:
        other_live = mode == "close_without_retry" and any(w.status in {"pending", "running", "ready"} for w in roots)
        request.state = "running" if other_live else "closed" if mode == "close_without_retry" else "cancelled"
        request.completed_at = None if other_live else now
    else:
        request.state, request.last_code, request.completed_at = "waiting_memory", None, None
