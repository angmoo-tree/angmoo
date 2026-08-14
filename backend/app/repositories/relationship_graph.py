"""L4 compatibility facade for the canonical graph-read port and adapter.

Current consumer: downstream imports of app.repositories.relationship_graph.
Removal condition: old import usage reaches zero during L4.
"""

from app.domains.relationships.graph_read.repository import (
    DirectionMode,
    GraphEvidenceHit,
    GraphNeighborhoodHit,
    GraphPathHit,
    GraphRelationshipHit,
    RankingMode,
    RelationshipGraphQueryPort,
)
from app.integrations.relationship_graph_read import (
    MAX_EDGE_RESULTS,
    MAX_EVIDENCE_RESULTS,
    MAX_NODE_RESULTS,
    MAX_PATH_HOPS,
    GraphQueryExecutor,
    RelationshipGraphRepository,
)


__all__ = [
    "DirectionMode",
    "GraphEvidenceHit",
    "GraphNeighborhoodHit",
    "GraphPathHit",
    "GraphQueryExecutor",
    "GraphRelationshipHit",
    "MAX_EDGE_RESULTS",
    "MAX_EVIDENCE_RESULTS",
    "MAX_NODE_RESULTS",
    "MAX_PATH_HOPS",
    "RankingMode",
    "RelationshipGraphQueryPort",
    "RelationshipGraphRepository",
]