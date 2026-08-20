from __future__ import annotations

import asyncio
from collections.abc import Callable
import socket
import threading
from typing import Protocol

from app.core.config import settings
from app.core.db import SessionLocal
from app.domains.relationships.ports.projection import (
    RelationshipProjectionBackendError,
)
from app.services.graph_projection_runtime import graph_client_from_settings
from app.services.graph_projection_worker import GraphProjectionWorker
from app.services.resident_tick_scheduler import run_resident_tick_scheduler


ComponentStateListener = Callable[[str], None]


class ClosableProjectionStore(Protocol):
    def verify_connectivity(self) -> None: ...

    def bootstrap(self) -> None: ...

    def close(self) -> None: ...


async def run_legacy_scheduler_component(
    stop_event: asyncio.Event,
    state_listener: ComponentStateListener,
) -> None:
    """Run the L2 scheduler unchanged under the ER4 lifespan owner."""

    await run_resident_tick_scheduler(
        stop_event=stop_event,
        state_listener=state_listener,
    )


def run_legacy_projector_component(
    stop_event: threading.Event,
    state_listener: ComponentStateListener,
) -> None:
    """Run the current outbox projector under the ER4 lifespan owner."""

    while not stop_event.is_set():
        client: ClosableProjectionStore | None = None
        try:
            client = graph_client_from_settings()
            client.verify_connectivity()
            client.bootstrap()
            worker_id = settings.graph_projector_worker_id or (
                f"in-process-{socket.gethostname()}-{threading.get_native_id()}"
            )
            worker = GraphProjectionWorker(
                session_factory=SessionLocal,
                store=client,
                worker_id=worker_id,
                batch_size=settings.graph_projector_batch_size,
                concurrency=settings.graph_projector_concurrency,
                command_timeout_seconds=(
                    settings.graph_projector_command_timeout_seconds
                ),
                shutdown_drain_seconds=(
                    settings.graph_projector_shutdown_drain_seconds
                ),
            )
            state_listener("ready")
            worker.run_loop(
                poll_interval_seconds=settings.graph_projector_poll_interval_seconds,
                stop_event=stop_event,
                connectivity_probe=client.verify_connectivity,
                state_listener=state_listener,
            )
            return
        except RelationshipProjectionBackendError:
            state_listener("degraded")
            if stop_event.wait(settings.graph_projector_poll_interval_seconds):
                return
        finally:
            if client is not None:
                client.close()


__all__ = [
    "run_legacy_projector_component",
    "run_legacy_scheduler_component",
]
