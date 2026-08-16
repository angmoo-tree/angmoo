from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from time import monotonic
from types import TracebackType
from typing import Awaitable, Callable
from uuid import uuid4

from app import schemas
from app.core.config import settings
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


class SchedulerProcessLockHeld(RuntimeError):
    pass


class SchedulerProcessLock:
    """Best-effort same-filesystem lock; PostgreSQL remains the authority."""

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


def _coordinator() -> SchedulerLeaseCoordinator:
    if (
        settings.RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS
        >= settings.RESIDENT_TICK_LEASE_TTL_SECONDS
    ):
        raise ValueError(
            "RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS must be shorter than "
            "RESIDENT_TICK_LEASE_TTL_SECONDS"
        )
    return SchedulerLeaseCoordinator(
        SqlAlchemySchedulerLeaseRepository(SessionLocal),
        ttl_seconds=settings.RESIDENT_TICK_LEASE_TTL_SECONDS,
        interval_seconds=settings.resident_tick_interval_seconds,
    )


async def _tick_once() -> schemas.ResidentSlotTickRead:
    with SessionLocal() as db:
        transition = agent_runs.reconcile_all_elapsed_routines(db)
        if transition.completed or transition.skipped:
            logger.info(
                "elapsed routines reconciled completed=%s skipped=%s",
                transition.completed,
                transition.skipped,
            )
        return await agent_runs.tick_resident_slots(
            db,
            schemas.ResidentSlotTickCreate(
                post_id=settings.resident_tick_post_id,
                max_runs=settings.resident_tick_max_runs,
                timeout_seconds=settings.openclaw_timeout_seconds,
            ),
        )


async def _run_fenced_tick_with_heartbeat(
    *,
    coordinator: SchedulerLeaseCoordinator,
    owner_id: str,
    fencing_epoch: int,
    tick_runner: Callable[[], Awaitable[schemas.ResidentSlotTickRead]],
    sleep: Callable[[float], Awaitable[None]],
) -> schemas.ResidentSlotTickRead:
    async def run_tick() -> schemas.ResidentSlotTickRead:
        with scheduler_fence(owner_id=owner_id, fencing_epoch=fencing_epoch):
            return await tick_runner()

    async def heartbeat() -> None:
        while True:
            await sleep(settings.RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS)
            coordinator.heartbeat(owner_id=owner_id, fencing_epoch=fencing_epoch)

    tick_task = asyncio.create_task(run_tick())
    heartbeat_task = asyncio.create_task(heartbeat())
    done, _ = await asyncio.wait(
        {tick_task, heartbeat_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if heartbeat_task in done:
        error = heartbeat_task.exception()
        tick_task.cancel()
        await asyncio.gather(tick_task, return_exceptions=True)
        if error is not None:
            raise error
        raise SchedulerLeaseLostError("scheduler heartbeat stopped unexpectedly")
    heartbeat_task.cancel()
    await asyncio.gather(heartbeat_task, return_exceptions=True)
    return tick_task.result()


async def _sleep_until_next_tick_with_heartbeat(
    *,
    coordinator: SchedulerLeaseCoordinator,
    owner_id: str,
    fencing_epoch: int,
    duration_seconds: float,
    sleep: Callable[[float], Awaitable[None]],
    monotonic_clock: Callable[[], float] = monotonic,
) -> None:
    deadline = monotonic_clock() + max(0.0, duration_seconds)
    heartbeat_interval = max(
        1.0,
        float(settings.RESIDENT_TICK_HEARTBEAT_INTERVAL_SECONDS),
    )
    while (remaining := deadline - monotonic_clock()) > 0:
        wait_seconds = min(remaining, heartbeat_interval)
        await sleep(wait_seconds)
        coordinator.heartbeat(owner_id=owner_id, fencing_epoch=fencing_epoch)


async def run_resident_tick_scheduler(
    *,
    coordinator: SchedulerLeaseCoordinator | None = None,
    owner_id: str | None = None,
    tick_runner: Callable[[], Awaitable[schemas.ResidentSlotTickRead]] = _tick_once,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    monotonic_clock: Callable[[], float] = monotonic,
    process_lock: SchedulerProcessLock | None = None,
    ready_path: str | None = None,
) -> None:
    lease_coordinator = coordinator or _coordinator()
    lease_owner_id = owner_id or f"scheduler-{uuid4()}"
    lock = process_lock or SchedulerProcessLock(
        settings.RESIDENT_TICK_PROCESS_LOCK_PATH
    )
    readiness = Path(ready_path or settings.RESIDENT_TICK_READY_PATH)
    lease = None

    with lock:
        try:
            lease = lease_coordinator.acquire(owner_id=lease_owner_id)
            readiness.parent.mkdir(parents=True, exist_ok=True)
            readiness.write_text(
                f"owner={lease_owner_id}\nepoch={lease.fencing_epoch}\n",
                encoding="utf-8",
            )
            logger.info(
                "resident scheduler lease acquired owner=%s epoch=%s",
                lease_owner_id,
                lease.fencing_epoch,
            )
            while True:
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
                            tick_runner=tick_runner,
                            sleep=sleep,
                        )
                    except asyncio.CancelledError:
                        raise
                    except SchedulerLeaseLostError:
                        raise
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
                await _sleep_until_next_tick_with_heartbeat(
                    coordinator=lease_coordinator,
                    owner_id=lease_owner_id,
                    fencing_epoch=lease.fencing_epoch,
                    duration_seconds=settings.resident_tick_interval_seconds,
                    sleep=sleep,
                    monotonic_clock=monotonic_clock,
                )
        except SchedulerLeaseHeldError:
            logger.error("resident scheduler duplicate rejected")
            raise
        except SchedulerLeaseLostError:
            logger.exception("resident scheduler lease lost")
            raise
        finally:
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
