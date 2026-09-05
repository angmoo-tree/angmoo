"""Stable errors for the relationship-graph read use case."""

from __future__ import annotations


class RelationshipGraphReadError(RuntimeError):
    reason_code = "relationship_graph_read_error"


class RelationshipGraphNotFoundError(RelationshipGraphReadError):
    reason_code = "world_character_not_found"


class RelationshipGraphForbiddenError(RelationshipGraphReadError):
    reason_code = "character_not_owned"


class RelationshipGraphRequestError(RelationshipGraphReadError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class GraphReadBackendError(RuntimeError):
    """Normalized failure raised by graph adapters to the domain use case."""

    def __init__(self, error_class: str) -> None:
        super().__init__(error_class)
        self.error_class = error_class
