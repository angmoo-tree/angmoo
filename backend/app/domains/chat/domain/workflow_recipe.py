"""Strict typed retrieval plans and code-owned bounded workflow recipes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalIntentEnvelope,
    RetrievalRoute,
)

RETRIEVAL_WORKFLOW_VERSION = "retrieval-workflow.v1"


class WorkflowRecipe(StrEnum):
    INDEPENDENT_PARALLEL = "INDEPENDENT_PARALLEL"
    GRAPH_THEN_CANONICAL = "GRAPH_THEN_CANONICAL"
    CANONICAL_THEN_GRAPH = "CANONICAL_THEN_GRAPH"


class WorkflowAxis(StrEnum):
    CANONICAL = "canonical"
    GRAPH = "graph"


class WorkflowDependencyKind(StrEnum):
    EVENT_REFERENCES = "event_references"
    WORLD_CHARACTER_REFERENCES = "world_character_references"


class WorkflowMergeMode(StrEnum):
    UNION = "union"
    INTERSECTION = "intersection"


@dataclass(frozen=True, slots=True)
class WorkflowRecipeSpec:
    recipe: WorkflowRecipe
    planner_axes: tuple[WorkflowAxis, WorkflowAxis]
    planners_parallel: bool
    dependency_kind: WorkflowDependencyKind | None
    merge_mode: WorkflowMergeMode
    intents: frozenset[str]
    normal_planner_call_cap: int = 2

    def __post_init__(self) -> None:
        if set(self.planner_axes) != {WorkflowAxis.CANONICAL, WorkflowAxis.GRAPH}:
            raise RetrievalContractError("retrieval_workflow_recipe_axes_invalid")
        if not self.intents or self.normal_planner_call_cap != 2:
            raise RetrievalContractError("retrieval_workflow_recipe_cost_invalid")
        if self.planners_parallel:
            if (
                self.dependency_kind is not None
                or self.merge_mode is not WorkflowMergeMode.UNION
            ):
                raise RetrievalContractError(
                    "retrieval_workflow_parallel_recipe_invalid"
                )
        elif (
            self.dependency_kind is None
            or self.merge_mode is not WorkflowMergeMode.INTERSECTION
        ):
            raise RetrievalContractError("retrieval_workflow_dependency_invalid")


WORKFLOW_RECIPE_REGISTRY = MappingProxyType(
    {
        WorkflowRecipe.INDEPENDENT_PARALLEL: WorkflowRecipeSpec(
            recipe=WorkflowRecipe.INDEPENDENT_PARALLEL,
            planner_axes=(WorkflowAxis.CANONICAL, WorkflowAxis.GRAPH),
            planners_parallel=True,
            dependency_kind=None,
            merge_mode=WorkflowMergeMode.UNION,
            intents=frozenset({"relationship_comparison", "mixed_evidence"}),
        ),
        WorkflowRecipe.GRAPH_THEN_CANONICAL: WorkflowRecipeSpec(
            recipe=WorkflowRecipe.GRAPH_THEN_CANONICAL,
            planner_axes=(WorkflowAxis.GRAPH, WorkflowAxis.CANONICAL),
            planners_parallel=False,
            dependency_kind=WorkflowDependencyKind.EVENT_REFERENCES,
            merge_mode=WorkflowMergeMode.INTERSECTION,
            intents=frozenset(
                {"relationship_state", "relationship_cause", "relationship_path"}
            ),
        ),
        WorkflowRecipe.CANONICAL_THEN_GRAPH: WorkflowRecipeSpec(
            recipe=WorkflowRecipe.CANONICAL_THEN_GRAPH,
            planner_axes=(WorkflowAxis.CANONICAL, WorkflowAxis.GRAPH),
            planners_parallel=False,
            dependency_kind=WorkflowDependencyKind.WORLD_CHARACTER_REFERENCES,
            merge_mode=WorkflowMergeMode.INTERSECTION,
            intents=frozenset({"historical_recall", "event_aggregation"}),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class WorkflowRecipeSelection:
    requested: WorkflowRecipe
    selected: WorkflowRecipe
    hint_accepted: bool
    spec: WorkflowRecipeSpec


@dataclass(frozen=True, slots=True)
class WorkflowDependencyBinding:
    """Opaque cross-axis slot plus code-only canonical values.

    Only ``opaque_reference`` may describe the handoff to a Planner. The
    ``actual_values`` stay inside Chat orchestration and deterministic typed
    execution/merge code; they are never part of provider request schemas.
    """

    opaque_reference: str
    source_axis: WorkflowAxis
    target_axis: WorkflowAxis
    kind: WorkflowDependencyKind
    actual_values: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = {
            (
                WorkflowAxis.GRAPH,
                WorkflowAxis.CANONICAL,
                WorkflowDependencyKind.EVENT_REFERENCES,
            ): "graph-result.event_refs",
            (
                WorkflowAxis.CANONICAL,
                WorkflowAxis.GRAPH,
                WorkflowDependencyKind.WORLD_CHARACTER_REFERENCES,
            ): "canonical-result.world_character_refs",
        }.get((self.source_axis, self.target_axis, self.kind))
        if expected is None or self.opaque_reference != expected:
            raise RetrievalContractError("retrieval_workflow_dependency_shape_invalid")
        if (
            not self.actual_values
            or len(self.actual_values) > 40
            or any(not value for value in self.actual_values)
            or len(set(self.actual_values)) != len(self.actual_values)
        ):
            raise RetrievalContractError("retrieval_workflow_dependency_values_invalid")


def select_workflow_recipe(
    intent: RetrievalIntentEnvelope,
) -> WorkflowRecipeSelection:
    """Validate the Router hint and select the bounded code-owned recipe.

    The Router may suggest one of the three names, but cannot change the
    intent-to-recipe registry, execution order, merge mode or call cap.
    """

    if intent.route is not RetrievalRoute.BOTH:
        raise RetrievalContractError("retrieval_workflow_both_route_required")
    if intent.coordination_hint is None:
        raise RetrievalContractError("retrieval_workflow_coordination_hint_required")
    try:
        requested = WorkflowRecipe(intent.coordination_hint)
    except ValueError as exc:
        raise RetrievalContractError(
            "retrieval_workflow_coordination_hint_invalid"
        ) from exc

    selected_spec = next(
        (spec for spec in WORKFLOW_RECIPE_REGISTRY.values() if intent.intent in spec.intents),
        None,
    )
    if selected_spec is None:
        raise RetrievalContractError("retrieval_workflow_intent_not_registered")
    return WorkflowRecipeSelection(
        requested=requested,
        selected=selected_spec.recipe,
        hint_accepted=requested is selected_spec.recipe,
        spec=selected_spec,
    )


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
    "WORKFLOW_RECIPE_REGISTRY",
    "WorkflowAxis",
    "WorkflowDependencyBinding",
    "WorkflowDependencyKind",
    "WorkflowMergeMode",
    "WorkflowRecipe",
    "WorkflowRecipeSelection",
    "WorkflowRecipeSpec",
    "select_workflow_recipe",
]
