"""Conditional canonical claims; checkpoint I/O belongs to the runtime owner."""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.domains.world_characters.activity_models import ActivityGraphRun
from app.domains.world_characters.contracts.checkpoint_retention import (
    RETENTION_KEY, TERMINAL_STATUSES, completion, retention, utc,
)


def eligible(row: ActivityGraphRun, *, now: datetime) -> bool:
    policy = retention(row.result)
    if policy is None or not policy.graph_complete or policy.state == "pruned":
        return False
    if row.status not in TERMINAL_STATUSES or not isinstance(row.finished_at, datetime):
        return False
    if utc(row.finished_at) + timedelta(hours=24) > utc(now):
        return False
    try:
        completion(row)
    except ValueError:
        return False
    return True


def candidates(db: Session, *, now: datetime, cursor: tuple[datetime, str] | None,
               limit: int) -> list[tuple[datetime, str]]:
    query = select(ActivityGraphRun.finished_at, ActivityGraphRun.activity_id).where(
        ActivityGraphRun.engine == "personalized_graph_v2",
        ActivityGraphRun.status.in_(TERMINAL_STATUSES),
        ActivityGraphRun.finished_at <= utc(now) - timedelta(hours=24),
        ActivityGraphRun.result[RETENTION_KEY]["policy"].as_string() == "sns-completed-checkpoint-24h-v1",
        ActivityGraphRun.result[RETENTION_KEY]["state"].as_string() != "pruned",
    )
    if cursor is not None:
        finished, identifier = cursor
        query = query.where(or_(ActivityGraphRun.finished_at > finished,
            and_(ActivityGraphRun.finished_at == finished, ActivityGraphRun.activity_id > identifier)))
    return list(db.execute(query.order_by(ActivityGraphRun.finished_at, ActivityGraphRun.activity_id).limit(limit)))


def _replace_policy(db: Session, row: ActivityGraphRun, payload: dict) -> bool:
    # CAS protects reservations/results written by another canonical owner.
    changed = db.execute(update(ActivityGraphRun).where(
        ActivityGraphRun.activity_id == row.activity_id,
        ActivityGraphRun.status == row.status,
        ActivityGraphRun.finished_at == row.finished_at,
        ActivityGraphRun.result == row.result,
    ).values(result={**row.result, RETENTION_KEY: payload}),
        execution_options={"synchronize_session": False}).rowcount
    return changed == 1


def claim(db: Session, row: ActivityGraphRun, *, now: datetime) -> str | None:
    if not eligible(row, now=now):
        return None
    policy = retention(row.result)
    token = uuid4().hex
    updated = policy.model_copy(update={"state": "claimed", "claim_token": token})
    return token if _replace_policy(db, row, updated.model_dump()) else None


def mark_pruned(db: Session, row: ActivityGraphRun, *, token: str) -> bool:
    policy = retention(row.result)
    if policy is None or policy.state != "claimed" or policy.claim_token != token:
        return False
    updated = policy.model_copy(update={"state": "pruned", "claim_token": None})
    return _replace_policy(db, row, updated.model_dump())


def confirm_graph(db: Session, row: ActivityGraphRun) -> bool:
    policy = retention(row.result)
    if policy is None or policy.graph_complete or row.status not in TERMINAL_STATUSES:
        return False
    completion(row)
    return _replace_policy(db, row, policy.model_copy(update={"graph_complete": True}).model_dump())
