"""Neo4j adapter for relationship-graph read query ports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from app.domains.relationships.graph_read.repository import (
    GraphEvidenceHit,
    GraphNeighborhoodHit,
    GraphPathHit,
    GraphQueryTemplate,
    GraphRelationshipHit,
)


DirectionMode = Literal["outgoing", "incoming", "either"]
RankingMode = Literal["positive", "tense", "recent"]

MAX_PATH_HOPS = 3
MAX_NODE_RESULTS = 30
MAX_EDGE_RESULTS = 60
MAX_EVIDENCE_RESULTS = 5


class GraphQueryExecutor(Protocol):
    def run_template(
        self,
        template: GraphQueryTemplate,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]: ...


def _bounded(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _graph_datetime(
    value: object,
    *,
    field_name: str,
    allow_none: bool = True,
) -> datetime | str | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"graph_{field_name}_missing")
    if isinstance(value, (datetime, str)):
        return value

    # Neo4j temporal values are driver-specific objects. Keep them inside the
    # graph repository boundary so API schemas only receive native datetimes.
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        native = to_native()
        if isinstance(native, datetime):
            return native
    raise ValueError(f"graph_{field_name}_invalid")


def _relationship(
    *, world_id: str, actor_id: object, target_id: object, payload: object
) -> GraphRelationshipHit:
    if not isinstance(actor_id, str) or not isinstance(target_id, str):
        raise ValueError("graph_relationship_id_invalid")
    if not isinstance(payload, dict):
        raise ValueError("graph_relationship_payload_invalid")
    if payload.get("world_id") != world_id:
        raise ValueError("graph_relationship_world_mismatch")
    state_id = payload.get("relationship_state_id")
    if not isinstance(state_id, str) or not state_id:
        raise ValueError("graph_relationship_state_id_invalid")
    return GraphRelationshipHit(
        world_id=world_id,
        actor_world_character_id=actor_id,
        target_world_character_id=target_id,
        relationship_state_id=state_id,
        familiarity=int(payload.get("familiarity") or 0),
        affinity=int(payload.get("affinity") or 0),
        trust=int(payload.get("trust") or 0),
        tension=int(payload.get("tension") or 0),
        interaction_count=int(payload.get("interaction_count") or 0),
        relationship_version=int(payload.get("relationship_version") or 0),
        last_event_id=(
            str(payload["last_event_id"])
            if payload.get("last_event_id") is not None
            else None
        ),
        last_event_at=_graph_datetime(
            payload.get("last_event_at"),
            field_name="relationship_last_event_at",
        ),
        updated_at=_graph_datetime(
            payload.get("updated_at"),
            field_name="relationship_updated_at",
        ),
    )


class RelationshipGraphRepository:
    def __init__(self, executor: GraphQueryExecutor) -> None:
        self._executor = executor

    def get_direct_relationship(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        include_reverse: bool = False,
    ) -> list[GraphRelationshipHit]:
        pairs = [(source_world_character_id, target_world_character_id)]
        if include_reverse:
            pairs.append((target_world_character_id, source_world_character_id))
        hits: list[GraphRelationshipHit] = []
        for source_id, target_id in pairs:
            rows = self._executor.run_template(
                GraphQueryTemplate.DIRECT_RELATIONSHIP,
                {
                    "world_id": world_id,
                    "source_id": source_id,
                    "target_id": target_id,
                },
            )
            for row in rows[:1]:
                hits.append(
                    _relationship(
                        world_id=world_id,
                        actor_id=row.get("actor_id"),
                        target_id=row.get("target_id"),
                        payload=row.get("relationship"),
                    )
                )
        return hits

    def list_shared_neighbors(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        direction_mode: DirectionMode = "either",
        limit: int = 20,
    ) -> list[str]:
        template = {
            "outgoing": GraphQueryTemplate.SHARED_NEIGHBORS_OUTGOING,
            "incoming": GraphQueryTemplate.SHARED_NEIGHBORS_INCOMING,
            "either": GraphQueryTemplate.SHARED_NEIGHBORS_EITHER,
        }[direction_mode]
        bounded_limit = _bounded(limit, minimum=1, maximum=MAX_NODE_RESULTS)
        rows = self._executor.run_template(
            template,
            {
                "world_id": world_id,
                "source_id": source_world_character_id,
                "target_id": target_world_character_id,
                "limit": bounded_limit,
            },
        )
        return [
            str(row["world_character_id"])
            for row in rows[:bounded_limit]
            if isinstance(row.get("world_character_id"), str)
        ]

    def find_shortest_path(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        direction_mode: DirectionMode = "either",
        max_hops: int = 2,
    ) -> GraphPathHit | None:
        hops = _bounded(max_hops, minimum=1, maximum=MAX_PATH_HOPS)
        template = GraphQueryTemplate(
            f"shortest_path_{direction_mode}_{hops}"
        )
        rows = self._executor.run_template(
            template,
            {
                "world_id": world_id,
                "source_id": source_world_character_id,
                "target_id": target_world_character_id,
            },
        )
        if not rows:
            return None
        row = rows[0]
        node_ids = row.get("world_character_ids")
        raw_edges = row.get("oriented_edges")
        if not isinstance(node_ids, list) or not isinstance(raw_edges, list):
            raise ValueError("graph_path_payload_invalid")
        edges = []
        for raw_edge in raw_edges[:MAX_PATH_HOPS]:
            if not isinstance(raw_edge, dict):
                raise ValueError("graph_path_edge_invalid")
            edges.append(
                _relationship(
                    world_id=world_id,
                    actor_id=raw_edge.get("actor_id"),
                    target_id=raw_edge.get("target_id"),
                    payload=raw_edge.get("relationship"),
                )
            )
        hop_count = int(row.get("hop_count") or len(edges))
        if hop_count > hops or len(node_ids) > hops + 1:
            raise ValueError("graph_path_limit_exceeded")
        return GraphPathHit(
            world_character_ids=tuple(str(value) for value in node_ids),
            oriented_edges=tuple(edges),
            hop_count=hop_count,
        )

    def rank_related_characters(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        mode: RankingMode = "positive",
        limit: int = 20,
    ) -> list[GraphRelationshipHit]:
        template = {
            "positive": GraphQueryTemplate.RANK_POSITIVE,
            "tense": GraphQueryTemplate.RANK_TENSE,
            "recent": GraphQueryTemplate.RANK_RECENT,
        }[mode]
        bounded_limit = _bounded(limit, minimum=1, maximum=MAX_NODE_RESULTS)
        rows = self._executor.run_template(
            template,
            {
                "world_id": world_id,
                "source_id": source_world_character_id,
                "limit": bounded_limit,
            },
        )
        return [
            _relationship(
                world_id=world_id,
                actor_id=row.get("actor_id"),
                target_id=row.get("target_id"),
                payload=row.get("relationship"),
            )
            for row in rows[:bounded_limit]
        ]

    def list_relationship_evidence(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        target_world_character_id: str,
        limit: int = 3,
    ) -> list[GraphEvidenceHit]:
        evidence_limit = _bounded(
            limit, minimum=1, maximum=MAX_EVIDENCE_RESULTS
        )
        rows = self._executor.run_template(
            GraphQueryTemplate.RELATIONSHIP_EVIDENCE,
            {
                "world_id": world_id,
                "source_id": source_world_character_id,
                "target_id": target_world_character_id,
                "evidence_limit": evidence_limit,
            },
        )
        result = []
        for row in rows[:evidence_limit]:
            if not isinstance(row.get("event_id"), str):
                continue
            result.append(
                GraphEvidenceHit(
                    event_id=str(row["event_id"]),
                    event_type=str(row.get("event_type") or ""),
                    occurred_at=_graph_datetime(
                        row.get("occurred_at"),
                        field_name="evidence_occurred_at",
                        allow_none=False,
                    ),
                    relationship_state_id=str(
                        row.get("relationship_state_id") or ""
                    ),
                    relationship_version=int(
                        row.get("relationship_version") or 0
                    ),
                )
            )
        return result

    def get_visualization_neighborhood(
        self,
        *,
        world_id: str,
        source_world_character_id: str,
        depth: int = 1,
        node_limit: int = 20,
        edge_limit: int = 40,
    ) -> GraphNeighborhoodHit:
        bounded_depth = _bounded(depth, minimum=1, maximum=2)
        bounded_nodes = _bounded(node_limit, minimum=1, maximum=MAX_NODE_RESULTS)
        bounded_edges = _bounded(edge_limit, minimum=1, maximum=MAX_EDGE_RESULTS)
        rows = self._executor.run_template(
            (
                GraphQueryTemplate.VISUALIZATION_1
                if bounded_depth == 1
                else GraphQueryTemplate.VISUALIZATION_2
            ),
            {
                "world_id": world_id,
                "source_id": source_world_character_id,
                "edge_limit": bounded_edges + 1,
            },
        )
        truncated = len(rows) > bounded_edges
        edges: list[GraphRelationshipHit] = []
        nodes = {source_world_character_id}
        for row in rows[:bounded_edges]:
            edge = _relationship(
                world_id=world_id,
                actor_id=row.get("actor_id"),
                target_id=row.get("target_id"),
                payload=row.get("relationship"),
            )
            edges.append(edge)
            nodes.add(edge.actor_world_character_id)
            nodes.add(edge.target_world_character_id)
        sorted_nodes = sorted(nodes)
        if len(sorted_nodes) > bounded_nodes:
            allowed = set(sorted_nodes[:bounded_nodes]) | {source_world_character_id}
            edges = [
                edge
                for edge in edges
                if edge.actor_world_character_id in allowed
                and edge.target_world_character_id in allowed
            ]
            sorted_nodes = sorted(allowed)
            truncated = True
        return GraphNeighborhoodHit(
            center_world_character_id=source_world_character_id,
            nodes=tuple(sorted_nodes[:bounded_nodes]),
            edges=tuple(edges[:bounded_edges]),
            truncated=truncated,
        )
