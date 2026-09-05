"""Outbox eligibility rows and per-World projection readiness aggregates."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session
from app.domains.relationships import models
from app.domains.relationships.contracts.outbox import GraphOutboxCounts


def claimable_rows(db: Session, *, now: datetime, batch_size: int) -> list[models.GraphProjectionOutbox]:
    active_rebuild = exists(
            select(models.GraphProjectionReplayRun.id).where(
                models.GraphProjectionReplayRun.world_id
                == models.GraphProjectionOutbox.world_id,
                models.GraphProjectionReplayRun.mode == "world_rebuild",
                models.GraphProjectionReplayRun.status.in_(("pending", "running")),
            )
        )
    rows = list(
            db.scalars(
                select(models.GraphProjectionOutbox)
                .where(
                    or_(
                        models.GraphProjectionOutbox.status == "pending",
                        (
                            (models.GraphProjectionOutbox.status == "processing")
                            & (
                                models.GraphProjectionOutbox.lease_expires_at
                                < now
                            )
                        ),
                    ),
                    or_(
                        models.GraphProjectionOutbox.next_attempt_at.is_(None),
                        models.GraphProjectionOutbox.next_attempt_at <= now,
                    ),
                    ~active_rebuild,
                )
                .order_by(
                    models.GraphProjectionOutbox.created_at.asc(),
                    models.GraphProjectionOutbox.id.asc(),
                )
                .with_for_update(skip_locked=True)
                .limit(max(1, min(batch_size, 100)))
            )
        )
    return rows


def get_outbox(db: Session, outbox_id: str) -> models.GraphProjectionOutbox | None:
    return db.get(models.GraphProjectionOutbox, outbox_id)


def world_counts(db: Session, *, world_id: str) -> GraphOutboxCounts:
    counts = dict(
        db.execute(
            select(
                models.GraphProjectionOutbox.status,
                func.count(models.GraphProjectionOutbox.id),
            )
            .where(models.GraphProjectionOutbox.world_id == world_id)
            .group_by(models.GraphProjectionOutbox.status)
        ).all()
    )
    oldest_pending_at = db.scalar(
        select(func.min(models.GraphProjectionOutbox.created_at)).where(
            models.GraphProjectionOutbox.world_id == world_id,
            models.GraphProjectionOutbox.status.in_(("pending", "processing")),
        )
    )
    last_succeeded_at = db.scalar(
        select(func.max(models.GraphProjectionOutbox.completed_at)).where(
            models.GraphProjectionOutbox.world_id == world_id,
            models.GraphProjectionOutbox.status == "succeeded",
        )
    )
    active_replay = db.scalar(
        select(models.GraphProjectionReplayRun.id).where(
            models.GraphProjectionReplayRun.world_id == world_id,
            models.GraphProjectionReplayRun.mode == "world_rebuild",
            models.GraphProjectionReplayRun.status.in_(("pending", "running")),
        )
    ) is not None
    latest_rebuild_status = db.scalar(
        select(models.GraphProjectionReplayRun.status)
        .where(
            models.GraphProjectionReplayRun.world_id == world_id,
            models.GraphProjectionReplayRun.mode == "world_rebuild",
        )
        .order_by(
            models.GraphProjectionReplayRun.created_at.desc(),
            models.GraphProjectionReplayRun.id.desc(),
        )
        .limit(1)
    )
    return GraphOutboxCounts(
        pending=int(counts.get("pending", 0)),
        processing=int(counts.get("processing", 0)),
        dead=int(counts.get("dead", 0)),
        oldest_pending_at=oldest_pending_at,
        last_succeeded_at=last_succeeded_at,
        active_replay=active_replay,
        failed_rebuild=latest_rebuild_status == "failed",
    )
