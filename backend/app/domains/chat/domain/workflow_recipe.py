"""Strict typed retrieval plans and code-owned bounded workflow recipes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalRoute,
)
RETRIEVAL_WORKFLOW_VERSION = "retrieval-workflow.v1"


class WorkflowRecipe(StrEnum):
    INDEPENDENT_PARALLEL = "INDEPENDENT_PARALLEL"
    GRAPH_THEN_CANONICAL = "GRAPH_THEN_CANONICAL"
    CANONICAL_THEN_GRAPH = "CANONICAL_THEN_GRAPH"


class BoundRetrievalPlan(Protocol):
    request_id: str
    envelope_version: str
    envelope_hash: str


@dataclass(frozen=True, slots=True)
class RetrievalWorkflow:
    request_id: str
    route: RetrievalRoute
    envelope_version: str
    envelope_hash: str
    canonical_plan: BoundRetrievalPlan | None = None
    graph_plan: BoundRetrievalPlan | None = None
    recipe: WorkflowRecipe | None = None
    version: str = RETRIEVAL_WORKFLOW_VERSION

    def __post_init__(self) -> None:
        if self.version != RETRIEVAL_WORKFLOW_VERSION:
            raise RetrievalContractError("retrieval_workflow_version_mismatch")
        for plan in (self.canonical_plan, self.graph_plan):
            if plan is None:
                continue
            if (
                plan.request_id != self.request_id
                or plan.envelope_version != self.envelope_version
                or plan.envelope_hash != self.envelope_hash
            ):
                raise RetrievalContractError("retrieval_workflow_plan_binding_mismatch")
        expected = {
            RetrievalRoute.CURRENT_CONTEXT: (False, False, False),
            RetrievalRoute.CANONICAL: (True, False, False),
            RetrievalRoute.GRAPH: (False, True, False),
            RetrievalRoute.BOTH: (True, True, True),
            RetrievalRoute.CLARIFICATION: (False, False, False),
        }[self.route]
        actual = (
            self.canonical_plan is not None,
            self.graph_plan is not None,
            self.recipe is not None,
        )
        if actual != expected:
            raise RetrievalContractError("retrieval_workflow_route_shape_mismatch")


__all__ = [
    "BoundRetrievalPlan",
    "RETRIEVAL_WORKFLOW_VERSION",
    "RetrievalWorkflow",
    "WorkflowRecipe",
]
