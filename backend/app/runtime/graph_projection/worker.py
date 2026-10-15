from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import threading
import time
from typing import Callable
from app.core.sqlite_concurrency import is_sqlite_contention

from app.domains.relationships.contracts.outbox import (OutboxCapacityError, OutboxPort, ProjectionWorkItem)
from app.domains.relationships.contracts.projection import (
    RelationshipProjectionBackendError,
    RelationshipProjectionPort,
)
from app.domains.relationships.contracts.projection_commands import (ProjectionCommandError)
from app.runtime.graph_projection.sqlalchemy_outbox import (
    SessionFactory,
    SqlAlchemyProjectionOutbox,
)
from app.runtime.graph_projection.metrics import graph_metrics


logger = logging.getLogger(__name__)


ProjectionStore = RelationshipProjectionPort


@dataclass(frozen=True)
class ProjectionBatchResult:
    claimed: int
    succeeded: int
    retried: int
    dead: int
    cancelled: int
    lease_lost: int
    graph_degraded: bool = False
    canonical_busy: int = 0


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
        session_factory: SessionFactory | None = None,
        outbox: OutboxPort | None = None,
        store: ProjectionStore,
        worker_id: str,
        batch_size: int = 50,
        concurrency: int = 2,
        command_timeout_seconds: float = 5.0,
        shutdown_drain_seconds: float = 20.0,
    ) -> None:
        if outbox is None and session_factory is None:
            raise ValueError("session_factory or outbox is required")
        self._outbox = outbox or SqlAlchemyProjectionOutbox(session_factory)
        self._store = store
        self.worker_id = worker_id[:128]
        self.batch_size = max(1, min(batch_size, 100))
        self.concurrency = max(1, min(concurrency, 4))
        self.shutdown_drain_seconds = max(0.1, min(shutdown_drain_seconds, 30.0))
        self.command_timeout_seconds = min(
            max(0.1, min(command_timeout_seconds, 10.0)),
            self.shutdown_drain_seconds,
        )

    def _claim(self) -> tuple[ProjectionWorkItem, ...]:
        return self._outbox.claim(
            worker_id=self.worker_id,
            now=_utc_now(),
            batch_size=self.batch_size,
        )

    def _finalize_success(self, outbox_id: str) -> str:
        return self._outbox.finalize_success(
            outbox_id=outbox_id,
            worker_id=self.worker_id,
            now=_utc_now(),
        )

    def _finalize_failure(
        self,
        outbox_id: str,
        *,
        error_class: str,
        terminal: bool,
        cancelled: bool = False,
    ) -> str:
        return self._outbox.finalize_failure(
            outbox_id=outbox_id,
            worker_id=self.worker_id,
            now=_utc_now(),
            error_class=error_class,
            terminal=terminal,
            cancelled=cancelled,
        )

    def _process_one(self, item: ProjectionWorkItem) -> _ProjectionItemResult:
        try:
            return self._process_claim(item)
        except Exception as exc:
            if not (isinstance(exc, OutboxCapacityError) or is_sqlite_contention(exc)):
                raise
            # load/ack/failure recording may all contend. Do not turn canonical
            # pressure into a poison payload or spend another graph attempt.
            logger.warning("graph_projection_canonical_deferred error_type=%s", type(exc).__name__)
            return _ProjectionItemResult(status="storage_busy", graph_degraded=True)

    def _process_claim(self, item: ProjectionWorkItem) -> _ProjectionItemResult:
        outbox_id = item.id
        started = time.monotonic()
        projection_type = item.projection_type
        error_class = "none"
        graph_degraded = False
        try:
            graph_metrics.increment(
                "graph_projection_claimed_total",
                projection_type=projection_type,
            )
            command = self._outbox.load_command(outbox_id=outbox_id)
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
        except RelationshipProjectionBackendError as exc:
            error_class = exc.error_class
            status = self._finalize_failure(
                outbox_id,
                error_class=exc.error_class,
                terminal=False,
            )
            graph_degraded = True
        except Exception as exc:
            if isinstance(exc, OutboxCapacityError) or is_sqlite_contention(exc):
                raise
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

    def _release_unstarted(
        self, items: list[ProjectionWorkItem]
    ) -> list[_ProjectionItemResult]:
        results, errors = [], []
        for item in items:
            try:
                status = self._finalize_failure(item.id, error_class="shutdown_interrupted", terminal=False)
                results.append(_ProjectionItemResult(status=status))
            except Exception as exc:
                if isinstance(exc, OutboxCapacityError) or is_sqlite_contention(exc):
                    results.append(_ProjectionItemResult(status="storage_busy", graph_degraded=True))
                else:
                    errors.append(exc)
        if errors:
            raise errors[0]
        return results

    def process_batch(
        self,
        *,
        stop_event: threading.Event | None = None,
    ) -> ProjectionBatchResult:
        stop = stop_event or threading.Event()
        if stop.is_set():
            return ProjectionBatchResult(0, 0, 0, 0, 0, 0)
        items = self._claim()
        if not items:
            return ProjectionBatchResult(0, 0, 0, 0, 0, 0)
        item_results: list[_ProjectionItemResult] = []
        if stop.is_set():
            item_results.extend(self._release_unstarted(list(items)))
        elif self.concurrency == 1 or len(items) == 1:
            for index, item in enumerate(items):
                if stop.is_set():
                    item_results.extend(self._release_unstarted(list(items[index:])))
                    break
                try:
                    item_results.append(self._process_one(item))
                except Exception:
                    self._release_unstarted(list(items[index + 1:]))
                    raise
        else:
            with ThreadPoolExecutor(
                max_workers=self.concurrency,
                thread_name_prefix="graph-projector",
            ) as executor:
                remaining = iter(items)
                active: dict[Future[_ProjectionItemResult], ProjectionWorkItem] = {}
                unstarted: list[ProjectionWorkItem] = []
                errors: list[Exception] = []
                for _ in range(min(self.concurrency, len(items))):
                    item = next(remaining, None)
                    if item is None:
                        break
                    active[executor.submit(self._process_one, item)] = item
                while active:
                    completed, _ = wait(active, return_when=FIRST_COMPLETED)
                    for future in completed:
                        active.pop(future)
                        try:
                            item_results.append(future.result())
                        except Exception as exc:
                            errors.append(exc)
                    if stop.is_set() or errors:
                        if not unstarted:
                            unstarted.extend(remaining)
                        continue
                    while len(active) < self.concurrency:
                        item = next(remaining, None)
                        if item is None:
                            break
                        active[executor.submit(self._process_one, item)] = item
                item_results.extend(self._release_unstarted(unstarted))
                if errors:
                    raise errors[0]  # Every started future was consumed first.
        statuses = [item.status for item in item_results]
        return ProjectionBatchResult(
            claimed=len(items),
            succeeded=statuses.count("succeeded"),
            retried=statuses.count("pending"),
            dead=statuses.count("dead"),
            cancelled=statuses.count("cancelled"),
            lease_lost=statuses.count("lease_lost"),
            graph_degraded=any(item.graph_degraded for item in item_results),
            canonical_busy=statuses.count("storage_busy"),
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
        retry_delay = interval
        canonical_recovery = False
        while not stop.is_set():
            try:
                result = self.process_batch(stop_event=stop)
                if canonical_recovery and not result.canonical_busy:
                    canonical_recovery = self._outbox.has_unfinished()
            except Exception as exc:
                if not (isinstance(exc, OutboxCapacityError) or is_sqlite_contention(exc)):
                    raise
                # Keep the registered worker alive. Any claimed commands retain
                # their existing lease/finalize fence and expire normally.
                logger.warning("graph_projector_canonical_deferred error_type=%s", type(exc).__name__)
                canonical_recovery = True
                if state_listener is not None:
                    state_listener("degraded")
                stop.wait(retry_delay)
                retry_delay = min(retry_delay * 2, max(interval, 30.0))
                continue
            if result.canonical_busy:
                canonical_recovery = True
                if state_listener is not None:
                    state_listener("degraded")
                stop.wait(retry_delay)
                retry_delay = min(retry_delay * 2, max(interval, 30.0))
                continue
            retry_delay = interval
            if result.graph_degraded or canonical_recovery:
                if state_listener is not None:
                    state_listener("degraded")
            elif result.succeeded > 0 and state_listener is not None:
                state_listener("ready")
            if result.claimed == 0:
                if canonical_recovery:
                    stop.wait(interval)
                    continue
                if connectivity_probe is not None:
                    try:
                        connectivity_probe()
                    except RelationshipProjectionBackendError:
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
