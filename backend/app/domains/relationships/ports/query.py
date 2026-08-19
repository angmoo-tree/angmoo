"""Stable name for the storage-neutral relationship query boundary."""

from app.domains.relationships.graph_read.repository import (
    RelationshipGraphQueryPort,
)


RelationshipQueryPort = RelationshipGraphQueryPort

__all__ = ["RelationshipQueryPort"]
