from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import threading
import time
from typing import Callable, Protocol

from sqlalchemy.orm import Session

from app import models
from app.cruds import graph_projection as graph_projection_crud
from app.integrations.neo4j import GraphClientError
from app.services.graph_projection_metrics import graph_metrics
from app.services.graph_projection_commands import (
    ProjectionCommand,
    ProjectionCommandError,
    build_projection_command,
)


logger = logging.getLogger(__name__)


class ProjectionStore(Protocol):
    def apply(
        self, command: ProjectionCommand, *, timeout_seconds: float = 5.0
    ) -> str: ...


SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class ProjectionBatchResult:
    claimed: int
    succeeded: int
    retried: int
    dead: int
    cancelled: int
    lease_lost: int
    graph_degraded: bool = False


@dataclass(frozen=True)
class _ProjectionItemResult:
    status: str
    graph_degraded: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GraphProjectionWorker:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        store: ProjectionStore,
        worker_id: str,
        batch_size: int = 50,
        concurrency: int = 2,
        command_timeout_seconds: float = 5.0,
        shutdown_drain_seconds: float = 20.0,
    ) -> None:
        self._session_factory = session_factory
        self._store = store
        self.worker_id = worker_id[:128]
        self.batch_size = max(1, min(batch_size, 100))
        self.concurrency = max(1, min(concurrency, 4))
        self.shutdown_drain_seconds = max(0.1, min(shutdown_drain_seconds, 30.0))
        self.command_timeout_seconds = min(
            max(0.1, min(command_timeout_seconds, 10.0)),
            self.shutdown_drain_seconds,
        )

    def _claim(self) -> list[str]:
        with self._session_factory() as db:
            ids = graph_projection_crud.claim_batch(
                db,
                worker_id=self.worker_id,
                now=_utc_now(),
                batch_size=self.batch_size,
            )
            db.commit()
            return ids

    def _finalize_success(self, outbox_id: str) -> str:
        with self._session_factory() as db:
            ok = graph_projection_crud.finalize_success(
                db,
                outbox_id=outbox_id,
                worker_id=self.worker_id,
                now=_utc_now(),
            )
            db.commit()
            return "succeeded" if ok else "lease_lost"

    def _finalize_failure(
        self,
        outbox_id: str,
        *,
        error_class: str,
        terminal: bool,
        cancelled: bool = False,
    ) -> str:
        with self._session_factory() as db:
            status = graph_projection_crud.finalize_failure(
                db,
                outbox_id=outbox_id,
                worker_id=self.worker_id,
                now=_utc_now(),
                error_class=error_class,
                terminal=terminal,
                cancelled=cancelled,
            )
            db.commit()
            return status

    def _process_one(self, outbox_id: str) -> _ProjectionItemResult:
        started = time.monotonic()
        projection_type = "unknown"
        error_class = "none"
        graph_degraded = False
        try:
            with self._session_factory() as db:
                row = db.get(models.GraphProjectionOutbox, outbox_id)
                if row is not None:
                    projection_type = row.projection_type
                graph_metrics.increment(
                    "graph_projection_claimed_total",
                    projection_type=projection_type,
                )
                command = build_projection_command(db, outbox_id=outbox_id)
            result_class = self._store.apply(
                command, timeout_seconds=self.command_timeout_seconds
            )
            status = self._finalize_success(outbox_id)
            logger.info(
                "graph_projection_result",
                extra={
                    "outbox_id": outbox_id,
                    "projection_type": projection_type,
                    "worker_id": self.worker_id,
                    "result_class": result_class if status == "succeeded" else status,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )
            duration = time.monotonic() - started
            graph_metrics.observe(
                "graph_projection_duration_seconds",
                duration,
                projection_type=projection_type,
            )
            if status == "succeeded":
                graph_metrics.increment(
                    "graph_projection_succeeded_total",
                    projection_type=projection_type,
                    result_class=result_class,
                )
            return _ProjectionItemResult(status=status)
        except ProjectionCommandError as exc:
            error_class = exc.error_class
            status = self._finalize_failure(
                outbox_id,
                error_class=exc.error_class,
                terminal=exc.terminal,
                cancelled=exc.cancelled,
            )
        except GraphClientError as exc:
            error_class = exc.error_class
            status = self._finalize_failure(
                outbox_id,
                error_class=exc.error_class,
                terminal=False,
            )
            graph_degraded = True
        except Exception:
            error_class = "internal_error"
            status = self._finalize_failure(
                outbox_id,
                error_class="internal_error",
                terminal=False,
            )
        duration = time.monotonic() - started
        graph_metrics.observe(
            "graph_projection_duration_seconds",
            duration,
            projection_type=projection_type,
        )
        if status == "pending":
            graph_metrics.increment(
                "graph_projection_retry_total", error_class=error_class
            )
        elif status == "dead":
            graph_metrics.increment(
                "graph_projection_dead_total", error_class=error_class
            )
        logger.warning(
            "graph_projection_failed",
            extra={
                "outbox_id": outbox_id,
                "projection_type": projection_type,
                "worker_id": self.worker_id,
                "result_class": status,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return _ProjectionItemResult(
            status=status,
            graph_degraded=graph_degraded,
        )

    def _release_unstarted(self, outbox_ids: list[str]) -> list[_ProjectionItemResult]:
        return [
            _ProjectionItemResult(
                status=self._finalize_failure(
                    outbox_id,
                    error_class="shutdown_interrupted",
                    terminal=False,
                )
            )
            for outbox_id in outbox_ids
        ]

    def process_batch(
        self,
        *,
        stop_event: threading.Event | None = None,
    ) -> ProjectionBatchResult:
        stop = stop_event or threading.Event()
        if stop.is_set():
            return ProjectionBatchResult(0, 0, 0, 0, 0, 0)
        outbox_ids = self._claim()
        if not outbox_ids:
            return ProjectionBatchResult(0, 0, 0, 0, 0, 0)
        item_results: list[_ProjectionItemResult] = []
        if stop.is_set():
            item_results.extend(self._release_unstarted(outbox_ids))
        elif self.concurrency == 1 or len(outbox_ids) == 1:
            for index, outbox_id in enumerate(outbox_ids):
                if stop.is_set():
                    item_results.extend(self._release_unstarted(outbox_ids[index:]))
                    break
                item_results.append(self._process_one(outbox_id))
        else:
            with ThreadPoolExecutor(
                max_workers=self.concurrency,
                thread_name_prefix="graph-projector",
            ) as executor:
                remaining = iter(outbox_ids)
                active: dict[Future[_ProjectionItemResult], str] = {}
                unstarted: list[str] = []
                for _ in range(min(self.concurrency, len(outbox_ids))):
                    outbox_id = next(remaining, None)
                    if outbox_id is None:
                        break
                    active[executor.submit(self._process_one, outbox_id)] = outbox_id
                while active:
                    completed, _ = wait(active, return_when=FIRST_COMPLETED)
                    for future in completed:
                        active.pop(future)
                        item_results.append(future.result())
                    if stop.is_set():
                        if not unstarted:
                            unstarted.extend(remaining)
                        continue
                    while len(active) < self.concurrency:
                        outbox_id = next(remaining, None)
                        if outbox_id is None:
                            break
                        active[executor.submit(self._process_one, outbox_id)] = outbox_id
                item_results.extend(self._release_unstarted(unstarted))
        statuses = [item.status for item in item_results]
        return ProjectionBatchResult(
            claimed=len(outbox_ids),
            succeeded=statuses.count("succeeded"),
            retried=statuses.count("pending"),
            dead=statuses.count("dead"),
            cancelled=statuses.count("cancelled"),
            lease_lost=statuses.count("lease_lost"),
            graph_degraded=any(item.graph_degraded for item in item_results),
        )

    def run_loop(
        self,
        *,
        poll_interval_seconds: float = 2.0,
        stop_event: threading.Event | None = None,
        connectivity_probe: Callable[[], None] | None = None,
        state_listener: Callable[[str], None] | None = None,
    ) -> None:
        interval = max(1.0, poll_interval_seconds)
        stop = stop_event or threading.Event()
        while not stop.is_set():
            result = self.process_batch(stop_event=stop)
            if result.graph_degraded:
                if state_listener is not None:
                    state_listener("degraded")
            elif result.succeeded > 0 and state_listener is not None:
                state_listener("ready")
            if result.claimed == 0:
                if connectivity_probe is not None:
                    try:
                        connectivity_probe()
                    except GraphClientError:
                        if state_listener is not None:
                            state_listener("degraded")
                    except Exception:
                        logger.exception("graph projector connectivity probe failed")
                        if state_listener is not None:
                            state_listener("degraded")
                    else:
                        if state_listener is not None:
                            state_listener("ready")
                stop.wait(interval)
