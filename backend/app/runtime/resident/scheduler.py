from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from time import monotonic
from types import TracebackType
from typing import Awaitable, Callable, Any
from uuid import uuid4

from app.domains.routines import schemas
from app.runtime.routines.lifecycle_references import SqlAlchemyLifecycleReferences

from app.config import Settings, settings
from app.core.db import SessionLocal
from app.domains.runtime.public import (
    SchedulerLeaseCoordinator,
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
    SchedulerTickResult,
    SqlAlchemySchedulerLeaseRepository,
    scheduler_fence,
)
from app.services import agent_runs


logger = logging.getLogger(__name__)
SchedulerStateListener = Callable[[str], None]


class SchedulerShutdownDrainTimeout(RuntimeError):
    pass


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
    return SchedulerLeaseCoordinator(
        SqlAlchemySchedulerLeaseRepository(resolved_session_factory),
        ttl_seconds=config.RESIDENT_TICK_LEASE_TTL_SECONDS,
        interval_seconds=config.resident_tick_interval_seconds,
    )


async def _tick_once(
    config: Settings = settings,
    session_factory: Callable[[], Any] | None = None,
) -> schemas.ResidentSlotTickRead:
    resolved_session_factory = session_factory or SessionLocal
    with resolved_session_factory() as db:
        transition = agent_runs.reconcile_all_elapsed_routines(
            db, references=SqlAlchemyLifecycleReferences(db)
        )
        if transition.completed or transition.skipped:
            logger.info(
                "elapsed routines reconciled completed=%s skipped=%s",
                transition.completed,
                transition.skipped,
            )
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
    async def run_tick() -> schemas.ResidentSlotTickRead:
        with scheduler_fence(owner_id=owner_id, fencing_epoch=fencing_epoch):
            return await tick_runner()

    async def heartbeat() -> None:
        while True:
            await sleep(config.RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS)
            coordinator.heartbeat(owner_id=owner_id, fencing_epoch=fencing_epoch)

    tick_task = asyncio.create_task(run_tick())
    heartbeat_task = asyncio.create_task(heartbeat())
    stop_task = (
        asyncio.create_task(stop_event.wait()) if stop_event is not None else None
    )
    watched = {tick_task, heartbeat_task}
    if stop_task is not None:
        watched.add(stop_task)
    done, _ = await asyncio.wait(
        watched,
        return_when=asyncio.FIRST_COMPLETED,
    )
    if heartbeat_task in done:
        error = heartbeat_task.exception()
        tick_task.cancel()
        await asyncio.gather(tick_task, return_exceptions=True)
        if error is not None:
            raise error
        raise SchedulerLeaseLostError("scheduler heartbeat stopped unexpectedly")
    if stop_task is not None and stop_task in done and tick_task not in done:
        timeout = (
            config.resident_tick_shutdown_drain_seconds
            if drain_timeout_seconds is None
            else max(0.1, drain_timeout_seconds)
        )
        done, _ = await asyncio.wait(
            {tick_task, heartbeat_task},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat_task in done:
            error = heartbeat_task.exception()
            tick_task.cancel()
            await asyncio.gather(tick_task, return_exceptions=True)
            if error is not None:
                raise error
            raise SchedulerLeaseLostError("scheduler heartbeat stopped unexpectedly")
        if tick_task not in done:
            tick_task.cancel()
            await asyncio.gather(tick_task, return_exceptions=True)
            raise SchedulerShutdownDrainTimeout(
                "resident scheduler tick exceeded shutdown drain timeout"
            )
    heartbeat_task.cancel()
    if stop_task is not None:
        stop_task.cancel()
    await asyncio.gather(
        heartbeat_task,
        *([stop_task] if stop_task is not None else []),
        return_exceptions=True,
    )
    return tick_task.result()


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
            done, _ = await asyncio.wait(
                {sleep_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done:
                sleep_task.cancel()
                await asyncio.gather(sleep_task, return_exceptions=True)
                return False
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
            await sleep_task
        coordinator.heartbeat(owner_id=owner_id, fencing_epoch=fencing_epoch)
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
    lease_coordinator = coordinator or _coordinator(
        config,
        resolved_session_factory,
    )
    run_tick = tick_runner or (
        lambda: _tick_once(config, resolved_session_factory)
    )
    lease_owner_id = owner_id or f"scheduler-{uuid4()}"
    lock = process_lock or SchedulerProcessLock(
        config.RESIDENT_TICK_PROCESS_LOCK_PATH
    )
    readiness = Path(ready_path or config.RESIDENT_TICK_READY_PATH)
    stop = stop_event or asyncio.Event()
    lease = None

    with lock:
        try:
            lease = lease_coordinator.acquire(owner_id=lease_owner_id)
            readiness.parent.mkdir(parents=True, exist_ok=True)
            readiness.write_text(
                "state=ready\n"
                f"owner={lease_owner_id}\nepoch={lease.fencing_epoch}\n",
                encoding="utf-8",
            )
            logger.info(
                "resident scheduler lease acquired owner=%s epoch=%s",
                lease_owner_id,
                lease.fencing_epoch,
            )
            if state_listener is not None:
                state_listener("ready")
            while not stop.is_set():
                permit = lease_coordinator.begin_tick(
                    owner_id=lease_owner_id,
                    fencing_epoch=lease.fencing_epoch,
                )
                if permit.should_run:
                    try:
                        result = await _run_fenced_tick_with_heartbeat(
                            coordinator=lease_coordinator,
                            owner_id=lease_owner_id,
                            fencing_epoch=lease.fencing_epoch,
                            tick_runner=run_tick,
                            sleep=sleep,
                            stop_event=stop,
                            drain_timeout_seconds=drain_timeout_seconds,
                            config=config,
                        )
                    except asyncio.CancelledError:
                        raise
                    except SchedulerLeaseLostError:
                        raise
                    except SchedulerShutdownDrainTimeout as exc:
                        logger.warning("resident scheduler bounded drain timed out")
                        lease_coordinator.finish_tick(
                            owner_id=lease_owner_id,
                            fencing_epoch=lease.fencing_epoch,
                            result=SchedulerTickResult.FAILED,
                            error_code=type(exc).__name__,
                        )
                        break
                    except Exception as exc:
                        logger.exception("resident scheduler tick failed")
                        lease_coordinator.finish_tick(
                            owner_id=lease_owner_id,
                            fencing_epoch=lease.fencing_epoch,
                            result=SchedulerTickResult.FAILED,
                            error_code=type(exc).__name__,
                        )
                    else:
                        lease_coordinator.finish_tick(
                            owner_id=lease_owner_id,
                            fencing_epoch=lease.fencing_epoch,
                            result=(
                                SchedulerTickResult.SUCCESS
                                if result.started_count
                                else SchedulerTickResult.NO_ACTION
                            ),
                        )
                else:
                    lease_coordinator.heartbeat(
                        owner_id=lease_owner_id,
                        fencing_epoch=lease.fencing_epoch,
                    )
                if stop.is_set():
                    break
                completed_wait = await _sleep_until_next_tick_with_heartbeat(
                    coordinator=lease_coordinator,
                    owner_id=lease_owner_id,
                    fencing_epoch=lease.fencing_epoch,
                    duration_seconds=config.resident_tick_interval_seconds,
                    sleep=sleep,
                    monotonic_clock=monotonic_clock,
                    stop_event=stop,
                    config=config,
                )
                if not completed_wait:
                    break
        except SchedulerLeaseHeldError:
            if state_listener is not None:
                state_listener("duplicate")
            logger.error("resident scheduler duplicate rejected")
            raise
        except SchedulerLeaseLostError:
            if state_listener is not None:
                state_listener("failed")
            logger.exception("resident scheduler lease lost")
            raise
        finally:
            if lease is not None and stop.is_set() and readiness.exists():
                if state_listener is not None:
                    state_listener("draining")
                readiness.write_text(
                    "state=draining\n"
                    f"owner={lease_owner_id}\nepoch={lease.fencing_epoch}\n",
                    encoding="utf-8",
                )
            readiness.unlink(missing_ok=True)
            if lease is not None:
                try:
                    lease_coordinator.release(
                        owner_id=lease_owner_id,
                        fencing_epoch=lease.fencing_epoch,
                    )
                except SchedulerLeaseLostError:
                    logger.warning(
                        "resident scheduler lease already transferred owner=%s epoch=%s",
                        lease_owner_id,
                        lease.fencing_epoch,
                    )
            if state_listener is not None:
                state_listener("stopped")
