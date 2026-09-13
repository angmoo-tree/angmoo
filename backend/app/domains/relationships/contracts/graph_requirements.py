"""Provider-neutral graph requirements, before query planning or identity lookup."""
from dataclasses import dataclass

from app.domains.relationships.contracts.graph_plan import GraphPlanContractError


@dataclass(frozen=True, slots=True)
class GraphQueryRequirement:
    kind: str
    direction: str
    target_ref: str | None = None
    result_of: int | None = None

    def __post_init__(self):
        allowed = {
            "pair": {"outgoing", "incoming", "bidirectional"},
            "collection": {"outgoing", "incoming"},
            "shared": {"outgoing", "incoming", "either"},
            "path": {"outgoing", "incoming", "either"},
        }
        if self.kind not in allowed or self.direction not in allowed[self.kind]:
            raise GraphPlanContractError("graph_query_direction_invalid")
        if self.kind == "collection":
            if self.target_ref is not None or self.result_of is not None:
                raise GraphPlanContractError("graph_query_collection_target_forbidden")
        elif (self.target_ref is None) == (self.result_of is None):
            raise GraphPlanContractError("graph_query_target_required")
        if self.target_ref is not None and (not isinstance(self.target_ref, str) or not self.target_ref):
            raise GraphPlanContractError("graph_query_target_invalid")
        if self.result_of is not None and (type(self.result_of) is not int or not 1 <= self.result_of <= 2):
            raise GraphPlanContractError("graph_query_dependency_invalid")

    def payload(self):
        return {"kind": self.kind, "direction": self.direction,
                "target_ref": self.target_ref, "result_of": self.result_of}


def validate_graph_queries(queries, refs):
    if not 1 <= len(queries) <= 3:
        raise GraphPlanContractError("graph_query_count_invalid")
    for ordinal, query in enumerate(queries, 1):
        if query.target_ref is not None and query.target_ref not in refs:
            raise GraphPlanContractError("graph_query_target_unbound")
        if query.result_of is not None and query.result_of >= ordinal:
            raise GraphPlanContractError("graph_query_dependency_invalid")


QUERY_OPERATIONS = {
    "pair": frozenset({"direct_relationship", "relationship_evidence"}),
    "collection": frozenset({"rank_related_characters", "relationship_neighborhood"}),
    "shared": frozenset({"shared_neighbors"}),
    "path": frozenset({"shortest_path"}),
}
