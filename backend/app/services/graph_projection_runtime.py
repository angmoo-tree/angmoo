from __future__ import annotations

from app.core.config import Settings, settings
from app.integrations.neo4j import GraphClientError, Neo4jGraphClient


def graph_client_from_settings(
    config: Settings = settings,
    *,
    require_enabled: bool = True,
) -> Neo4jGraphClient:
    if require_enabled and not config.graph_projection_enabled:
        raise GraphClientError("graph_disabled")
    password = config.neo4j_password
    if not password:
        raise GraphClientError("neo4j_auth_invalid")
    return Neo4jGraphClient(
        uri=config.neo4j_uri,
        username=config.neo4j_username,
        password=password,
        database=config.neo4j_database,
    )
