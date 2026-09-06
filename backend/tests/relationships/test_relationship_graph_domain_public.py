from __future__ import annotations
import app.domains.relationships.service.graph_read as relationships_service_graph_read

from sqlalchemy.orm import Session

from app.runtime.graph_projection.relationship_graph_read import (
    SqlAlchemyRelationshipGraphReadGateway,
)
from app.config import Settings

from app.domains.relationships.exceptions import (GraphReadBackendError)
from p7_graph_support import seed_projection_fixture, sqlite_engine


def test_domain_public_read_preserves_canonical_fallback_contract() -> None:
    engine = sqlite_engine()
    config = Settings(GRAPH_PROJECTION_ENABLED=False)
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="domain-public")
        result = relationships_service_graph_read.get_owner_relationship_graph(
            SqlAlchemyRelationshipGraphReadGateway(db, config=config),
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            owner_id=fixture.owner.id,
            graph_projection_enabled=config.graph_projection_enabled,
        )

    import app.domains.relationships.schemas as relationships
    assert isinstance(result, relationships.RelationshipGraphRead)
    assert result.meta.source == "canonical_fallback"
    assert result.meta.graph_status == "disabled"
    assert result.meta.fallback_reason == "graph_disabled"
    assert len(result.edges) == 1


def test_domain_public_read_maps_ladybug_schema_error_to_fallback(
    monkeypatch,
) -> None:
    engine = sqlite_engine()
    config = Settings(GRAPH_PROJECTION_ENABLED=True)
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="domain-auth-fallback")
        gateway = SqlAlchemyRelationshipGraphReadGateway(db, config=config)
        monkeypatch.setattr(
            gateway,
            "open_graph_repository",
            lambda: (_ for _ in ()).throw(GraphReadBackendError("schema_not_ready")),
        )
        result = relationships_service_graph_read.get_owner_relationship_graph(
            gateway,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            owner_id=fixture.owner.id,
            graph_projection_enabled=config.graph_projection_enabled,
        )

    assert result.meta.source == "canonical_fallback"
    assert result.meta.graph_status == "misconfigured"
    assert result.meta.fallback_reason == "schema_not_ready"
