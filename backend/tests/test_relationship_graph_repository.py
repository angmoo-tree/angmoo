from __future__ import annotations

from datetime import UTC, datetime
import time

from neo4j.exceptions import ClientError
from neo4j.time import DateTime as Neo4jDateTime
import pytest

from app.integrations.neo4j import (
    GraphClientError,
    GraphQueryTemplate,
    Neo4jGraphClient,
)
from app.integrations.relationship_graph_read import RelationshipGraphRepository


def _relationship(actor: str, target: str, *, version: int = 2):
    return {
        "actor_id": actor,
        "target_id": target,
        "relationship": {
            "world_id": "world-a",
            "relationship_state_id": f"relationship-{actor}-{target}",
            "familiarity": 4,
            "affinity": 2,
            "trust": 1,
            "tension": 0,
            "interaction_count": 2,
            "relationship_version": version,
        },
    }


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    def run_template(self, template, parameters):
        self.calls.append((template, parameters))
        if template == GraphQueryTemplate.DIRECT_RELATIONSHIP:
            return [_relationship(parameters["source_id"], parameters["target_id"])]
        if template == GraphQueryTemplate.SHARED_NEIGHBORS_EITHER:
            return [{"world_character_id": f"shared-{index}"} for index in range(40)]
        if template == GraphQueryTemplate.VISUALIZATION_1:
            return [_relationship("actor", f"target-{index}") for index in range(4)]
        return []


def test_direct_relationship_keeps_direction_and_uses_bound_parameters() -> None:
    executor = FakeExecutor()
    repository = RelationshipGraphRepository(executor)
    source = "actor' MATCH (n) DETACH DELETE n //"
    hits = repository.get_direct_relationship(
        world_id="world-a",
        source_world_character_id=source,
        target_world_character_id="target",
        include_reverse=True,
    )
    assert [(hit.actor_world_character_id, hit.target_world_character_id) for hit in hits] == [
        (source, "target"),
        ("target", source),
    ]
    assert all(call[0] == GraphQueryTemplate.DIRECT_RELATIONSHIP for call in executor.calls)
    assert executor.calls[0][1]["source_id"] == source


def test_query_result_caps_are_enforced_in_repository() -> None:
    executor = FakeExecutor()
    repository = RelationshipGraphRepository(executor)
    shared = repository.list_shared_neighbors(
        world_id="world-a",
        source_world_character_id="actor",
        target_world_character_id="target",
        direction_mode="either",
        limit=999,
    )
    neighborhood = repository.get_visualization_neighborhood(
        world_id="world-a",
        source_world_character_id="actor",
        depth=1,
        node_limit=2,
        edge_limit=2,
    )
    assert len(shared) == 30
    assert executor.calls[0][1]["limit"] == 30
    assert len(neighborhood.nodes) <= 2
    assert len(neighborhood.edges) <= 2
    assert neighborhood.truncated is True


def test_neo4j_temporal_values_are_normalized_to_native_datetimes() -> None:
    occurred_at = datetime(2026, 8, 13, 4, 5, 6, tzinfo=UTC)

    class TemporalExecutor:
        def run_template(self, template, parameters):
            if template == GraphQueryTemplate.DIRECT_RELATIONSHIP:
                row = _relationship("actor", "target")
                row["relationship"]["last_event_at"] = Neo4jDateTime.from_native(
                    occurred_at
                )
                row["relationship"]["updated_at"] = Neo4jDateTime.from_native(
                    occurred_at
                )
                return [row]
            if template == GraphQueryTemplate.RELATIONSHIP_EVIDENCE:
                return [
                    {
                        "event_id": "event-1",
                        "event_type": "reply_created",
                        "occurred_at": Neo4jDateTime.from_native(occurred_at),
                        "relationship_state_id": "relationship-actor-target",
                        "relationship_version": 2,
                    }
                ]
            return []

    repository = RelationshipGraphRepository(TemporalExecutor())
    relationship = repository.get_direct_relationship(
        world_id="world-a",
        source_world_character_id="actor",
        target_world_character_id="target",
    )[0]
    evidence = repository.list_relationship_evidence(
        world_id="world-a",
        source_world_character_id="actor",
        target_world_character_id="target",
    )[0]

    assert type(relationship.last_event_at) is datetime
    assert relationship.last_event_at == occurred_at
    assert type(relationship.updated_at) is datetime
    assert relationship.updated_at == occurred_at
    assert type(evidence.occurred_at) is datetime
    assert evidence.occurred_at == occurred_at


def test_neo4j_server_timeout_is_classified_as_query_timeout() -> None:
    client = object.__new__(Neo4jGraphClient)
    error = ClientError("transaction timed out")
    error._neo4j_code = "Neo.ClientError.Transaction.TransactionTimedOut"
    mapped = client._mapped_error(error)
    assert mapped.error_class == "neo4j_query_timeout"


def test_neo4j_client_timeout_returns_without_waiting_for_query_thread() -> None:
    client = object.__new__(Neo4jGraphClient)

    def slow_execute(*args, **kwargs):
        time.sleep(0.25)
        return []

    client._execute = slow_execute
    started = time.monotonic()
    with pytest.raises(GraphClientError) as captured:
        client._bounded_execute(
            "RETURN 1",
            {},
            server_timeout_seconds=1.5,
            client_timeout_seconds=0.01,
        )
    elapsed = time.monotonic() - started
    assert captured.value.error_class == "neo4j_query_timeout"
    assert elapsed < 0.15
