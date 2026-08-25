from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
import time

from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session

from app import models
from app.core.ids import uuid7_string
from app.domains.relationships.projection.digest import projection_digest
from app.services.graph_projection_commands import (
    ProjectionCommand,
    build_projection_command,
)
from app.services.graph_projection_metrics import graph_metrics
from app.services.graph_projection_worker import ProjectionStore, SessionFactory


class ReplayStore(ProjectionStore, Protocol):
    def clear_world(self, world_id: str) -> None: ...

    def world_digest(self, world_id: str) -> dict[str, list[str]]: ...


class GraphReplayError(RuntimeError):
    def __init__(self, error_class: str) -> None:
        super().__init__(error_class)
        self.error_class = error_class


def _now() -> datetime:
    return datetime.now(UTC)


def create_replay_run(
    db: Session,
    *,
    world_id: str,
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
    if db.get(models.World, world_id) is None:
        raise GraphReplayError("world_not_found")
    if mode == "world_rebuild":
        active_run_id = db.scalar(
            select(models.GraphProjectionReplayRun.id).where(
                models.GraphProjectionReplayRun.world_id == world_id,
                models.GraphProjectionReplayRun.mode == "world_rebuild",
                models.GraphProjectionReplayRun.status.in_(("pending", "running")),
            )
        )
        if active_run_id is not None:
            raise GraphReplayError("replay_active")
    if source_event_id is not None:
        event = db.get(models.SocialEvent, source_event_id)
        if event is None or event.world_id != world_id:
            raise GraphReplayError("source_missing")
        outbox_exists = db.scalar(
            select(models.GraphProjectionOutbox.id).where(
                models.GraphProjectionOutbox.world_id == world_id,
                models.GraphProjectionOutbox.source_event_id == source_event_id,
            ).limit(1)
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


class GraphProjectionReplayService:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        store: ReplayStore,
        worker_id: str,
        command_timeout_seconds: float = 5.0,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self.worker_id = worker_id[:128]
        self.command_timeout_seconds = max(
            0.1, min(command_timeout_seconds, 10.0)
        )

    def _start(self, replay_run_id: str) -> tuple[str, str, str | None, list[str]]:
        now = _now()
        with self._session_factory() as db:
            run = db.scalar(
                select(models.GraphProjectionReplayRun)
                .where(models.GraphProjectionReplayRun.id == replay_run_id)
                .with_for_update()
            )
            if run is None:
                raise GraphReplayError("replay_not_found")
            if run.status not in {"pending", "running"}:
                raise GraphReplayError("replay_state_invalid")
            if (
                run.status == "running"
                and run.lease_expires_at is not None
                and run.lease_expires_at > now
                and run.lease_owner != self.worker_id
            ):
                raise GraphReplayError("replay_lease_active")
            snapshot_initialized = run.started_at is not None
            run.status = "running"
            run.started_at = run.started_at or now
            run.lease_owner = self.worker_id
            run.lease_expires_at = now + timedelta(minutes=5)

            statement = select(models.GraphProjectionOutbox).where(
                models.GraphProjectionOutbox.world_id == run.world_id
            )
            if run.mode == "world_rebuild":
                if not snapshot_initialized:
                    high_water = db.scalar(
                        statement.order_by(
                            models.GraphProjectionOutbox.created_at.desc(),
                            models.GraphProjectionOutbox.id.desc(),
                        ).limit(1)
                    )
                    if high_water is not None:
                        run.high_water_created_at = high_water.created_at
                        run.high_water_outbox_id = high_water.id
                if (
                    run.high_water_created_at is not None
                    and run.high_water_outbox_id is not None
                ):
                    statement = statement.where(
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
                elif snapshot_initialized:
                    statement = statement.where(false())
            else:
                statement = statement.where(
                    models.GraphProjectionOutbox.source_event_id
                    == run.source_event_id
                )
                if run.mode == "dead_retry":
                    statement = statement.where(
                        models.GraphProjectionOutbox.status == "dead"
                    )
            outbox_ids = list(
                db.scalars(
                    statement.order_by(
                        models.GraphProjectionOutbox.created_at.asc(),
                        models.GraphProjectionOutbox.id.asc(),
                    )
                )
            )
            run.total_count = len(outbox_ids)
            db.commit()
            return run.world_id, run.mode, run.source_event_id, [
                row.id for row in outbox_ids
            ]

    def _renew_lease(self, replay_run_id: str) -> None:
        now = _now()
        with self._session_factory() as db:
            run = db.scalar(
                select(models.GraphProjectionReplayRun)
                .where(models.GraphProjectionReplayRun.id == replay_run_id)
                .with_for_update()
            )
            if (
                run is None
                or run.status != "running"
                or run.lease_owner != self.worker_id
            ):
                raise GraphReplayError("lease_lost")
            run.lease_expires_at = now + timedelta(minutes=5)
            db.commit()

    def execute(self, replay_run_id: str) -> models.GraphProjectionReplayRun:
        started = time.monotonic()
        world_id, mode, _, outbox_ids = self._start(replay_run_id)
        applied = noop = failed = 0
        commands: list[ProjectionCommand] = []
        try:
            if mode == "world_rebuild":
                self._store.clear_world(world_id)
                self._renew_lease(replay_run_id)
            for outbox_id in outbox_ids:
                self._renew_lease(replay_run_id)
                with self._session_factory() as db:
                    command = build_projection_command(
                        db,
                        outbox_id=outbox_id,
                        replay_relationship_snapshot=mode == "world_rebuild",
                    )
                commands.append(command)
                result = self._store.apply(
                    command, timeout_seconds=self.command_timeout_seconds
                )
                if result in {"noop", "stale_noop"}:
                    noop += 1
                else:
                    applied += 1
            if mode == "world_rebuild":
                expected_digest = projection_digest(commands)
                actual_digest = self._store.world_digest(world_id)
                if actual_digest != expected_digest:
                    raise GraphReplayError("replay_parity_mismatch")
        except Exception as exc:
            failed += 1
            error_class = getattr(exc, "error_class", "internal_error")
            with self._session_factory() as db:
                run = db.get(models.GraphProjectionReplayRun, replay_run_id)
                if run is None:
                    raise GraphReplayError("replay_not_found") from None
                run.applied_count = applied
                run.noop_count = noop
                run.failed_count = failed
                run.status = "failed"
                run.last_error_class = str(error_class)[:120]
                run.lease_owner = None
                run.lease_expires_at = None
                run.completed_at = _now()
                db.commit()
            graph_metrics.increment(
                "graph_replay_total", mode=mode, status="failed"
            )
            graph_metrics.observe(
                "graph_replay_duration_seconds",
                time.monotonic() - started,
                mode=mode,
                status="failed",
            )
            raise GraphReplayError(str(error_class)) from None

        with self._session_factory() as db:
            run = db.get(models.GraphProjectionReplayRun, replay_run_id)
            if run is None:
                raise GraphReplayError("replay_not_found")
            if run.lease_owner != self.worker_id:
                raise GraphReplayError("lease_lost")
            run.applied_count = applied
            run.noop_count = noop
            run.failed_count = failed
            run.status = "succeeded"
            run.last_error_class = None
            run.lease_owner = None
            run.lease_expires_at = None
            run.completed_at = _now()
            db.commit()
            db.refresh(run)
            graph_metrics.increment(
                "graph_replay_total", mode=mode, status="succeeded"
            )
            graph_metrics.observe(
                "graph_replay_duration_seconds",
                time.monotonic() - started,
                mode=mode,
                status="succeeded",
            )
            return run
