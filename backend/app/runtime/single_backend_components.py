from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import threading
from functools import partial
from typing import Any

from app.compatibility.runtime.single_backend_workers import (
    run_legacy_projector_component,
    run_legacy_scheduler_component,
)
from app.core.config import Settings, settings
from app.domains.runtime.public import (
    ComponentObservationRegistry,
    RuntimeComponentState,
    RuntimeDiagnosticCode,
    SchedulerLeaseHeldError,
    SchedulerLeaseLostError,
    component_observations,
)


logger = logging.getLogger(__name__)

ComponentStateListener = Callable[[str], None]
SchedulerRunner = Callable[
    [asyncio.Event, ComponentStateListener], Awaitable[None]
]
ProjectorRunner = Callable[[threading.Event, ComponentStateListener], None]


class SingleBackendRuntimeStartupError(RuntimeError):
    """Content-free startup failure safe for logs and diagnostics."""


class SingleBackendRuntimeComponents:
    """Own scheduler and projector lifecycles inside one FastAPI process.

    Domain behavior remains in the existing reviewed workers. This runtime
    component owns startup, shutdown, and privacy-safe observations only.
    """

    def __init__(
        self,
        *,
        scheduler_runner: SchedulerRunner = run_legacy_scheduler_component,
        projector_runner: ProjectorRunner = run_legacy_projector_component,
        startup_timeout_seconds: float | None = None,
        shutdown_timeout_seconds: float | None = None,
        scheduler_restart_delay_seconds: float = 1.0,
        registry: ComponentObservationRegistry = component_observations,
    ) -> None:
        self._scheduler_runner = scheduler_runner
        self._projector_runner = projector_runner
        self._startup_timeout_seconds = max(
            0.1,
            startup_timeout_seconds
            if startup_timeout_seconds is not None
            else settings.LOCAL_RUNTIME_COMPONENT_STARTUP_TIMEOUT_SECONDS,
        )
        self._shutdown_timeout_seconds = max(
            0.1,
            shutdown_timeout_seconds
            if shutdown_timeout_seconds is not None
            else settings.LOCAL_RUNTIME_COMPONENT_SHUTDOWN_TIMEOUT_SECONDS,
        )
        self._scheduler_restart_delay_seconds = max(
            0.0, scheduler_restart_delay_seconds
        )
        self._registry = registry
        self._scheduler_stop: asyncio.Event | None = None
        self._projector_stop: threading.Event | None = None
        self._scheduler_task: asyncio.Task[None] | None = None
        self._projector_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._scheduler_task is not None or self._projector_task is not None:
            raise SingleBackendRuntimeStartupError("component_runtime_already_started")

        loop = asyncio.get_running_loop()
        scheduler_started = asyncio.Event()
        projector_started = asyncio.Event()
        self._scheduler_stop = asyncio.Event()
        self._projector_stop = threading.Event()
        self._registry.reset()
        self._registry.update("scheduler", RuntimeComponentState.RUNNING)
        self._registry.update("projector", RuntimeComponentState.RUNNING)

        def scheduler_listener(state: str) -> None:
            self._observe_scheduler_state(state)
            if state in {"ready", "degraded"}:
                scheduler_started.set()

        def projector_listener(state: str) -> None:
            loop.call_soon_threadsafe(self._observe_projector_state, state)
            if state in {"ready", "degraded"}:
                loop.call_soon_threadsafe(projector_started.set)

        self._scheduler_task = asyncio.create_task(
            self._run_scheduler(self._scheduler_stop, scheduler_listener),
            name="angmoo-in-process-scheduler",
        )
        self._projector_task = asyncio.create_task(
            asyncio.to_thread(
                self._run_projector,
                self._projector_stop,
                projector_listener,
            ),
            name="angmoo-in-process-projector",
        )
        try:
            await asyncio.gather(
                self._wait_started(
                    "scheduler", scheduler_started, self._scheduler_task
                ),
                self._wait_started(
                    "projector", projector_started, self._projector_task
                ),
            )
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        if self._scheduler_stop is not None:
            self._scheduler_stop.set()
        if self._projector_stop is not None:
            self._projector_stop.set()
        tasks = tuple(
            task
            for task in (self._scheduler_task, self._projector_task)
            if task is not None
        )
        if tasks:
            _, pending = await asyncio.wait(
                tasks,
                timeout=self._shutdown_timeout_seconds,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if self._scheduler_task in pending:
                self._registry.update(
                    "scheduler",
                    RuntimeComponentState.FAILED,
                    reason_code=RuntimeDiagnosticCode.SCHEDULER_LEASE_LOST,
                )
            if self._projector_task in pending:
                self._registry.update(
                    "projector",
                    RuntimeComponentState.FAILED,
                    reason_code=RuntimeDiagnosticCode.PROJECTOR_STALLED,
                )
        self._scheduler_task = None
        self._projector_task = None
        self._scheduler_stop = None
        self._projector_stop = None

    async def _wait_started(
        self,
        name: str,
        started: asyncio.Event,
        task: asyncio.Task[None],
    ) -> None:
        wait_task = asyncio.create_task(started.wait())
        try:
            done, _ = await asyncio.wait(
                {wait_task, task},
                timeout=self._startup_timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                raise SingleBackendRuntimeStartupError(
                    f"{name}_component_start_timeout"
                )
            if task in done:
                error = task.exception()
                if error is not None:
                    raise SingleBackendRuntimeStartupError(
                        f"{name}_component_start_failed"
                    ) from error
                raise SingleBackendRuntimeStartupError(
                    f"{name}_component_stopped_during_start"
                )
        finally:
            wait_task.cancel()
            await asyncio.gather(wait_task, return_exceptions=True)

    async def _run_scheduler(
        self,
        stop_event: asyncio.Event,
        listener: ComponentStateListener,
    ) -> None:
        while True:
            try:
                await self._scheduler_runner(stop_event, listener)
            except SchedulerLeaseHeldError:
                self._registry.update(
                    "scheduler",
                    RuntimeComponentState.FAILED,
                    reason_code=RuntimeDiagnosticCode.SCHEDULER_DUPLICATE_ACTIVE,
                )
                raise
            except SchedulerLeaseLostError:
                # A Windows sleep can advance the database clock beyond the
                # lease TTL before the event loop can heartbeat.  The former
                # standalone container recovered because its restart policy
                # relaunched the worker.  Preserve the same behavior after
                # moving the worker into the FastAPI lifespan: expose the
                # bounded failure, then acquire a fresh fencing epoch without
                # replaying missed ticks.
                self._registry.update(
                    "scheduler",
                    RuntimeComponentState.FAILED,
                    reason_code=RuntimeDiagnosticCode.SCHEDULER_LEASE_LOST,
                )
                if stop_event.is_set():
                    return
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=self._scheduler_restart_delay_seconds,
                    )
                except TimeoutError:
                    continue
                return
            except asyncio.CancelledError:
                self._registry.update("scheduler", RuntimeComponentState.STOPPED)
                raise
            except Exception:
                logger.exception("in-process scheduler component failed")
                self._registry.update(
                    "scheduler",
                    RuntimeComponentState.FAILED,
                    reason_code=RuntimeDiagnosticCode.SCHEDULER_LEASE_LOST,
                )
                raise
            else:
                self._registry.update("scheduler", RuntimeComponentState.STOPPED)
                return

    def _run_projector(
        self,
        stop_event: threading.Event,
        listener: ComponentStateListener,
    ) -> None:
        try:
            self._projector_runner(stop_event, listener)
        except Exception:
            logger.exception("in-process projector component failed")
            self._registry.update(
                "projector",
                RuntimeComponentState.FAILED,
                reason_code=RuntimeDiagnosticCode.PROJECTOR_STALLED,
            )
            raise
        else:
            self._registry.update("projector", RuntimeComponentState.STOPPED)

    def _observe_scheduler_state(self, state: str) -> None:
        mapping = {
            "ready": (RuntimeComponentState.READY, None),
            "draining": (RuntimeComponentState.RUNNING, None),
            "stopped": (RuntimeComponentState.STOPPED, None),
            "duplicate": (
                RuntimeComponentState.FAILED,
                RuntimeDiagnosticCode.SCHEDULER_DUPLICATE_ACTIVE,
            ),
            "failed": (
                RuntimeComponentState.FAILED,
                RuntimeDiagnosticCode.SCHEDULER_LEASE_LOST,
            ),
        }
        component_state, reason = mapping.get(
            state,
            (
                RuntimeComponentState.DEGRADED,
                RuntimeDiagnosticCode.SCHEDULER_LEASE_LOST,
            ),
        )
        self._registry.update("scheduler", component_state, reason_code=reason)

    def _observe_projector_state(self, state: str) -> None:
        mapping = {
            "ready": (RuntimeComponentState.READY, None),
            "degraded": (
                RuntimeComponentState.DEGRADED,
                RuntimeDiagnosticCode.GRAPH_DEGRADED,
            ),
            "stopped": (RuntimeComponentState.STOPPED, None),
            "failed": (
                RuntimeComponentState.FAILED,
                RuntimeDiagnosticCode.PROJECTOR_STALLED,
            ),
        }
        component_state, reason = mapping.get(
            state,
            (
                RuntimeComponentState.DEGRADED,
                RuntimeDiagnosticCode.GRAPH_DEGRADED,
            ),
        )
        self._registry.update("projector", component_state, reason_code=reason)


def create_single_backend_runtime_components(
    config: Settings = settings,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> SingleBackendRuntimeComponents | None:
    if config.LOCAL_RUNTIME_COMPONENT_MODE != "in_process":
        return None
    if session_factory is None:
        return SingleBackendRuntimeComponents()
    return SingleBackendRuntimeComponents(
        scheduler_runner=partial(
            run_legacy_scheduler_component,
            config=config,
            session_factory=session_factory,
        ),
        projector_runner=partial(
            run_legacy_projector_component,
            config=config,
            session_factory=session_factory,
        ),
        startup_timeout_seconds=(
            config.LOCAL_RUNTIME_COMPONENT_STARTUP_TIMEOUT_SECONDS
        ),
        shutdown_timeout_seconds=(
            config.LOCAL_RUNTIME_COMPONENT_SHUTDOWN_TIMEOUT_SECONDS
        ),
    )


__all__ = [
    "SingleBackendRuntimeComponents",
    "SingleBackendRuntimeStartupError",
    "create_single_backend_runtime_components",
]
