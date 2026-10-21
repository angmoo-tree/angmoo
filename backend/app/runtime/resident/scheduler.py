from __future__ import annotations

import asyncio

import logging

import os

from pathlib import Path

from time import monotonic

from types import TracebackType

from typing import Awaitable

from typing import Callable

from typing import Any

from uuid import uuid4

from app.domains.routines import schemas

from app.runtime.routines.lifecycle_references import SqlAlchemyLifecycleReferences

from app.config import Settings

from app.config import settings

from app.database import SessionLocal

from app.domains.runtime.service.lease_coordinator import SchedulerLeaseCoordinator

from app.domains.runtime.exceptions import SchedulerLeaseHeldError

from app.domains.runtime.exceptions import SchedulerLeaseLostError

from app.domains.runtime.contracts.lease import SchedulerTickResult

from app.runtime.persistence.scheduler_lease import SqlAlchemySchedulerLeaseRepository
from app.runtime.persistence.sqlite_scheduler_lease import SqliteSchedulerLeaseRepository
from app.runtime.resident.lease_executor import SchedulerLeaseExecutor, lease_call
from app.runtime.resident.lease_errors import SchedulerHeartbeatDeadlineExceeded
from app.exceptions import SqliteBusyRetryExhausted, SqliteTaskQueueFull, SqliteWriteDeadlineExceeded
from datetime import UTC, datetime

from app.runtime.persistence.scheduler_fence import scheduler_fence

from app.runtime.resident import execution as agent_runs

from app.domains.routines.service.lifecycle import reconcile_all_elapsed_routines

logger = logging.getLogger(__name__)

SchedulerStateListener = Callable[[str], None]

class SchedulerShutdownDrainTimeout(RuntimeError):
    pending_tasks: tuple[asyncio.Task, ...] = ()

class SchedulerProcessLockHeld(RuntimeError):
    pass

class SchedulerProcessLock:
    """Same-filesystem singleton guard paired with the durable SQLite lease."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._handle = None

    def __enter__(self) -> "SchedulerProcessLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise SchedulerProcessLockHeld("scheduler process lock is held") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("ascii"))
        handle.flush()
        self._handle = handle
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

def _coordinator(
    config: Settings = settings,
    session_factory: Callable[[], Any] | None = None,
) -> SchedulerLeaseCoordinator:
    resolved_session_factory = session_factory or SessionLocal
    if (
        config.RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS
        >= config.RESIDENT_TICK_LEASE_TTL_SECONDS
    ):
        raise ValueError(
            "RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS must be shorter than "
            "RESIDENT_TICK_LEASE_TTL_SECONDS"
        )
    with resolved_session_factory() as session:
        engine = session.get_bind()
    repository = SqliteSchedulerLeaseRepository(engine) if engine.dialect.name == "sqlite" else SqlAlchemySchedulerLeaseRepository(resolved_session_factory)
    return SchedulerLeaseCoordinator(
        repository,
        ttl_seconds=config.RESIDENT_TICK_LEASE_TTL_SECONDS,
        interval_seconds=config.resident_tick_interval_seconds,
    )

async def _tick_once(
    config: Settings = settings,
    session_factory: Callable[[], Any] | None = None,
) -> schemas.ResidentSlotTickRead:
    resolved_session_factory = session_factory or SessionLocal
    with resolved_session_factory() as db:
        transition = reconcile_all_elapsed_routines(
            db, references=SqlAlchemyLifecycleReferences(db)
        )
        if transition.completed or transition.skipped:
            logger.info(
                "elapsed routines reconciled completed=%s skipped=%s",
                transition.completed,
                transition.skipped,
            )
        if config.DAILY_PREPARATION_ENABLED:
            from app.runtime.daily_preparation import prepare_due_dates
            db.commit()
            await prepare_due_dates(db, limit=config.resident_tick_max_runs)
        return await agent_runs.tick_resident_slots(
            db,
            schemas.ResidentSlotTickCreate(
                post_id=config.resident_tick_post_id,
                max_runs=config.resident_tick_max_runs,
                timeout_seconds=config.openclaw_timeout_seconds,
            ),
        )

async def _run_fenced_tick_with_heartbeat(
    *,
    coordinator: SchedulerLeaseCoordinator,
    owner_id: str,
    fencing_epoch: int,
    tick_runner: Callable[[], Awaitable[schemas.ResidentSlotTickRead]],
    sleep: Callable[[float], Awaitable[None]],
    stop_event: asyncio.Event | None = None,
    drain_timeout_seconds: float | None = None,
    config: Settings = settings,
) -> schemas.ResidentSlotTickRead:
    from app.contracts.activity_cancellation import CancellationIntent, CancellationReason, cancellation_scope
    cancellation = CancellationIntent()
    async def run_tick() -> schemas.ResidentSlotTickRead:
        with cancellation_scope(cancellation), scheduler_fence(owner_id=owner_id, fencing_epoch=fencing_epoch):
            return await tick_runner()

    async def heartbeat() -> None:
        while True:
            await sleep(config.RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS)
            snapshot = await _heartbeat_with_budget(coordinator, owner_id=owner_id, fencing_epoch=fencing_epoch, config=config)
            _record_proof(config, snapshot)

    tick_task = asyncio.create_task(run_tick())
    heartbeat_task = asyncio.create_task(heartbeat())
    stop_task = asyncio.create_task(stop_event.wait()) if stop_event is not None else None
    tasks = {tick_task, heartbeat_task, *([stop_task] if stop_task else [])}
    timeout = config.resident_tick_shutdown_drain_seconds if drain_timeout_seconds is None else max(0.1, drain_timeout_seconds)
    primary_error: BaseException | None = None
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if heartbeat_task in done:
            error = heartbeat_task.exception()
            if error is not None:
                raise error
            raise SchedulerLeaseLostError("scheduler_heartbeat_stopped")
        if stop_task is not None and stop_task in done and tick_task not in done:
            done, _ = await asyncio.wait({tick_task, heartbeat_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if heartbeat_task in done:
                error = heartbeat_task.exception()
                if error is not None:
                    raise error
            if tick_task not in done:
                raise SchedulerShutdownDrainTimeout("scheduler_tick_drain_timeout")
        return tick_task.result()
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if heartbeat_task.done() and not heartbeat_task.cancelled() and heartbeat_task.exception() is not None:
            failure = heartbeat_task.exception()
            cancellation.reason = (CancellationReason.LEASE_LOST if isinstance(failure, SchedulerLeaseLostError)
                else CancellationReason.HEARTBEAT if isinstance(failure, (SqliteBusyRetryExhausted, SqliteTaskQueueFull, SchedulerHeartbeatDeadlineExceeded))
                else CancellationReason.UNKNOWN)
        elif stop_event is not None and stop_event.is_set():
            cancellation.reason = CancellationReason.SHUTDOWN
        for task in tasks:
            if not task.done(): task.cancel()
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        for task in tasks - pending:
            if not task.cancelled(): task.exception()
        if pending:
            if primary_error is not None:
                # Preserve the original lease/tick failure while preventing a
                # replacement runner until its real child work has settled.
                primary_error.pending_tasks = tuple(pending)
                raise primary_error
            error = SchedulerShutdownDrainTimeout("scheduler_children_not_settled")
            error.pending_tasks = tuple(pending)
            raise error

async def _sleep_until_next_tick_with_heartbeat(
    *,
    coordinator: SchedulerLeaseCoordinator,
    owner_id: str,
    fencing_epoch: int,
    duration_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
    monotonic_clock: Callable[[], float] = monotonic,
    stop_event: asyncio.Event | None = None,
    config: Settings = settings,
) -> bool:
    deadline = monotonic_clock() + max(0.0, duration_seconds)
    heartbeat_interval = max(
        1.0,
        float(config.RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS),
    )
    while (remaining := deadline - monotonic_clock()) > 0:
        if stop_event is not None and stop_event.is_set():
            return False
        wait_seconds = min(remaining, heartbeat_interval)
        if stop_event is None:
            await sleep(wait_seconds)
        else:
            sleep_task = asyncio.create_task(sleep(wait_seconds))
            stop_task = asyncio.create_task(stop_event.wait())
            try:
                done, _ = await asyncio.wait({sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
                if stop_task in done:
                    return False
                await sleep_task
            finally:
                sleep_task.cancel(); stop_task.cancel()
                await asyncio.gather(sleep_task, stop_task, return_exceptions=True)
        snapshot = await _heartbeat_with_budget(coordinator, owner_id=owner_id, fencing_epoch=fencing_epoch, config=config)
        _record_proof(config, snapshot)
    return True

async def run_resident_tick_scheduler(
    *,
    coordinator: SchedulerLeaseCoordinator | None = None,
    owner_id: str | None = None,
    tick_runner: Callable[[], Awaitable[schemas.ResidentSlotTickRead]] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    monotonic_clock: Callable[[], float] = monotonic,
    process_lock: SchedulerProcessLock | None = None,
    ready_path: str | None = None,
    stop_event: asyncio.Event | None = None,
    drain_timeout_seconds: float | None = None,
    state_listener: SchedulerStateListener | None = None,
    config: Settings = settings,
    session_factory: Callable[[], Any] | None = None,
) -> None:
    resolved_session_factory = session_factory or SessionLocal
    lease_coordinator = SchedulerLeaseExecutor(lambda: coordinator or _coordinator(config, resolved_session_factory))
    run_tick = tick_runner or (lambda: _tick_once(config, resolved_session_factory))
    lease_owner_id = owner_id or f"scheduler-{uuid4()}"
    lock = process_lock or SchedulerProcessLock(config.RESIDENT_TICK_PROCESS_LOCK_PATH)
    readiness = Path(ready_path or config.RESIDENT_TICK_READY_PATH)
    stop = stop_event or asyncio.Event()
    lease = None
    primary_error: BaseException | None = None
    recovering = True
    backoff = 1.0
    drain_timeout = config.resident_tick_shutdown_drain_seconds if drain_timeout_seconds is None else max(0.1, drain_timeout_seconds)

    def observe(state: str) -> None:
        if state != "ready":
            _clear_proof(config); readiness.unlink(missing_ok=True)
        if state_listener is not None: state_listener(state)

    async def pause() -> None:
        nonlocal backoff
        try:
            await asyncio.wait_for(stop.wait(), timeout=backoff)
        except TimeoutError:
            pass
        backoff = min(10.0, backoff * 2)

    try:
        with lock:
            while not stop.is_set():
                try:
                    if lease is None:
                        lease = await lease_coordinator.call("acquire", owner_id=lease_owner_id)
                    if stop.is_set(): break
                    if recovering:
                        # A snapshot alone is not readiness: verify a live heartbeat
                        # before resuming, or acquire a new epoch after expiry.
                        lease = await _heartbeat_with_budget(lease_coordinator, owner_id=lease_owner_id,
                            fencing_epoch=lease.fencing_epoch, config=config, proof=lease)
                        if stop.is_set(): break
                        _record_proof(config, lease)
                        readiness.parent.mkdir(parents=True, exist_ok=True)
                        readiness.write_text(f"state=ready\nowner={lease_owner_id}\nepoch={lease.fencing_epoch}\n", encoding="utf-8")
                        observe("ready"); recovering = False; backoff = 1.0
                    permit = await lease_coordinator.call("begin_tick", owner_id=lease_owner_id, fencing_epoch=lease.fencing_epoch)
                    if stop.is_set(): break
                    if permit.should_run:
                        result_kind, tick_error = SchedulerTickResult.NO_ACTION, None
                        try:
                            result = await _run_fenced_tick_with_heartbeat(coordinator=lease_coordinator, owner_id=lease_owner_id,
                                fencing_epoch=lease.fencing_epoch, tick_runner=run_tick, sleep=sleep, stop_event=stop,
                                drain_timeout_seconds=drain_timeout_seconds, config=config)
                            result_kind = SchedulerTickResult.SUCCESS if result.started_count else SchedulerTickResult.NO_ACTION
                        except SchedulerShutdownDrainTimeout as exc:
                            if exc.pending_tasks:
                                raise
                            logger.warning("scheduler_tick_failed code=%s", type(exc).__name__)
                            result_kind, tick_error = SchedulerTickResult.FAILED, type(exc).__name__
                        except (asyncio.CancelledError, SchedulerLeaseLostError, SqliteBusyRetryExhausted,
                                SqliteTaskQueueFull, SchedulerHeartbeatDeadlineExceeded):
                            raise
                        except Exception as exc:
                            # Even a non-lease primary failure may leave a child
                            # that did not honor cancellation. Do not finish the
                            # window or start another tick while it is alive.
                            if getattr(exc, "pending_tasks", ()):
                                raise
                            logger.warning("scheduler_tick_failed code=%s", type(exc).__name__)
                            result_kind, tick_error = SchedulerTickResult.FAILED, type(exc).__name__
                        # A failed finish never causes this completed tick to rerun:
                        # begin_tick's committed logical window is retained.
                        lease = await lease_coordinator.call("finish_tick", owner_id=lease_owner_id, fencing_epoch=lease.fencing_epoch,
                            result=result_kind, error_code=tick_error)
                    if stop.is_set(): break
                    if not await _sleep_until_next_tick_with_heartbeat(coordinator=lease_coordinator, owner_id=lease_owner_id,
                        fencing_epoch=lease.fencing_epoch, duration_seconds=config.resident_tick_interval_seconds, sleep=sleep,
                        monotonic_clock=monotonic_clock, stop_event=stop, config=config): break
                except (SqliteBusyRetryExhausted, SqliteTaskQueueFull, SchedulerHeartbeatDeadlineExceeded) as exc:
                    if getattr(exc, "pending_tasks", ()):
                        raise
                    # Keep the last successful heartbeat for the recovery margin,
                    # but remove its public readiness proof before draining.
                    lease = _scheduler_proofs.get(config.RESIDENT_TICK_READY_PATH, lease)
                    observe("degraded"); recovering = True
                    logger.warning("scheduler_recovery code=%s owner=%s epoch=%s backoff_seconds=%s",
                        type(exc).__name__, lease_owner_id, lease.fencing_epoch if lease else None, backoff)
                    if not await lease_coordinator.drain(drain_timeout):
                        raise SchedulerShutdownDrainTimeout("scheduler_lease_work_not_settled") from exc
                    if not stop.is_set(): await pause()
                except (SchedulerLeaseLostError, SchedulerLeaseHeldError) as exc:
                    if getattr(exc, "pending_tasks", ()):
                        raise
                    observe("degraded"); recovering = True; lease = None
                    logger.warning("scheduler_recovery code=%s owner=%s backoff_seconds=%s", type(exc).__name__, lease_owner_id, backoff)
                    if not await lease_coordinator.drain(drain_timeout):
                        raise SchedulerShutdownDrainTimeout("scheduler_lease_work_not_settled") from exc
                    if not stop.is_set(): await pause()
    except BaseException as exc:
        primary_error = exc
        observe("draining" if isinstance(exc, asyncio.CancelledError) else "failed")
        raise
    finally:
        _clear_proof(config); readiness.unlink(missing_ok=True)
        settled = await lease_coordinator.drain(drain_timeout)
        children = getattr(primary_error, "pending_tasks", ())
        if children:
            _, unfinished = await asyncio.wait(children, timeout=drain_timeout)
            for child in children:
                child.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            settled = settled and not unfinished
        cleanup_error = None
        if settled and lease is not None:
            try:
                await lease_coordinator.call("release", owner_id=lease_owner_id, fencing_epoch=lease.fencing_epoch)
            except SchedulerLeaseLostError:
                logger.warning("scheduler_cleanup code=lease_transferred owner=%s epoch=%s", lease_owner_id, lease.fencing_epoch)
            except BaseException as exc:
                cleanup_error = exc
                logger.warning("scheduler_cleanup_failed code=%s primary_code=%s owner=%s epoch=%s",
                    type(exc).__name__, type(primary_error).__name__ if primary_error else None, lease_owner_id, lease.fencing_epoch)
        lease_coordinator.close()
        if not settled and primary_error is None:
            observe("failed")
            raise SchedulerShutdownDrainTimeout("scheduler_lease_work_not_settled")
        if cleanup_error is not None and primary_error is None:
            observe("failed")
            raise cleanup_error
        if primary_error is None: observe("stopped")


# Content-free proof consumed by health; expires even when an event loop stalls.
_scheduler_proofs: dict[str, Any] = {}


async def _heartbeat_with_budget(coordinator, *, owner_id, fencing_epoch, config, proof=None):
    """Share one deadline from first queue admission through bounded DB retries.

    Timeout of this wait is recoverable only after the executor's real work has
    drained. An unrelated TimeoutError from inside the operation stays fatal.
    """
    started = monotonic()
    deadline = started + 2.0
    proof = _scheduler_proofs.get(config.RESIDENT_TICK_READY_PATH, proof)
    if proof is not None:
        if (proof.lease_expires_at is None or proof.lease_owner_id != owner_id
                or proof.fencing_epoch != fencing_epoch):
            raise SchedulerLeaseLostError("scheduler_heartbeat_proof_mismatch")
        expiry = proof.lease_expires_at.replace(tzinfo=UTC)
        remaining_lease = (expiry - datetime.now(UTC)).total_seconds()
        if remaining_lease <= 0:
            raise SchedulerLeaseLostError("scheduler_heartbeat_proof_expired")
        safe_seconds = remaining_lease - config.resident_tick_shutdown_drain_seconds - 1
        deadline = min(deadline, started + safe_seconds)
    if deadline <= monotonic():
        raise SchedulerHeartbeatDeadlineExceeded("scheduler_heartbeat_safety_margin")
    # asyncio's timeout clock is loop.time(); convert from the same monotonic
    # clock used by the executor/writer without assuming identical epochs.
    timeout = asyncio.timeout(max(0.0, deadline - monotonic()))
    try:
        async with timeout:
            for attempt, delay in enumerate((0.0, 0.05, 0.1)):
                if delay:
                    await asyncio.sleep(delay)  # No transaction survives a retry.
                try:
                    return await lease_call(coordinator, "heartbeat", owner_id=owner_id,
                        fencing_epoch=fencing_epoch, queue_deadline=deadline)
                except SqliteBusyRetryExhausted:
                    if proof is None or attempt == 2:
                        raise
    except TimeoutError as exc:
        if not timeout.expired():
            raise
        raise SchedulerHeartbeatDeadlineExceeded("scheduler_heartbeat_wait_deadline") from exc
    except SqliteWriteDeadlineExceeded as exc:
        raise SchedulerHeartbeatDeadlineExceeded("scheduler_heartbeat_writer_deadline") from exc

def _record_proof(config: Settings, lease: Any) -> None:
    _scheduler_proofs[config.RESIDENT_TICK_READY_PATH] = lease

def _clear_proof(config: Settings) -> None:
    _scheduler_proofs.pop(config.RESIDENT_TICK_READY_PATH, None)

def scheduler_is_ready(config: Settings) -> bool:
    proof = _scheduler_proofs.get(config.RESIDENT_TICK_READY_PATH)
    return proof is not None and proof.lease_expires_at is not None and proof.lease_expires_at > datetime.now(UTC)
