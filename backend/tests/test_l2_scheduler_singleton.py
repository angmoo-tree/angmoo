from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.domains.runtime.public import (
    SchedulerFenceRejectedError,
    SchedulerLeaseCoordinator,
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
    SchedulerTickPermit,
    SchedulerTickResult,
    SqlAlchemySchedulerLeaseRepository,
    decide_tick_window,
    scheduler_fence,
)
from app.services import resident_tick_scheduler


def _repository() -> tuple[SqlAlchemySchedulerLeaseRepository, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.User.__table__.create(engine)
    models.InstallationIdentity.__table__.create(engine)
    models.RuntimeSchedulerLease.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(
            models.InstallationIdentity(
                singleton_key="local-installation",
                installation_id="installation-l2-test",
                bootstrap_state="unclaimed",
            )
        )
        db.commit()
    return SqlAlchemySchedulerLeaseRepository(factory), factory


def test_scheduler_lease_rejects_duplicate_and_fences_stale_owner() -> None:
    repository, factory = _repository()
    first = repository.acquire(owner_id="owner-a", ttl_seconds=30)
    assert first.fencing_epoch == 1

    with pytest.raises(SchedulerLeaseHeldError):
        repository.acquire(owner_id="owner-b", ttl_seconds=30)

    with factory() as db:
        row = db.get(models.RuntimeSchedulerLease, "resident-tick-scheduler")
        assert row is not None
        row.lease_expires_at = datetime(2000, 1, 1, tzinfo=UTC)
        db.commit()

    second = repository.acquire(owner_id="owner-b", ttl_seconds=30)
    assert second.fencing_epoch == 2
    with pytest.raises(SchedulerLeaseLostError):
        repository.heartbeat(
            owner_id="owner-a",
            fencing_epoch=first.fencing_epoch,
            ttl_seconds=30,
        )
    with factory() as db, scheduler_fence(
        owner_id="owner-a",
        fencing_epoch=first.fencing_epoch,
    ):
        with pytest.raises(SchedulerFenceRejectedError):
            db.commit()


def test_tick_window_skips_forward_catchup_and_backward_duplicates() -> None:
    previous = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)
    forward = decide_tick_window(
        now=datetime(2026, 8, 16, 9, 17, 42, tzinfo=UTC),
        interval_seconds=60,
        last_tick_window_at=previous,
        last_observed_at=previous,
    )
    assert forward.should_run is True
    assert forward.logical_window_at == datetime(2026, 8, 16, 9, 17, tzinfo=UTC)
    assert forward.observed_gap_seconds == 29_862

    backward = decide_tick_window(
        now=datetime(2026, 8, 16, 0, 59, 59, tzinfo=UTC),
        interval_seconds=60,
        last_tick_window_at=previous,
        last_observed_at=previous,
    )
    assert backward.should_run is False
    assert backward.observed_gap_seconds == 0


def test_scheduler_process_lock_rejects_second_local_loop(tmp_path: Path) -> None:
    lock_path = tmp_path / "resident-scheduler.lock"
    first = resident_tick_scheduler.SchedulerProcessLock(str(lock_path))
    with first:
        with pytest.raises(resident_tick_scheduler.SchedulerProcessLockHeld):
            with resident_tick_scheduler.SchedulerProcessLock(str(lock_path)):
                raise AssertionError("second scheduler process lock must not be entered")

    with resident_tick_scheduler.SchedulerProcessLock(str(lock_path)):
        pass
    assert lock_path.read_text(encoding="ascii") == str(os.getpid())


class _FakeCoordinator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def acquire(self, *, owner_id: str):
        self.calls.append(f"acquire:{owner_id}")
        return SimpleNamespace(fencing_epoch=7)

    def begin_tick(self, *, owner_id: str, fencing_epoch: int):
        self.calls.append(f"begin:{owner_id}:{fencing_epoch}")
        return SchedulerTickPermit(
            should_run=True,
            logical_window_at=datetime(2026, 8, 16, tzinfo=UTC),
            next_tick_at=datetime(2026, 8, 16, 0, 1, tzinfo=UTC),
            observed_gap_seconds=0,
        )

    def heartbeat(self, *, owner_id: str, fencing_epoch: int):
        self.calls.append(f"heartbeat:{owner_id}:{fencing_epoch}")

    def finish_tick(
        self,
        *,
        owner_id: str,
        fencing_epoch: int,
        result: SchedulerTickResult,
        error_code: str | None = None,
    ):
        self.calls.append(f"finish:{result.value}:{error_code}")

    def release(self, *, owner_id: str, fencing_epoch: int):
        self.calls.append(f"release:{owner_id}:{fencing_epoch}")


class _NullProcessLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None


def test_scheduler_readiness_exists_only_while_lease_is_held(tmp_path: Path) -> None:
    coordinator = _FakeCoordinator()
    ready = tmp_path / "scheduler-ready"
    sleep_call_count = 0

    async def tick_runner():
        assert ready.exists()
        return SimpleNamespace(started_count=0)

    async def sleep(seconds: float) -> None:
        nonlocal sleep_call_count
        sleep_call_count += 1
        if sleep_call_count > 1:
            raise asyncio.CancelledError
        await asyncio.Event().wait()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            resident_tick_scheduler.run_resident_tick_scheduler(
                coordinator=coordinator,  # type: ignore[arg-type]
                owner_id="owner-test",
                tick_runner=tick_runner,  # type: ignore[arg-type]
                sleep=sleep,
                process_lock=_NullProcessLock(),  # type: ignore[arg-type]
                ready_path=str(ready),
            )
        )

    assert not ready.exists()
    assert coordinator.calls == [
        "acquire:owner-test",
        "begin:owner-test:7",
        "finish:no_action:None",
        "release:owner-test:7",
    ]


def test_wait_between_ticks_keeps_lease_alive() -> None:
    coordinator = _FakeCoordinator()
    sleeps: list[float] = []
    clock = [0.0]

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    asyncio.run(
        resident_tick_scheduler._sleep_until_next_tick_with_heartbeat(
            coordinator=coordinator,  # type: ignore[arg-type]
            owner_id="owner-test",
            fencing_epoch=7,
            duration_seconds=25,
            sleep=sleep,
            monotonic_clock=lambda: clock[0],
        )
    )

    assert sleeps == [10.0, 10.0, 5.0]
    assert coordinator.calls == [
        "heartbeat:owner-test:7",
        "heartbeat:owner-test:7",
        "heartbeat:owner-test:7",
    ]


def test_sleep_wake_gap_does_not_replay_missed_intervals() -> None:
    coordinator = _FakeCoordinator()
    sleeps: list[float] = []
    clock = [0.0]

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += 3_600

    asyncio.run(
        resident_tick_scheduler._sleep_until_next_tick_with_heartbeat(
            coordinator=coordinator,  # type: ignore[arg-type]
            owner_id="owner-test",
            fencing_epoch=7,
            duration_seconds=60,
            sleep=sleep,
            monotonic_clock=lambda: clock[0],
        )
    )

    assert sleeps == [10.0]
    assert coordinator.calls == ["heartbeat:owner-test:7"]


def test_shutdown_before_first_tick_releases_lease_without_claiming_work(
    tmp_path: Path,
) -> None:
    coordinator = _FakeCoordinator()
    stop = asyncio.Event()
    stop.set()

    asyncio.run(
        resident_tick_scheduler.run_resident_tick_scheduler(
            coordinator=coordinator,  # type: ignore[arg-type]
            owner_id="owner-stop-before-tick",
            stop_event=stop,
            process_lock=_NullProcessLock(),  # type: ignore[arg-type]
            ready_path=str(tmp_path / "scheduler-ready"),
        )
    )

    assert coordinator.calls == [
        "acquire:owner-stop-before-tick",
        "release:owner-stop-before-tick:7",
    ]


def test_shutdown_during_tick_drains_then_releases_without_second_tick(
    tmp_path: Path,
) -> None:
    coordinator = _FakeCoordinator()

    async def scenario() -> None:
        stop = asyncio.Event()
        tick_started = asyncio.Event()
        finish_tick = asyncio.Event()

        async def tick_runner():
            tick_started.set()
            await finish_tick.wait()
            return SimpleNamespace(started_count=1)

        task = asyncio.create_task(
            resident_tick_scheduler.run_resident_tick_scheduler(
                coordinator=coordinator,  # type: ignore[arg-type]
                owner_id="owner-drain",
                tick_runner=tick_runner,  # type: ignore[arg-type]
                stop_event=stop,
                drain_timeout_seconds=1.0,
                process_lock=_NullProcessLock(),  # type: ignore[arg-type]
                ready_path=str(tmp_path / "scheduler-ready"),
            )
        )
        await tick_started.wait()
        stop.set()
        finish_tick.set()
        await task

    asyncio.run(scenario())

    assert coordinator.calls == [
        "acquire:owner-drain",
        "begin:owner-drain:7",
        "finish:success:None",
        "release:owner-drain:7",
    ]


def test_shutdown_drain_timeout_cancels_tick_and_releases_lease(
    tmp_path: Path,
) -> None:
    coordinator = _FakeCoordinator()

    async def scenario() -> None:
        stop = asyncio.Event()
        tick_started = asyncio.Event()

        async def tick_runner():
            tick_started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(
            resident_tick_scheduler.run_resident_tick_scheduler(
                coordinator=coordinator,  # type: ignore[arg-type]
                owner_id="owner-timeout",
                tick_runner=tick_runner,  # type: ignore[arg-type]
                stop_event=stop,
                drain_timeout_seconds=0.01,
                process_lock=_NullProcessLock(),  # type: ignore[arg-type]
                ready_path=str(tmp_path / "scheduler-ready"),
            )
        )
        await tick_started.wait()
        stop.set()
        await task

    asyncio.run(scenario())

    assert coordinator.calls == [
        "acquire:owner-timeout",
        "begin:owner-timeout:7",
        "finish:failed:SchedulerShutdownDrainTimeout",
        "release:owner-timeout:7",
    ]
