from __future__ import annotations

from app.core.config import Settings, settings
from app.domains.relationships.ports.projection import RelationshipProjectionPort
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.integrations.neo4j import GraphClientError, Neo4jGraphClient


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
