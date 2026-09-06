"""Canonical replay audit and high-water queries on the supplied Session."""
from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session
from app.domains.relationships import models


def active_world_rebuild_id(db: Session, *, world_id: str):
    return db.scalar(
        select(models.GraphProjectionReplayRun.id).where(
            models.GraphProjectionReplayRun.world_id == world_id,
            models.GraphProjectionReplayRun.mode == "world_rebuild",
            models.GraphProjectionReplayRun.status.in_(("pending", "running")),
        )
    )


def outbox_id_for_source(db: Session, *, world_id: str, source_event_id: str):
    return db.scalar(
        select(models.GraphProjectionOutbox.id).where(
            models.GraphProjectionOutbox.world_id == world_id,
            models.GraphProjectionOutbox.source_event_id == source_event_id,
        ).limit(1)
    )


def get_run_for_update(db: Session, replay_run_id: str):
    return db.scalar(
        select(models.GraphProjectionReplayRun)
        .where(models.GraphProjectionReplayRun.id == replay_run_id)
        .with_for_update()
    )


def latest_outbox(db: Session, statement):
    return db.scalar(
        statement.order_by(
            models.GraphProjectionOutbox.created_at.desc(),
            models.GraphProjectionOutbox.id.desc(),
        ).limit(1)
    )


def ordered_outbox_rows(db: Session, statement):
    return list(
        db.scalars(
            statement.order_by(
                models.GraphProjectionOutbox.created_at.asc(),
                models.GraphProjectionOutbox.id.asc(),
            )
        )
    )


def world_outbox_statement(run: models.GraphProjectionReplayRun):
    return select(models.GraphProjectionOutbox).where(
        models.GraphProjectionOutbox.world_id == run.world_id
    )


def for_source_event(statement, run: models.GraphProjectionReplayRun):
    return statement.where(
        models.GraphProjectionOutbox.source_event_id
        == run.source_event_id
    )


def through_high_water(statement, run: models.GraphProjectionReplayRun):
    return statement.where(
        or_(
            models.GraphProjectionOutbox.created_at
            < run.high_water_created_at,
            and_(
                models.GraphProjectionOutbox.created_at
                == run.high_water_created_at,
                models.GraphProjectionOutbox.id
                <= run.high_water_outbox_id,
            ),
        )
    )


def dead_rows(statement):
    return statement.where(
        models.GraphProjectionOutbox.status == "dead"
    )


def empty_snapshot(statement):
    return statement.where(false())


def get_run(db: Session, replay_run_id: str) -> models.GraphProjectionReplayRun | None:
    return db.get(models.GraphProjectionReplayRun, replay_run_id)


def ordered_world_outbox_ids(db: Session, world_id: str) -> tuple[str, ...]:
    return tuple(
        str(value)
        for value in db.scalars(
            select(models.GraphProjectionOutbox.id)
            .where(models.GraphProjectionOutbox.world_id == world_id)
            .order_by(
                models.GraphProjectionOutbox.created_at,
                models.GraphProjectionOutbox.id,
            )
        )
    )
