"""Replay admission, lease/high-water state and completion audit ownership."""
from __future__ import annotations
from collections.abc import Callable
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.ids import uuid7_string
from app.domains.relationships import models
from app.domains.relationships.exceptions import GraphReplayError
from app.domains.relationships.repository import replay as replay_repository
from app.domains.relationships.repository import projection_commands as command_repository


def create_replay_run(
    db: Session,
    *,
    world_id: str,
    get_world: Callable[[str], object | None],
    mode: str,
    source_event_id: str | None,
    requested_by: str,
    reason_code: str,
) -> models.GraphProjectionReplayRun:
    if mode not in {"world_rebuild", "event_reprocess", "dead_retry"}:
        raise GraphReplayError("replay_mode_invalid")
    if (mode == "world_rebuild") != (source_event_id is None):
        raise GraphReplayError("replay_source_invalid")
    if not requested_by.strip() or len(requested_by) > 120:
        raise GraphReplayError("replay_requester_invalid")
    if not reason_code.strip() or len(reason_code) > 80:
        raise GraphReplayError("replay_reason_invalid")
    if get_world(world_id) is None:
        raise GraphReplayError("world_not_found")
    if mode == "world_rebuild":
        active_run_id = replay_repository.active_world_rebuild_id(db, world_id=world_id)
        if active_run_id is not None:
            raise GraphReplayError("replay_active")
    if source_event_id is not None:
        event = command_repository.get_event(db, source_event_id)
        if event is None or event.world_id != world_id:
            raise GraphReplayError("source_missing")
        outbox_exists = replay_repository.outbox_id_for_source(
            db, world_id=world_id, source_event_id=source_event_id
        )
        if outbox_exists is None:
            raise GraphReplayError("replay_outbox_missing")
    row = models.GraphProjectionReplayRun(
        id=uuid7_string(),
        world_id=world_id,
        mode=mode,
        source_event_id=source_event_id,
        requested_by=requested_by.strip(),
        reason_code=reason_code.strip(),
        status="pending",
        total_count=0,
        applied_count=0,
        noop_count=0,
        failed_count=0,
    )
    db.add(row)
    db.flush()
    return row


def start(
    db: Session, *, replay_run_id: str, worker_id: str, now: datetime
) -> tuple[str, str, str | None, list[str]]:
    run = replay_repository.get_run_for_update(db, replay_run_id)
    if run is None:
        raise GraphReplayError("replay_not_found")
    if run.status not in {"pending", "running"}:
        raise GraphReplayError("replay_state_invalid")
    if (
        run.status == "running"
        and run.lease_expires_at is not None
        and run.lease_expires_at > now
        and run.lease_owner != worker_id
    ):
        raise GraphReplayError("replay_lease_active")
    snapshot_initialized = run.started_at is not None
    run.status = "running"
    run.started_at = run.started_at or now
    run.lease_owner = worker_id
    run.lease_expires_at = now + timedelta(minutes=5)

    statement = replay_repository.world_outbox_statement(run)
    if run.mode == "world_rebuild":
        if not snapshot_initialized:
            high_water = replay_repository.latest_outbox(db, statement)
            if high_water is not None:
                run.high_water_created_at = high_water.created_at
                run.high_water_outbox_id = high_water.id
        if (
            run.high_water_created_at is not None
            and run.high_water_outbox_id is not None
        ):
            statement = replay_repository.through_high_water(statement, run)
        elif snapshot_initialized:
            statement = replay_repository.empty_snapshot(statement)
    else:
        statement = replay_repository.for_source_event(statement, run)
        if run.mode == "dead_retry":
            statement = replay_repository.dead_rows(statement)
    outbox_ids = replay_repository.ordered_outbox_rows(db, statement)
    run.total_count = len(outbox_ids)
    db.commit()
    return run.world_id, run.mode, run.source_event_id, [
        row.id for row in outbox_ids
    ]


def renew_lease(db: Session, *, replay_run_id: str, worker_id: str, now: datetime) -> None:
    run = replay_repository.get_run_for_update(db, replay_run_id)
    if (
        run is None
        or run.status != "running"
        or run.lease_owner != worker_id
    ):
        raise GraphReplayError("lease_lost")
    run.lease_expires_at = now + timedelta(minutes=5)
    db.commit()


def finish_failure(
    db: Session,
    *,
    replay_run_id: str,
    applied: int,
    noop: int,
    failed: int,
    error_class: object,
    clock: Callable[[], datetime],
) -> None:
    run = replay_repository.get_run(db, replay_run_id)
    if run is None:
        raise GraphReplayError("replay_not_found") from None
    run.applied_count = applied
    run.noop_count = noop
    run.failed_count = failed
    run.status = "failed"
    run.last_error_class = str(error_class)[:120]
    run.lease_owner = None
    run.lease_expires_at = None
    run.completed_at = clock()
    db.commit()


def finish_success(
    db: Session,
    *,
    replay_run_id: str,
    worker_id: str,
    applied: int,
    noop: int,
    failed: int,
    clock: Callable[[], datetime],
) -> models.GraphProjectionReplayRun:
    run = replay_repository.get_run(db, replay_run_id)
    if run is None:
        raise GraphReplayError("replay_not_found")
    if run.lease_owner != worker_id:
        raise GraphReplayError("lease_lost")
    run.applied_count = applied
    run.noop_count = noop
    run.failed_count = failed
    run.status = "succeeded"
    run.last_error_class = None
    run.lease_owner = None
    run.lease_expires_at = None
    run.completed_at = clock()
    db.commit()
    db.refresh(run)
    return run
