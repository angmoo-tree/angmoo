"""Route-aware logical-call and physical-attempt accounting for P8-L."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from collections.abc import Mapping
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


_CALL_TRACKER_SNAPSHOT_KEYS = frozenset(
    {
        "route",
        "logical_counts",
        "physical_counts",
        "logical_total",
        "physical_total",
        "normal_full_path_cap",
        "request_maximum",
        "repair_node",
        "cancelled",
    }
)


def restore_call_tracker_snapshot(
    snapshot: Mapping[str, Any],
    *,
    deadline_at: datetime,
) -> RouteAwareCallTracker:
    """Restore one exact tracker snapshot at a trusted Chat boundary.

    Specialist Planners and the BOTH coordinator share this implementation so
    request-wide repair accounting cannot drift between routes.
    """

    if set(snapshot) != _CALL_TRACKER_SNAPSHOT_KEYS:
        raise RetrievalContractError("llm_tracker_snapshot_invalid")
    try:
        route = RetrievalRoute(snapshot["route"])
    except (TypeError, ValueError) as exc:
        raise RetrievalContractError("llm_tracker_snapshot_invalid") from exc

    logical_counts = _tracker_count_map(snapshot["logical_counts"])
    physical_counts = _tracker_count_map(snapshot["physical_counts"])
    repair_value = snapshot["repair_node"]
    try:
        repair_node = None if repair_value is None else LlmNode(repair_value)
    except (TypeError, ValueError) as exc:
        raise RetrievalContractError("llm_tracker_snapshot_invalid") from exc
    cancelled = snapshot["cancelled"]
    if not isinstance(cancelled, bool):
        raise RetrievalContractError("llm_tracker_snapshot_invalid")

    normal_cap = sum(NORMAL_NODE_BUDGETS[route].values())
    if (
        snapshot["logical_total"] != sum(logical_counts.values())
        or snapshot["physical_total"] != sum(physical_counts.values())
        or snapshot["normal_full_path_cap"] != normal_cap
        or snapshot["request_maximum"] != normal_cap + 1
    ):
        raise RetrievalContractError("llm_tracker_snapshot_invalid")

    for node in LlmNode:
        allowed_logical = NORMAL_NODE_BUDGETS[route][node]
        if node is repair_node:
            if (
                node is LlmNode.CHARACTER_RESPONSE_GENERATOR
                or allowed_logical < 1
                or logical_counts[node] != allowed_logical + 1
            ):
                raise RetrievalContractError("llm_tracker_snapshot_invalid")
            allowed_logical += 1
        if logical_counts[node] > allowed_logical:
            raise RetrievalContractError("llm_tracker_snapshot_invalid")
        if physical_counts[node] > logical_counts[node] * 2:
            raise RetrievalContractError("llm_tracker_snapshot_invalid")

    tracker = RouteAwareCallTracker(route=route, deadline_at=deadline_at)
    tracker.logical_counts = logical_counts
    tracker.physical_counts = physical_counts
    tracker.repair_node = repair_node
    tracker.cancelled = cancelled
    return tracker


def _tracker_count_map(value: Any) -> dict[LlmNode, int]:
    if not isinstance(value, Mapping) or set(value) != {node.value for node in LlmNode}:
        raise RetrievalContractError("llm_tracker_snapshot_invalid")
    counts: dict[LlmNode, int] = {}
    for node in LlmNode:
        count = value[node.value]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RetrievalContractError("llm_tracker_snapshot_invalid")
        counts[node] = count
    return counts


__all__ = [
    "LlmNode",
    "NORMAL_NODE_BUDGETS",
    "RouteAwareCallTracker",
    "restore_call_tracker_snapshot",
]
