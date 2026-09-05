"""Stable name for the storage-neutral relationship query boundary."""

from app.domains.relationships.contracts.graph_query import (RelationshipGraphQueryPort)


RelationshipQueryPort = RelationshipGraphQueryPort

__all__ = ["RelationshipQueryPort"]
