from __future__ import annotations

from datetime import UTC, datetime
import os
from uuid import uuid4

import pytest

from app.core.config import settings
from app.integrations.neo4j import Neo4jGraphClient
from app.integrations.relationship_graph_read import RelationshipGraphRepository
from app.services.graph_projection_replay import projection_digest
from app.services.graph_projection_commands import (
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)


pytestmark = pytest.mark.skipif(
    os.getenv("P7_NEO4J_INTEGRATION") != "1",
    reason="set P7_NEO4J_INTEGRATION=1 for the local Neo4j integration test",
)


def _event(
    *,
    world_id: str,
    event_id: str,
    actor_id: str,
    actor_character_id: str,
    target_id: str,
    target_character_id: str,
) -> SocialEventProjectionCommand:
    return SocialEventProjectionCommand(
        world_id=world_id,
        event_id=event_id,
        event_type="reply_created",
        occurred_at=datetime(2026, 8, 12, 3, 0, tzinfo=UTC),
        schema_version="social-event-v1",
        actor_world_character_id=actor_id,
        actor_character_id=actor_character_id,
        target_world_character_id=target_id,
        target_character_id=target_character_id,
    )


def _relationship(
    *,
    event: SocialEventProjectionCommand,
    state_id: str,
    version: int,
    affinity: int,
) -> RelationshipStateProjectionCommand:
    return RelationshipStateProjectionCommand(
        event=event,
        relationship_state_id=state_id,
        familiarity=5,
        affinity=affinity,
        trust=3,
        tension=1,
        interaction_count=4,
        last_event_id=event.event_id,
        last_event_at=event.occurred_at,
        updated_at=event.occurred_at,
        relationship_version=version,
    )


def test_real_neo4j_projection_direction_version_exclusion_and_world_isolation() -> None:
    password = settings.neo4j_password
    assert password is not None
    client = Neo4jGraphClient(
        uri=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=password,
        database=settings.neo4j_database,
    )
    suffix = uuid4().hex
    world_id = f"p7-it-world-{suffix}"
    other_world_id = f"p7-it-other-world-{suffix}"
    actor_id = f"p7-it-actor-{suffix}"
    target_id = f"p7-it-target-{suffix}"
    event_ab = _event(
        world_id=world_id,
        event_id=f"p7-it-event-ab-{suffix}",
        actor_id=actor_id,
        actor_character_id=f"p7-it-character-a-{suffix}",
        target_id=target_id,
        target_character_id=f"p7-it-character-b-{suffix}",
    )
    event_ba = _event(
        world_id=world_id,
        event_id=f"p7-it-event-ba-{suffix}",
        actor_id=target_id,
        actor_character_id=f"p7-it-character-b-{suffix}",
        target_id=actor_id,
        target_character_id=f"p7-it-character-a-{suffix}",
    )
    repository = RelationshipGraphRepository(client)
    try:
        client.verify_connectivity()
        client.bootstrap()
        relationship_ab = _relationship(
            event=event_ab,
            state_id=f"p7-it-state-ab-{suffix}",
            version=2,
            affinity=7,
        )
        relationship_ba = _relationship(
            event=event_ba,
            state_id=f"p7-it-state-ba-{suffix}",
            version=3,
            affinity=-2,
        )
        assert client.apply(relationship_ab, timeout_seconds=10.0) == "applied"
        assert client.apply(relationship_ba, timeout_seconds=10.0) == "applied"
        assert client.world_digest(world_id) == projection_digest(
            [relationship_ab, relationship_ba]
        )

        directions = repository.get_direct_relationship(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
            include_reverse=True,
        )
        assert [
            (hit.actor_world_character_id, hit.target_world_character_id)
            for hit in directions
        ] == [(actor_id, target_id), (target_id, actor_id)]
        assert [hit.relationship_version for hit in directions] == [2, 3]
        assert [hit.affinity for hit in directions] == [7, -2]

        before_stale_digest = client.world_digest(world_id)
        stale = _relationship(
            event=event_ab,
            state_id=f"p7-it-state-ab-{suffix}",
            version=1,
            affinity=99,
        )
        assert client.apply(stale, timeout_seconds=10.0) == "stale_noop"
        current = repository.get_direct_relationship(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        assert current[0].relationship_version == 2
        assert current[0].affinity == 7
        assert client.world_digest(world_id) == before_stale_digest

        assert repository.get_direct_relationship(
            world_id=other_world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        ) == []
        evidence = repository.list_relationship_evidence(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        assert [item.event_id for item in evidence] == [event_ab.event_id]

        exclusion = SourceExclusionProjectionCommand(
            world_id=world_id,
            event_id=event_ab.event_id,
            reason="source_hidden",
        )
        assert client.apply(exclusion, timeout_seconds=10.0) == "removed"
        assert client.world_digest(world_id) == projection_digest(
            [relationship_ab, relationship_ba, exclusion]
        )
        assert repository.list_relationship_evidence(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        ) == []
        remaining = repository.get_direct_relationship(
            world_id=world_id,
            source_world_character_id=actor_id,
            target_world_character_id=target_id,
        )
        assert remaining[0].relationship_version == 2
    finally:
        client.clear_world(world_id)
        client.clear_world(other_world_id)
        client.close()
