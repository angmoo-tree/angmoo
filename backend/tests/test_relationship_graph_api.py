from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.graph_projection_replay import create_replay_run
from app.services.relationship_graph_read import (
    RelationshipGraphForbiddenError,
    get_owner_relationship_graph,
)
from p7_graph_support import seed_projection_fixture, sqlite_engine


def test_owner_read_falls_back_to_directional_postgres_when_graph_disabled() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db)
        result = get_owner_relationship_graph(
            db,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            user=fixture.owner,
            config=Settings(GRAPH_PROJECTION_ENABLED=False),
        )
    assert result.meta.source == "postgres_fallback"
    assert result.meta.graph_status == "disabled"
    assert result.meta.fallback_reason == "graph_disabled"
    assert len(result.edges) == 1
    assert result.edges[0].actor_world_character_id == fixture.actor_world_character.id
    assert result.edges[0].target_world_character_id == fixture.target_world_character.id
    assert {node.display_name for node in result.nodes} == {"Mango", "Sage"}


def test_other_owner_cannot_read_character_graph() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="forbidden")
        with pytest.raises(RelationshipGraphForbiddenError):
            get_owner_relationship_graph(
                db,
                character_id=fixture.actor.id,
                world_id=fixture.world.id,
                user=fixture.other_owner,
                config=Settings(GRAPH_PROJECTION_ENABLED=False),
            )

def test_failed_world_rebuild_falls_back_to_postgres_as_unavailable() -> None:
    engine = sqlite_engine()
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="failed-rebuild")
        run = create_replay_run(
            db,
            world_id=fixture.world.id,
            mode="world_rebuild",
            source_event_id=None,
            requested_by="local-maintainer",
            reason_code="verify_failed_rebuild_fallback",
        )
        run.status = "failed"
        run.last_error_class = "replay_parity_mismatch"
        db.commit()
        result = get_owner_relationship_graph(
            db,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            user=fixture.owner,
            config=Settings(
                GRAPH_PROJECTION_ENABLED=True,
                NEO4J_PASSWORD="local-test-only",
            ),
        )
    assert result.meta.source == "postgres_fallback"
    assert result.meta.graph_status == "unavailable"
    assert result.meta.fallback_reason == "graph_rebuild_failed"
    assert len(result.edges) == 1
