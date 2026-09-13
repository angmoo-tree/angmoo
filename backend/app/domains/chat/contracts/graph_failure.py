"""Chat-owned Graph termination details, separate from provider/UI payloads."""
from dataclasses import dataclass

from app.domains.relationships.contracts.graph_diagnostics import GraphRejection


_TERMINALS = frozenset({
    "graph_planner_request_wide_repair_exhausted", "graph_retrieval_deadline_exceeded",
    "graph_retrieval_failed", "graph_retrieval_cancelled",
})


@dataclass(frozen=True, slots=True)
class GraphFailureDiagnostic:
    terminal_code: str
    rejections: tuple[GraphRejection, ...]
    repair_node: str | None
    physical_count_complete: bool

    def __post_init__(self):
        if self.terminal_code not in _TERMINALS or not isinstance(self.rejections, tuple) or not 1 <= len(self.rejections) <= 2 or any(not isinstance(row, GraphRejection) for row in self.rejections):
            raise ValueError("graph_failure_diagnostic_invalid")
        if self.repair_node not in {None, "retrieval_router", "canonical_planner", "graph_planner"} or type(self.physical_count_complete) is not bool:
            raise ValueError("graph_failure_state_invalid")

    def payload(self):
        return {
            "version": "graph-failure.v1", "terminal_code": self.terminal_code,
            "rejections": [row.payload() for row in self.rejections],
            "repair_node": self.repair_node,
            "repair_exhausted": self.terminal_code == "graph_planner_request_wide_repair_exhausted",
            "physical_count_complete": self.physical_count_complete,
        }


def graph_failure_diagnostic(exc: BaseException, *, include_sibling: bool = False) -> GraphFailureDiagnostic | None:
    value = getattr(exc, "graph_failure_diagnostic", None)
    if not isinstance(value, GraphFailureDiagnostic) and include_sibling:
        value = getattr(exc, "sibling_graph_failure_diagnostic", None)
    return value if isinstance(value, GraphFailureDiagnostic) else None
