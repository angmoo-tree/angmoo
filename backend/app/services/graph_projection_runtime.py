from __future__ import annotations

import threading
from typing import Any, Protocol

from app.core.config import Settings, settings
from app.domains.relationships.ports.projection import RelationshipProjectionPort
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.integrations.neo4j import GraphClientError, Neo4jGraphClient


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
            raise GraphClientError("graph_process_client_already_registered")
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
        or not config.ladybug_graph_preview_enabled
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
        raise GraphClientError("graph_disabled")
    if config.ladybug_graph_preview_enabled:
        return LadybugRelationshipProjection(
            database_root=config.ladybug_database_root,
        )
    password = config.neo4j_password
    if not password:
        raise GraphClientError("neo4j_auth_invalid")
    return Neo4jGraphClient(
        uri=config.neo4j_uri,
        username=config.neo4j_username,
        password=password,
        database=config.neo4j_database,
    )


__all__ = [
    "ProcessGraphClient",
    "borrow_process_graph_client",
    "graph_client_from_settings",
    "register_process_graph_client",
    "unregister_process_graph_client",
]
