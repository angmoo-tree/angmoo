"""L4 compatibility facade for canonical relationship graph schemas.

Current consumer: downstream imports of app.schemas.relationship_graph.
Removal condition: old import usage reaches zero during L4.
"""

from app.domains.relationships.graph_read.schemas import (
    GraphStatus,
    RelationshipGraphEdgeRead,
    RelationshipGraphEvidenceRead,
    RelationshipGraphNodeRead,
    RelationshipGraphQueryMetaRead,
    RelationshipGraphRead,
    RelationshipGraphSchema,
)


__all__ = [
    "GraphStatus",
    "RelationshipGraphEdgeRead",
    "RelationshipGraphEvidenceRead",
    "RelationshipGraphNodeRead",
    "RelationshipGraphQueryMetaRead",
    "RelationshipGraphRead",
    "RelationshipGraphSchema",
]