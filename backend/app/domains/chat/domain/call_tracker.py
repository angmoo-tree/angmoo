"""Route-aware logical-call and physical-attempt accounting for P8-L."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.domains.chat.domain.retrieval_intent import RetrievalContractError, RetrievalRoute


class LlmNode(StrEnum):
    RETRIEVAL_ROUTER = "retrieval_router"
    CANONICAL_PLANNER = "canonical_planner"
    GRAPH_PLANNER = "graph_planner"
    CHARACTER_RESPONSE_GENERATOR = "character_response_generator"


NORMAL_NODE_BUDGETS: dict[RetrievalRoute, dict[LlmNode, int]] = {
    RetrievalRoute.CURRENT_CONTEXT: {
        LlmNode.RETRIEVAL_ROUTER: 1,
        LlmNode.CANONICAL_PLANNER: 0,
        LlmNode.GRAPH_PLANNER: 0,
        LlmNode.CHARACTER_RESPONSE_GENERATOR: 1,
    },
    RetrievalRoute.CANONICAL: {
        LlmNode.RETRIEVAL_ROUTER: 1,
        LlmNode.CANONICAL_PLANNER: 1,
        LlmNode.GRAPH_PLANNER: 0,
        LlmNode.CHARACTER_RESPONSE_GENERATOR: 1,
    },
    RetrievalRoute.GRAPH: {
        LlmNode.RETRIEVAL_ROUTER: 1,
        LlmNode.CANONICAL_PLANNER: 0,
        LlmNode.GRAPH_PLANNER: 1,
        LlmNode.CHARACTER_RESPONSE_GENERATOR: 1,
    },
    RetrievalRoute.BOTH: {
        LlmNode.RETRIEVAL_ROUTER: 1,
        LlmNode.CANONICAL_PLANNER: 1,
        LlmNode.GRAPH_PLANNER: 1,
        LlmNode.CHARACTER_RESPONSE_GENERATOR: 1,
    },
    RetrievalRoute.CLARIFICATION: {
        LlmNode.RETRIEVAL_ROUTER: 1,
        LlmNode.CANONICAL_PLANNER: 0,
        LlmNode.GRAPH_PLANNER: 0,
        LlmNode.CHARACTER_RESPONSE_GENERATOR: 1,
    },
}


@dataclass(slots=True)
class RouteAwareCallTracker:
    route: RetrievalRoute
    deadline_at: datetime
    max_physical_attempts_per_logical: int = 2
    logical_counts: dict[LlmNode, int] = field(
        default_factory=lambda: {node: 0 for node in LlmNode}
    )
    physical_counts: dict[LlmNode, int] = field(
        default_factory=lambda: {node: 0 for node in LlmNode}
    )
    repair_node: LlmNode | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        if self.max_physical_attempts_per_logical < 1:
            raise RetrievalContractError("llm_physical_attempt_cap_invalid")

    def _assert_active(self, now: datetime) -> None:
        if self.cancelled:
            raise RetrievalContractError("llm_request_cancelled")
        if now >= self.deadline_at:
            raise RetrievalContractError("llm_request_deadline_exceeded")

    def record_logical_call(
        self,
        node: LlmNode,
        *,
        now: datetime,
        repair: bool = False,
    ) -> int:
        self._assert_active(now)
        normal_cap = NORMAL_NODE_BUDGETS[self.route][node]
        current = self.logical_counts[node]
        if repair:
            if node is LlmNode.CHARACTER_RESPONSE_GENERATOR:
                raise RetrievalContractError("llm_crg_repair_forbidden")
            if self.repair_node is not None:
                raise RetrievalContractError("llm_request_wide_repair_exceeded")
            if current < 1 or normal_cap < 1:
                raise RetrievalContractError("llm_repair_without_normal_call")
            self.repair_node = node
            allowed = normal_cap + 1
        else:
            allowed = normal_cap
        if current >= allowed:
            if node is LlmNode.CHARACTER_RESPONSE_GENERATOR:
                raise RetrievalContractError("llm_duplicate_crg_call")
            raise RetrievalContractError("llm_route_logical_budget_exceeded")
        self.logical_counts[node] = current + 1
        return self.logical_counts[node]

    def record_physical_attempt(self, node: LlmNode, *, now: datetime) -> int:
        self._assert_active(now)
        logical = self.logical_counts[node]
        if logical < 1:
            raise RetrievalContractError("llm_physical_without_logical_call")
        maximum = logical * self.max_physical_attempts_per_logical
        if self.physical_counts[node] >= maximum:
            raise RetrievalContractError("llm_physical_attempt_budget_exceeded")
        self.physical_counts[node] += 1
        return self.physical_counts[node]

    def cancel(self) -> None:
        self.cancelled = True

    @property
    def logical_total(self) -> int:
        return sum(self.logical_counts.values())

    @property
    def physical_total(self) -> int:
        return sum(self.physical_counts.values())

    @property
    def normal_full_path_cap(self) -> int:
        return sum(NORMAL_NODE_BUDGETS[self.route].values())

    @property
    def request_maximum(self) -> int:
        return self.normal_full_path_cap + 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "route": self.route.value,
            "logical_counts": {
                node.value: self.logical_counts[node] for node in LlmNode
            },
            "physical_counts": {
                node.value: self.physical_counts[node] for node in LlmNode
            },
            "logical_total": self.logical_total,
            "physical_total": self.physical_total,
            "normal_full_path_cap": self.normal_full_path_cap,
            "request_maximum": self.request_maximum,
            "repair_node": None if self.repair_node is None else self.repair_node.value,
            "cancelled": self.cancelled,
        }


__all__ = [
    "LlmNode",
    "NORMAL_NODE_BUDGETS",
    "RouteAwareCallTracker",
]
