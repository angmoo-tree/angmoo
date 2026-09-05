from __future__ import annotations

import asyncio
from collections.abc import Callable
import socket
import threading
from typing import Any, Protocol

from app.config import Settings, settings
from app.core.db import SessionLocal
from app.domains.relationships.ports.projection import (
    RelationshipProjectionBackendError,
)
from app.runtime.graph_projection.process_client import (
    borrow_process_graph_client,
    graph_client_from_settings,
    register_process_graph_client,
    unregister_process_graph_client,
)
from app.runtime.graph_projection.worker import GraphProjectionWorker
from app.runtime.resident.scheduler import run_resident_tick_scheduler


ComponentStateListener = Callable[[str], None]


class ClosableProjectionStore(Protocol):
    def verify_connectivity(self) -> None: ...

    def bootstrap(self) -> None: ...

    def close(self) -> None: ...


def borrow_runtime_graph_client(config: Settings) -> ClosableProjectionStore | None:
    """Expose the process-owned graph client through the runtime boundary."""

    return borrow_process_graph_client(config)


async def run_scheduler_component(
    stop_event: asyncio.Event,
    state_listener: ComponentStateListener,
    *,
    config: Settings = settings,
    session_factory: Callable[[], Any] = SessionLocal,
) -> None:
    """Run the scheduler as an in-process backend component."""

    await run_resident_tick_scheduler(
        stop_event=stop_event,
        state_listener=state_listener,
        config=config,
        session_factory=session_factory,
    )


def run_projector_component(
    stop_event: threading.Event,
    state_listener: ComponentStateListener,
    *,
    config: Settings = settings,
    session_factory: Callable[[], Any] = SessionLocal,
) -> None:
    """Run the outbox projector as an in-process backend component."""

    while not stop_event.is_set():
        client: ClosableProjectionStore | None = None
        client_registered = False
        try:
            client = graph_client_from_settings(config)
            client.verify_connectivity()
            client.bootstrap()
            register_process_graph_client(client)
            client_registered = True
            worker_id = config.graph_projector_worker_id or (
                f"in-process-{socket.gethostname()}-{threading.get_native_id()}"
            )
            worker = GraphProjectionWorker(
                session_factory=session_factory,
                store=client,
                worker_id=worker_id,
                batch_size=config.graph_projector_batch_size,
                concurrency=config.graph_projector_concurrency,
                command_timeout_seconds=(
                    config.graph_projector_command_timeout_seconds
                ),
                shutdown_drain_seconds=(
                    config.graph_projector_shutdown_drain_seconds
                ),
            )
            state_listener("ready")
            worker.run_loop(
                poll_interval_seconds=config.graph_projector_poll_interval_seconds,
                stop_event=stop_event,
                connectivity_probe=client.verify_connectivity,
                state_listener=state_listener,
            )
            return
        except RelationshipProjectionBackendError:
            state_listener("degraded")
            if stop_event.wait(config.graph_projector_poll_interval_seconds):
                return
        finally:
            if client is not None:
                if client_registered:
                    unregister_process_graph_client(client)
                client.close()


__all__ = [
    "borrow_runtime_graph_client",
    "run_projector_component",
    "run_scheduler_component",
]
