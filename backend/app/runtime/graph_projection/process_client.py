from __future__ import annotations

import threading
from typing import Any, Protocol

from app.config import Settings, settings
from app.domains.relationships.ports.projection import (
    RelationshipProjectionBackendError,
    RelationshipProjectionPort,
)
from app.integrations.ladybug_projection import LadybugRelationshipProjection


class ProcessGraphClient(RelationshipProjectionPort, Protocol):
    """Projection/query client owned by the in-process projector lifecycle."""

    def verify_connectivity(self) -> None: ...

    def bootstrap(self) -> None: ...

    def run_template(
        self,
        template: Any,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...


_process_client_lock = threading.RLock()
_process_graph_client: ProcessGraphClient | None = None


def register_process_graph_client(client: ProcessGraphClient) -> None:
    """Publish the single backend's graph connection for concurrent reads.

    LadybugDB permits the projector and query paths to share one in-process
    ``Database`` instance, but a second database owner cannot open the same
    store while the writer lock is held.  The ER4 projector therefore owns the
    connection and publishes only a borrowed process-local reference.
    """

    global _process_graph_client
    with _process_client_lock:
        if (
            _process_graph_client is not None
            and _process_graph_client is not client
        ):
            raise RelationshipProjectionBackendError(
                "graph_process_client_already_registered"
            )
        _process_graph_client = client


def unregister_process_graph_client(client: ProcessGraphClient) -> None:
    """Remove the borrowed reference before its lifecycle owner closes it."""

    global _process_graph_client
    with _process_client_lock:
        if _process_graph_client is client:
            _process_graph_client = None


def borrow_process_graph_client(
    config: Settings = settings,
) -> ProcessGraphClient | None:
    """Borrow, but never transfer ownership of, the in-process graph client."""

    if (
        config.LOCAL_RUNTIME_COMPONENT_MODE != "in_process"
        or config.graph_provider != "ladybug"
    ):
        return None
    with _process_client_lock:
        return _process_graph_client


def graph_client_from_settings(
    config: Settings = settings,
    *,
    require_enabled: bool = True,
) -> RelationshipProjectionPort:
    if require_enabled and not config.graph_projection_enabled:
        raise RelationshipProjectionBackendError("graph_disabled")
    if config.graph_provider != "ladybug":
        raise RelationshipProjectionBackendError("graph_provider_unsupported")
    return LadybugRelationshipProjection(
        database_root=config.ladybug_database_root,
    )


__all__ = [
    "ProcessGraphClient",
    "borrow_process_graph_client",
    "graph_client_from_settings",
    "register_process_graph_client",
    "unregister_process_graph_client",
]
