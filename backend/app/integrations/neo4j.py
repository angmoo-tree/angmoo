from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any
import time

from neo4j import GraphDatabase, Query
from neo4j.exceptions import (
    AuthError,
    ClientError,
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)

from app.services.graph_projection_metrics import graph_metrics
from app.domains.relationships.ports.projection import (
    RelationshipProjectionBackendError,
)
from app.domains.relationships.graph_read.repository import GraphQueryTemplate
from app.domains.relationships.projection.commands import (
    NoGraphMutationCommand,
    ProjectionCommand,
    RelationshipStateProjectionCommand,
    SocialEventProjectionCommand,
    SourceExclusionProjectionCommand,
)


class GraphClientError(RelationshipProjectionBackendError):
    """Backward-compatible Neo4j error under the provider-neutral contract."""


_BOOTSTRAP_QUERIES = (
    "CREATE CONSTRAINT p7_world_id_unique IF NOT EXISTS "
    "FOR (n:World) REQUIRE n.world_id IS UNIQUE",
    "CREATE CONSTRAINT p7_world_character_id_unique IF NOT EXISTS "
    "FOR (n:WorldCharacter) REQUIRE n.world_character_id IS UNIQUE",
    "CREATE CONSTRAINT p7_social_event_id_unique IF NOT EXISTS "
    "FOR (n:SocialEvent) REQUIRE n.event_id IS UNIQUE",
    "CREATE INDEX p7_world_character_scope IF NOT EXISTS "
    "FOR (n:WorldCharacter) ON (n.world_id, n.world_character_id)",
    "CREATE INDEX p7_world_character_character IF NOT EXISTS "
    "FOR (n:WorldCharacter) ON (n.world_id, n.character_id)",
    "CREATE INDEX p7_social_event_occurred IF NOT EXISTS "
    "FOR (n:SocialEvent) ON (n.world_id, n.occurred_at)",
    "CREATE INDEX p7_social_event_type_occurred IF NOT EXISTS "
    "FOR (n:SocialEvent) ON (n.world_id, n.event_type, n.occurred_at)",
)

_EXPECTED_CONSTRAINTS = {
    "p7_world_id_unique",
    "p7_world_character_id_unique",
    "p7_social_event_id_unique",
}
_EXPECTED_INDEXES = {
    "p7_world_character_scope",
    "p7_world_character_character",
    "p7_social_event_occurred",
    "p7_social_event_type_occurred",
}

_EVENT_WITH_TARGET = """
MERGE (world:World {world_id: $world_id})
MERGE (actor:WorldCharacter {world_character_id: $actor_world_character_id})
SET actor.character_id = $actor_character_id, actor.world_id = $world_id
MERGE (target:WorldCharacter {world_character_id: $target_world_character_id})
SET target.character_id = $target_character_id, target.world_id = $world_id
MERGE (event:SocialEvent {event_id: $event_id})
SET event.world_id = $world_id, event.event_type = $event_type,
    event.occurred_at = $occurred_at, event.schema_version = $schema_version
MERGE (actor)-[:MEMBER_OF {world_id: $world_id}]->(world)
MERGE (target)-[:MEMBER_OF {world_id: $world_id}]->(world)
MERGE (actor)-[:PERFORMED {world_id: $world_id}]->(event)
MERGE (event)-[:TARGETED {world_id: $world_id}]->(target)
MERGE (event)-[:OCCURRED_IN {world_id: $world_id}]->(world)
RETURN event.event_id AS event_id
"""

_EVENT_WITHOUT_TARGET = """
MERGE (world:World {world_id: $world_id})
MERGE (actor:WorldCharacter {world_character_id: $actor_world_character_id})
SET actor.character_id = $actor_character_id, actor.world_id = $world_id
MERGE (event:SocialEvent {event_id: $event_id})
SET event.world_id = $world_id, event.event_type = $event_type,
    event.occurred_at = $occurred_at, event.schema_version = $schema_version
MERGE (actor)-[:MEMBER_OF {world_id: $world_id}]->(world)
MERGE (actor)-[:PERFORMED {world_id: $world_id}]->(event)
MERGE (event)-[:OCCURRED_IN {world_id: $world_id}]->(world)
RETURN event.event_id AS event_id
"""

_RELATIONSHIP = """
MERGE (world:World {world_id: $world_id})
MERGE (actor:WorldCharacter {world_character_id: $actor_world_character_id})
SET actor.character_id = $actor_character_id, actor.world_id = $world_id
MERGE (target:WorldCharacter {world_character_id: $target_world_character_id})
SET target.character_id = $target_character_id, target.world_id = $world_id
MERGE (event:SocialEvent {event_id: $event_id})
SET event.world_id = $world_id, event.event_type = $event_type,
    event.occurred_at = $occurred_at, event.schema_version = $schema_version
MERGE (actor)-[:MEMBER_OF {world_id: $world_id}]->(world)
MERGE (target)-[:MEMBER_OF {world_id: $world_id}]->(world)
MERGE (actor)-[:PERFORMED {world_id: $world_id}]->(event)
MERGE (event)-[:TARGETED {world_id: $world_id}]->(target)
MERGE (event)-[:OCCURRED_IN {world_id: $world_id}]->(world)
MERGE (actor)-[relationship:RELATES_TO {world_id: $world_id}]->(target)
WITH actor, target, event, relationship,
     coalesce(relationship.relationship_version, 0) AS existing_version
FOREACH (_ IN CASE WHEN existing_version <= $relationship_version THEN [1] ELSE [] END |
  SET relationship.relationship_state_id = $relationship_state_id,
      relationship.familiarity = $familiarity,
      relationship.affinity = $affinity,
      relationship.trust = $trust,
      relationship.tension = $tension,
      relationship.interaction_count = $interaction_count,
      relationship.last_event_id = $last_event_id,
      relationship.last_event_at = $last_event_at,
      relationship.updated_at = $updated_at,
      relationship.relationship_version = $relationship_version
  MERGE (actor)-[grounded:RELATIONSHIP_GROUNDED_IN {
    world_id: $world_id,
    target_world_character_id: $target_world_character_id,
    relationship_state_id: $relationship_state_id,
    event_id: $event_id
  }]->(event)
  SET grounded.relationship_version = $relationship_version
)
RETURN existing_version, relationship.relationship_version AS relationship_version
"""

_SOURCE_EXCLUSION = """
MATCH (event:SocialEvent {event_id: $event_id, world_id: $world_id})
DETACH DELETE event
RETURN count(event) AS removed_count
"""

_DIRECT = """
MATCH (actor:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
      -[relationship:RELATES_TO {world_id: $world_id}]->
      (target:WorldCharacter {world_character_id: $target_id, world_id: $world_id})
RETURN properties(relationship) AS relationship,
       actor.world_character_id AS actor_id,
       target.world_character_id AS target_id
LIMIT 1
"""

_SHARED_OUTGOING = """
MATCH (left:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
      -[:RELATES_TO {world_id: $world_id}]->
      (shared:WorldCharacter {world_id: $world_id})
MATCH (right:WorldCharacter {world_character_id: $target_id, world_id: $world_id})
      -[:RELATES_TO {world_id: $world_id}]->(shared)
RETURN DISTINCT shared.world_character_id AS world_character_id
ORDER BY world_character_id LIMIT $limit
"""

_SHARED_INCOMING = """
MATCH (shared:WorldCharacter {world_id: $world_id})
      -[:RELATES_TO {world_id: $world_id}]->
      (left:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
MATCH (shared)-[:RELATES_TO {world_id: $world_id}]->
      (right:WorldCharacter {world_character_id: $target_id, world_id: $world_id})
RETURN DISTINCT shared.world_character_id AS world_character_id
ORDER BY world_character_id LIMIT $limit
"""

_SHARED_EITHER = """
MATCH (left:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
      -[:RELATES_TO {world_id: $world_id}]-(shared:WorldCharacter {world_id: $world_id})
MATCH (right:WorldCharacter {world_character_id: $target_id, world_id: $world_id})
      -[:RELATES_TO {world_id: $world_id}]-(shared)
RETURN DISTINCT shared.world_character_id AS world_character_id
ORDER BY world_character_id LIMIT $limit
"""

_RANK_BASE = """
MATCH (source:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
      -[relationship:RELATES_TO {world_id: $world_id}]->
      (target:WorldCharacter {world_id: $world_id})
RETURN properties(relationship) AS relationship,
       source.world_character_id AS actor_id,
       target.world_character_id AS target_id
{order_by}
LIMIT $limit
"""

_EVIDENCE = """
MATCH (actor:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
      -[grounded:RELATIONSHIP_GROUNDED_IN {
        world_id: $world_id,
        target_world_character_id: $target_id
      }]->(event:SocialEvent {world_id: $world_id})
RETURN event.event_id AS event_id, event.event_type AS event_type,
       event.occurred_at AS occurred_at,
       grounded.relationship_state_id AS relationship_state_id,
       grounded.relationship_version AS relationship_version
ORDER BY event.occurred_at DESC, event.event_id DESC
LIMIT $evidence_limit
"""

_VISUALIZATION_1 = """
MATCH (center:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
MATCH (center)-[relationship:RELATES_TO {world_id: $world_id}]-(neighbor:WorldCharacter {world_id: $world_id})
RETURN center.world_character_id AS center_id,
       startNode(relationship).world_character_id AS actor_id,
       endNode(relationship).world_character_id AS target_id,
       properties(relationship) AS relationship
ORDER BY relationship.updated_at DESC, actor_id, target_id
LIMIT $edge_limit
"""

_VISUALIZATION_2 = """
MATCH (center:WorldCharacter {world_character_id: $source_id, world_id: $world_id})
MATCH path=(center)-[:RELATES_TO*1..2]-(neighbor:WorldCharacter {world_id: $world_id})
UNWIND relationships(path) AS relationship
WITH DISTINCT relationship
RETURN $source_id AS center_id,
       startNode(relationship).world_character_id AS actor_id,
       endNode(relationship).world_character_id AS target_id,
       properties(relationship) AS relationship
ORDER BY relationship.updated_at DESC, actor_id, target_id
LIMIT $edge_limit
"""


def _path_query(direction: str, hops: int) -> str:
    if direction == "outgoing":
        pattern = f"-[:RELATES_TO*1..{hops}]->"
    elif direction == "incoming":
        pattern = f"<-[:RELATES_TO*1..{hops}]-"
    else:
        pattern = f"-[:RELATES_TO*1..{hops}]-"
    return f"""
MATCH path=(source:WorldCharacter {{world_character_id: $source_id, world_id: $world_id}})
      {pattern}
      (target:WorldCharacter {{world_character_id: $target_id, world_id: $world_id}})
WHERE all(node IN nodes(path) WHERE node.world_id = $world_id)
  AND all(relationship IN relationships(path) WHERE relationship.world_id = $world_id)
RETURN [node IN nodes(path) | node.world_character_id] AS world_character_ids,
       [relationship IN relationships(path) | {{
         actor_id: startNode(relationship).world_character_id,
         target_id: endNode(relationship).world_character_id,
         relationship: properties(relationship)
       }}] AS oriented_edges,
       length(path) AS hop_count
ORDER BY hop_count ASC LIMIT 1
"""


_QUERY_TEXT: dict[GraphQueryTemplate, str] = {
    GraphQueryTemplate.DIRECT_RELATIONSHIP: _DIRECT,
    GraphQueryTemplate.SHARED_NEIGHBORS_OUTGOING: _SHARED_OUTGOING,
    GraphQueryTemplate.SHARED_NEIGHBORS_INCOMING: _SHARED_INCOMING,
    GraphQueryTemplate.SHARED_NEIGHBORS_EITHER: _SHARED_EITHER,
    GraphQueryTemplate.RANK_POSITIVE: _RANK_BASE.replace("{order_by}",
        "ORDER BY relationship.familiarity DESC, relationship.affinity DESC, relationship.trust DESC, relationship.tension ASC, target_id"
    ),
    GraphQueryTemplate.RANK_TENSE: _RANK_BASE.replace("{order_by}",
        "ORDER BY relationship.tension DESC, relationship.affinity ASC, relationship.updated_at DESC, target_id"
    ),
    GraphQueryTemplate.RANK_RECENT: _RANK_BASE.replace("{order_by}",
        "ORDER BY relationship.updated_at DESC, relationship.interaction_count DESC, target_id"
    ),
    GraphQueryTemplate.RELATIONSHIP_EVIDENCE: _EVIDENCE,
    GraphQueryTemplate.VISUALIZATION_1: _VISUALIZATION_1,
    GraphQueryTemplate.VISUALIZATION_2: _VISUALIZATION_2,
}
for _direction in ("outgoing", "incoming", "either"):
    for _hops in (1, 2, 3):
        _QUERY_TEXT[
            GraphQueryTemplate(f"shortest_path_{_direction}_{_hops}")
        ] = _path_query(_direction, _hops)


def _event_parameters(command: SocialEventProjectionCommand) -> dict[str, Any]:
    return {
        "world_id": command.world_id,
        "event_id": command.event_id,
        "event_type": command.event_type,
        "occurred_at": command.occurred_at,
        "schema_version": command.schema_version,
        "actor_world_character_id": command.actor_world_character_id,
        "actor_character_id": command.actor_character_id,
        "target_world_character_id": command.target_world_character_id,
        "target_character_id": command.target_character_id,
    }


class Neo4jGraphClient:
    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
        query_timeout_seconds: float = 1.5,
        client_timeout_seconds: float = 2.0,
    ) -> None:
        self._database = database
        self._query_timeout_seconds = query_timeout_seconds
        self._client_timeout_seconds = client_timeout_seconds
        self._driver = GraphDatabase.driver(
            uri,
            auth=(username, password),
            connection_timeout=client_timeout_seconds,
            connection_acquisition_timeout=client_timeout_seconds,
            max_transaction_retry_time=0,
        )

    def close(self) -> None:
        self._driver.close()

    def verify_connectivity(self) -> None:
        try:
            self._driver.verify_connectivity()
        except Exception as exc:  # mapped without retaining provider text
            raise self._mapped_error(exc) from None

    def _mapped_error(self, exc: Exception) -> GraphClientError:
        neo4j_code = str(getattr(exc, "code", ""))
        if ".TransactionTimedOut" in neo4j_code:
            return GraphClientError("neo4j_query_timeout")
        if isinstance(exc, AuthError):
            return GraphClientError("neo4j_auth_invalid")
        if isinstance(exc, (ServiceUnavailable, SessionExpired, OSError)):
            return GraphClientError("neo4j_unavailable")
        if isinstance(exc, TransientError):
            return GraphClientError("neo4j_transient")
        if isinstance(exc, ClientError):
            return GraphClientError("schema_not_ready")
        if isinstance(exc, Neo4jError):
            return GraphClientError("neo4j_transient")
        return GraphClientError("internal_error")

    def _execute(
        self,
        query: str,
        parameters: dict[str, Any],
        *,
        timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        try:
            records, _, _ = self._driver.execute_query(
                Query(query, timeout=timeout_seconds),
                parameters_=parameters,
                database_=self._database,
            )
            return [dict(record) for record in records]
        except Exception as exc:
            raise self._mapped_error(exc) from None

    def _bounded_execute(
        self,
        query: str,
        parameters: dict[str, Any],
        *,
        server_timeout_seconds: float,
        client_timeout_seconds: float,
    ) -> list[dict[str, Any]]:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="neo4j-query")
        future = executor.submit(
            self._execute,
            query,
            parameters,
            timeout_seconds=server_timeout_seconds,
        )
        try:
            return future.result(timeout=client_timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            raise GraphClientError("neo4j_query_timeout") from None
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def bootstrap(self) -> None:
        for query in _BOOTSTRAP_QUERIES:
            self._execute(query, {}, timeout_seconds=10.0)
        constraint_rows = self._execute(
            "SHOW CONSTRAINTS YIELD name RETURN name",
            {},
            timeout_seconds=10.0,
        )
        index_rows = self._execute(
            "SHOW INDEXES YIELD name RETURN name",
            {},
            timeout_seconds=10.0,
        )
        constraints = {str(row["name"]) for row in constraint_rows}
        indexes = {str(row["name"]) for row in index_rows}
        if not _EXPECTED_CONSTRAINTS.issubset(constraints):
            raise GraphClientError("schema_not_ready")
        if not _EXPECTED_INDEXES.issubset(indexes):
            raise GraphClientError("schema_not_ready")

    def apply(
        self, command: ProjectionCommand, *, timeout_seconds: float = 5.0
    ) -> str:
        if isinstance(command, NoGraphMutationCommand):
            return "noop"
        if isinstance(command, SourceExclusionProjectionCommand):
            rows = self._bounded_execute(
                _SOURCE_EXCLUSION,
                {"world_id": command.world_id, "event_id": command.event_id},
                server_timeout_seconds=timeout_seconds,
                client_timeout_seconds=min(10.0, timeout_seconds + 1.0),
            )
            return "removed" if rows and rows[0].get("removed_count") else "noop"
        if isinstance(command, RelationshipStateProjectionCommand):
            parameters = _event_parameters(command.event)
            parameters.update(
                {
                    "relationship_state_id": command.relationship_state_id,
                    "familiarity": command.familiarity,
                    "affinity": command.affinity,
                    "trust": command.trust,
                    "tension": command.tension,
                    "interaction_count": command.interaction_count,
                    "last_event_id": command.last_event_id,
                    "last_event_at": command.last_event_at,
                    "updated_at": command.updated_at,
                    "relationship_version": command.relationship_version,
                }
            )
            rows = self._bounded_execute(
                _RELATIONSHIP,
                parameters,
                server_timeout_seconds=timeout_seconds,
                client_timeout_seconds=min(10.0, timeout_seconds + 1.0),
            )
            if not rows:
                raise GraphClientError("neo4j_transient")
            existing = int(rows[0].get("existing_version") or 0)
            return "stale_noop" if existing > command.relationship_version else "applied"
        query = (
            _EVENT_WITH_TARGET
            if command.target_world_character_id is not None
            else _EVENT_WITHOUT_TARGET
        )
        self._bounded_execute(
            query,
            _event_parameters(command),
            server_timeout_seconds=timeout_seconds,
            client_timeout_seconds=min(10.0, timeout_seconds + 1.0),
        )
        return "applied"

    def run_template(
        self,
        template: GraphQueryTemplate,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        query = _QUERY_TEXT.get(template)
        if query is None:
            raise GraphClientError("payload_invalid")
        started = time.monotonic()
        status = "succeeded"
        try:
            return self._bounded_execute(
                query,
                parameters,
                server_timeout_seconds=self._query_timeout_seconds,
                client_timeout_seconds=self._client_timeout_seconds,
            )
        except GraphClientError as exc:
            status = exc.error_class
            if exc.error_class == "neo4j_query_timeout":
                graph_metrics.increment(
                    "graph_query_timeout_total", template=template.value
                )
            raise
        finally:
            graph_metrics.increment(
                "graph_query_total", template=template.value, status=status
            )
            graph_metrics.observe(
                "graph_query_duration_seconds",
                time.monotonic() - started,
                template=template.value,
                status=status,
            )

    def clear_world(self, world_id: str) -> None:
        while True:
            rows = self._bounded_execute(
                "MATCH (node {world_id: $world_id}) "
                "WITH node LIMIT $batch_size "
                "DETACH DELETE node RETURN count(node) AS removed_count",
                {"world_id": world_id, "batch_size": 500},
                server_timeout_seconds=10.0,
                client_timeout_seconds=10.0,
            )
            removed = int(rows[0].get("removed_count") or 0) if rows else 0
            if removed == 0:
                return

    def world_digest(self, world_id: str) -> dict[str, list[str]]:
        import json

        def entry(*values: object) -> str:
            return json.dumps(values, ensure_ascii=True, separators=(",", ":"))

        world_characters = self._bounded_execute(
            "MATCH (node:WorldCharacter {world_id: $world_id}) "
            "RETURN DISTINCT node.world_character_id AS world_character_id "
            "ORDER BY world_character_id",
            {"world_id": world_id},
            server_timeout_seconds=self._query_timeout_seconds,
            client_timeout_seconds=self._client_timeout_seconds,
        )
        events = self._bounded_execute(
            "MATCH (event:SocialEvent {world_id: $world_id}) "
            "RETURN DISTINCT event.event_id AS event_id ORDER BY event_id",
            {"world_id": world_id},
            server_timeout_seconds=self._query_timeout_seconds,
            client_timeout_seconds=self._client_timeout_seconds,
        )
        relationships = self._bounded_execute(
            "MATCH (actor:WorldCharacter {world_id: $world_id})"
            "-[relationship:RELATES_TO {world_id: $world_id}]->"
            "(target:WorldCharacter {world_id: $world_id}) "
            "RETURN relationship.relationship_state_id AS relationship_state_id, "
            "actor.world_character_id AS actor_id, "
            "target.world_character_id AS target_id, "
            "relationship.relationship_version AS relationship_version, "
            "relationship.familiarity AS familiarity, "
            "relationship.affinity AS affinity, "
            "relationship.trust AS trust, "
            "relationship.tension AS tension, "
            "relationship.interaction_count AS interaction_count "
            "ORDER BY relationship_state_id",
            {"world_id": world_id},
            server_timeout_seconds=self._query_timeout_seconds,
            client_timeout_seconds=self._client_timeout_seconds,
        )
        evidence = self._bounded_execute(
            "MATCH (actor:WorldCharacter {world_id: $world_id})"
            "-[grounded:RELATIONSHIP_GROUNDED_IN {world_id: $world_id}]->"
            "(event:SocialEvent {world_id: $world_id}) "
            "RETURN grounded.relationship_state_id AS relationship_state_id, "
            "actor.world_character_id AS actor_id, "
            "grounded.target_world_character_id AS target_id, "
            "event.event_id AS event_id, "
            "grounded.relationship_version AS relationship_version "
            "ORDER BY relationship_state_id, actor_id, target_id, event_id, relationship_version",
            {"world_id": world_id},
            server_timeout_seconds=self._query_timeout_seconds,
            client_timeout_seconds=self._client_timeout_seconds,
        )
        return {
            "world_characters": [
                entry(row["world_character_id"]) for row in world_characters
            ],
            "events": [entry(row["event_id"]) for row in events],
            "relationships": [
                entry(
                    row["relationship_state_id"],
                    row["actor_id"],
                    row["target_id"],
                    row["relationship_version"],
                    row["familiarity"],
                    row["affinity"],
                    row["trust"],
                    row["tension"],
                    row["interaction_count"],
                )
                for row in relationships
            ],
            "evidence": [
                entry(
                    row["relationship_state_id"],
                    row["actor_id"],
                    row["target_id"],
                    row["event_id"],
                    row["relationship_version"],
                )
                for row in evidence
            ],
        }
