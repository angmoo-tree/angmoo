from __future__ import annotations

from datetime import UTC, datetime
import time

from sqlalchemy.orm import Session

from app.domains.relationships import models
from app.domains.relationships.contracts.replay import ReplayStore
from app.domains.relationships.exceptions import GraphReplayError
from app.domains.relationships.service import replay as replay_service
from app.domains.worlds.service.character_entry import get_character_entry_world
from app.domains.relationships.utils.projection_digest import (projection_digest)
from app.runtime.graph_projection.sqlalchemy_commands import (
    ProjectionCommand,
    build_projection_command,
)
from app.runtime.graph_projection.metrics import graph_metrics
from app.runtime.graph_projection.sqlalchemy_outbox import SessionFactory


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
    return replay_service.create_replay_run(
        db, world_id=world_id, mode=mode, source_event_id=source_event_id,
        requested_by=requested_by, reason_code=reason_code,
        get_world=lambda identifier: get_character_entry_world(db, identifier),
    )


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
            return replay_service.start(db, replay_run_id=replay_run_id, worker_id=self.worker_id, now=now)

    def _renew_lease(self, replay_run_id: str) -> None:
        now = _now()
        with self._session_factory() as db:
            replay_service.renew_lease(db, replay_run_id=replay_run_id, worker_id=self.worker_id, now=now)

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
                replay_service.finish_failure(
                    db, replay_run_id=replay_run_id, applied=applied, noop=noop,
                    failed=failed, error_class=error_class, clock=_now,
                )
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
            run = replay_service.finish_success(
                db, replay_run_id=replay_run_id, worker_id=self.worker_id,
                applied=applied, noop=noop, failed=failed, clock=_now,
            )
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
