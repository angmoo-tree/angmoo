from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.ladybug_projection import LadybugRelationshipProjection
from app.services import social_memory_read
from app.services.graph_projection_commands import build_projection_command
from app.services.graph_projection_replay import create_replay_run
from app.services.graph_projection_runtime import (
    register_process_graph_client,
    unregister_process_graph_client,
)
from app.services.relationship_graph_read import (
    RelationshipGraphForbiddenError,
    get_owner_relationship_graph,
)
from p7_graph_support import seed_projection_fixture, sqlite_engine


def test_owner_read_falls_back_to_directional_canonical_when_graph_disabled() -> None:
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
    assert result.meta.source == "canonical_fallback"
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

def test_failed_world_rebuild_falls_back_to_canonical_as_unavailable() -> None:
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
            config=Settings(GRAPH_PROJECTION_ENABLED=True),
        )
    assert result.meta.source == "canonical_fallback"
    assert result.meta.graph_status == "unavailable"
    assert result.meta.fallback_reason == "graph_rebuild_failed"
    assert len(result.edges) == 1


def test_ladybug_reads_projection_and_recovers_from_lock(
    tmp_path: Path,
) -> None:
    engine = sqlite_engine()
    database_root = tmp_path / "ladybug-ui"
    config = Settings(
        GRAPH_PROJECTION_ENABLED=True,
        LADYBUG_DATABASE_ROOT=str(database_root),
    )
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="ladybug-ui")
        command = build_projection_command(db, outbox_id=fixture.outbox.id)
        world_id = fixture.world.id
        character_id = fixture.actor.id
        owner = fixture.owner

    with LadybugRelationshipProjection(database_root=database_root) as projection:
        assert projection.apply(command) == "applied"

    with Session(engine, expire_on_commit=False) as db:
        healthy = get_owner_relationship_graph(
            db,
            character_id=character_id,
            world_id=world_id,
            user=owner,
            config=config,
            graph_provider="ladybug",
        )
    assert healthy.meta.source == "ladybug"
    assert len(healthy.edges) == 1
    assert len(healthy.evidence) == 1
    assert healthy.evidence[0].root_post_id == "p7-root-ladybug-ui"
    assert healthy.evidence[0].source_post_id == "p7-reply-ladybug-ui"

    with LadybugRelationshipProjection(database_root=database_root):
        with Session(engine, expire_on_commit=False) as db:
            degraded = get_owner_relationship_graph(
                db,
                character_id=character_id,
                world_id=world_id,
                user=owner,
                config=config,
                graph_provider="ladybug",
            )
    assert degraded.meta.source == "canonical_fallback"
    assert degraded.meta.graph_status == "unavailable"
    assert degraded.meta.fallback_reason == "ladybug_writer_lock_unavailable"
    assert len(degraded.edges) == 1

    with Session(engine, expire_on_commit=False) as db:
        recovered = get_owner_relationship_graph(
            db,
            character_id=character_id,
            world_id=world_id,
            user=owner,
            config=config,
            graph_provider="ladybug",
        )
    assert recovered.meta.source == "ladybug"
    assert len(recovered.edges) == 1


def test_in_process_projector_connection_is_shared_with_graph_and_p6_reads(
    tmp_path: Path,
) -> None:
    engine = sqlite_engine()
    database_root = tmp_path / "ladybug-in-process"
    config = Settings(
        GRAPH_PROJECTION_ENABLED=True,
        LADYBUG_DATABASE_ROOT=str(database_root),
        LOCAL_RUNTIME_COMPONENT_MODE="in_process",
    )
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="in-process")
        command = build_projection_command(db, outbox_id=fixture.outbox.id)
        world_id = fixture.world.id
        character_id = fixture.actor.id
        owner = fixture.owner

    with LadybugRelationshipProjection(database_root=database_root) as projection:
        assert projection.apply(command) == "applied"
        register_process_graph_client(projection)
        try:
            with Session(engine, expire_on_commit=False) as db:
                graph = get_owner_relationship_graph(
                    db,
                    character_id=character_id,
                    world_id=world_id,
                    user=owner,
                    config=config,
                    graph_provider="ladybug",
                )
                diagnostics = social_memory_read.get_owner_diagnostics(
                    db,
                    character_id=character_id,
                    world_id=world_id,
                    user=owner,
                    config=config,
                )
            assert graph.meta.source == "ladybug"
            assert len(graph.edges) == 1
            assert diagnostics.relationship_graph_status == "lagging"
            assert diagnostics.latest_relationship_version_parity is True
            projection.verify_connectivity()
        finally:
            unregister_process_graph_client(projection)


def test_obsolete_preview_flag_cannot_disable_canonical_ladybug_provider(
    tmp_path: Path,
) -> None:
    engine = sqlite_engine()
    config = Settings(
        GRAPH_PROJECTION_ENABLED=True,
        LADYBUG_GRAPH_PREVIEW_ENABLED=False,
        LADYBUG_DATABASE_ROOT=str(tmp_path / "disabled-preview"),
    )
    with Session(engine, expire_on_commit=False) as db:
        fixture = seed_projection_fixture(db, suffix="ladybug-disabled")
        result = get_owner_relationship_graph(
            db,
            character_id=fixture.actor.id,
            world_id=fixture.world.id,
            user=fixture.owner,
            config=config,
            graph_provider="ladybug",
        )

    assert result.meta.source == "ladybug"
    assert result.meta.graph_status == "lagging"
    assert result.meta.fallback_reason is None
    assert config.ladybug_database_root.exists()
