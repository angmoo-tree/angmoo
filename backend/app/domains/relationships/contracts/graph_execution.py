"""Validated graph execution bindings and typed results."""
from __future__ import annotations
from dataclasses import (dataclass)

from app.domains.relationships.contracts.graph_plan import (
    GraphPlanContractError,
    GraphRetrievalPlan,
)

from app.domains.relationships.contracts.graph_recall import (
    GraphRecallDirection,
    GraphRecallQuery,
    GraphRecallResult,
    GraphRecallScope,
)


@dataclass(frozen=True, slots=True)
class GraphPlanExecutionContext:
    """Actual identities and graph caps injected only by trusted code."""

    request_id: str
    envelope_version: str
    envelope_hash: str
    scope: GraphRecallScope
    entity_bindings: tuple[tuple[str, str], ...]
    operation_allowlist: tuple[str, ...]
    row_limit: int
    max_hops: int
    fanout_limit: int
    relationship_from_world_character_id: str | None = None
    relationship_to_world_character_id: str | None = None
    graph_projection_enabled: bool = True

    def __post_init__(self) -> None:
        if not self.request_id or not self.envelope_version or len(self.envelope_hash) != 64:
            raise GraphPlanContractError("graph_execution_binding_invalid")
        if not all(
            (
                self.scope.owner_id,
                self.scope.world_id,
                self.scope.subject_world_character_id,
            )
        ):
            raise GraphPlanContractError("graph_execution_scope_invalid")
        refs = [ref for ref, _identifier in self.entity_bindings]
        identifiers = [identifier for _ref, identifier in self.entity_bindings]
        if (
            len(refs) != len(set(refs))
            or any(not ref for ref in refs)
            or any(not identifier for identifier in identifiers)
        ):
            raise GraphPlanContractError("graph_execution_entity_binding_invalid")
        if len(set(self.operation_allowlist)) != len(self.operation_allowlist):
            raise GraphPlanContractError("graph_execution_allowlist_duplicate")
        if not 1 <= self.row_limit <= 50:
            raise GraphPlanContractError("graph_execution_row_limit_invalid")
        if not 1 <= self.max_hops <= 3:
            raise GraphPlanContractError("graph_execution_hop_limit_invalid")
        if not 1 <= self.fanout_limit <= 40:
            raise GraphPlanContractError("graph_execution_fanout_invalid")
        if (self.relationship_from_world_character_id is None) != (
            self.relationship_to_world_character_id is None
        ):
            raise GraphPlanContractError("graph_execution_direction_incomplete")

    @property
    def expected_direction(self) -> GraphRecallDirection | None:
        subject = self.scope.subject_world_character_id
        if self.relationship_from_world_character_id is None:
            return None
        if self.relationship_from_world_character_id == subject:
            return GraphRecallDirection.OUTGOING
        if self.relationship_to_world_character_id == subject:
            return GraphRecallDirection.INCOMING
        raise GraphPlanContractError("graph_execution_subject_direction_mismatch")

    @property
    def expected_counterpart_id(self) -> str | None:
        direction = self.expected_direction
        if direction is GraphRecallDirection.OUTGOING:
            return self.relationship_to_world_character_id
        if direction is GraphRecallDirection.INCOMING:
            return self.relationship_from_world_character_id
        return None


@dataclass(frozen=True, slots=True)
class GraphPlanValidationResult:
    plan: GraphRetrievalPlan
    limit_clamped_steps: tuple[str, ...]
    hop_clamped_steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphPlanStepExecution:
    step_id: str
    queries: tuple[GraphRecallQuery, ...]
    results: tuple[GraphRecallResult, ...]
    dependency_short_circuited: bool = False


@dataclass(frozen=True, slots=True)
class GraphPlanExecutionResult:
    request_id: str
    plan: GraphRetrievalPlan
    steps: tuple[GraphPlanStepExecution, ...]
    limit_clamped_steps: tuple[str, ...]
    hop_clamped_steps: tuple[str, ...]

    @property
    def results(self) -> tuple[GraphRecallResult, ...]:
        return tuple(result for step in self.steps for result in step.results)
