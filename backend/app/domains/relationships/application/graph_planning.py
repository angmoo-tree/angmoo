"""Code-owned validation and typed execution for Graph Retrieval Plans."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from app.domains.relationships.domain.graph_retrieval_plan import (
    GraphPlanContractError,
    GraphPlanStep,
    GraphRetrievalPlan,
)
from app.domains.relationships.domain.graph_retrieval_planner import (
    parse_graph_retrieval_plan_payload,
)
from app.domains.relationships.graph_recall.contracts import (
    GraphRecallDirection,
    GraphRecallOperation,
    GraphRecallQuery,
    GraphRecallRanking,
    GraphRecallResult,
    GraphRecallScope,
    GraphRecallSource,
    GraphRecallStatus,
)
from app.domains.relationships.graph_recall.service import (
    GRAPH_RECALL_PRIMITIVE_REGISTRY,
    GraphRecallService,
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


class GraphRetrievalPlanValidator:
    """Bind one untrusted graph-only plan to immutable resolved policy."""

    def validate(
        self,
        plan: GraphRetrievalPlan,
        context: GraphPlanExecutionContext,
    ) -> GraphPlanValidationResult:
        plan = parse_graph_retrieval_plan_payload(
            {
                "version": plan.version,
                "request_id": plan.request_id,
                "envelope_version": plan.envelope_version,
                "envelope_hash": plan.envelope_hash,
                "steps": [
                    {
                        "id": step.id,
                        "operation": step.operation,
                        "input_ref": step.input_ref,
                        "parameters": dict(step.parameters),
                    }
                    for step in plan.steps
                ],
            }
        )
        if (
            plan.request_id != context.request_id
            or plan.envelope_version != context.envelope_version
            or plan.envelope_hash != context.envelope_hash
        ):
            raise GraphPlanContractError("graph_plan_binding_mismatch")

        registry = {operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY}
        allowed = set(context.operation_allowlist)
        if not allowed <= registry:
            raise GraphPlanContractError("graph_execution_allowlist_operation_unknown")
        entity_bindings = dict(context.entity_bindings)
        normalized_steps: list[GraphPlanStep] = []
        limit_clamped: list[str] = []
        hop_clamped: list[str] = []
        seen: set[str] = set()
        for step in plan.steps:
            if step.operation not in registry or step.operation not in allowed:
                raise GraphPlanContractError("graph_plan_operation_forbidden")
            parameters = dict(step.parameters)
            counterpart_ref = parameters.get("counterpart_ref")
            if counterpart_ref is not None:
                if not isinstance(counterpart_ref, str) or counterpart_ref not in entity_bindings:
                    raise GraphPlanContractError("graph_plan_entity_ref_unresolved")
                expected_counterpart = context.expected_counterpart_id
                if expected_counterpart is not None and (
                    entity_bindings[counterpart_ref] != expected_counterpart
                ):
                    raise GraphPlanContractError("graph_plan_counterpart_direction_mismatch")
            if step.input_ref is not None:
                source_step, _, slot = step.input_ref.partition(".")
                if source_step not in seen or slot != "world_character_refs":
                    raise GraphPlanContractError("graph_plan_reference_invalid")

            raw_direction = parameters.get("direction")
            try:
                direction = GraphRecallDirection(str(raw_direction))
            except ValueError as exc:
                raise GraphPlanContractError("graph_plan_direction_invalid") from exc
            expected_direction = context.expected_direction
            if expected_direction is not None and direction is not expected_direction:
                raise GraphPlanContractError("graph_plan_direction_mismatch")

            operation = GraphRecallOperation(step.operation)
            spec = GRAPH_RECALL_PRIMITIVE_REGISTRY[operation]
            raw_limit = parameters.get("limit", context.row_limit)
            if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
                raise GraphPlanContractError("graph_plan_limit_invalid")
            maximum = min(context.row_limit, spec.max_results)
            if raw_limit > maximum:
                parameters["limit"] = maximum
                limit_clamped.append(step.id)
            if "max_hops" in parameters:
                raw_hops = parameters["max_hops"]
                if isinstance(raw_hops, bool) or not isinstance(raw_hops, int):
                    raise GraphPlanContractError("graph_plan_hops_invalid")
                if raw_hops > context.max_hops:
                    parameters["max_hops"] = context.max_hops
                    hop_clamped.append(step.id)
            normalized_steps.append(
                replace(step, parameters=tuple(sorted(parameters.items())))
            )
            seen.add(step.id)

        return GraphPlanValidationResult(
            plan=replace(plan, steps=tuple(normalized_steps)),
            limit_clamped_steps=tuple(limit_clamped),
            hop_clamped_steps=tuple(hop_clamped),
        )


class GraphRetrievalPlanExecutor:
    """Execute only P8-L-I typed graph recall and its canonical revalidation."""

    def __init__(
        self,
        recall: GraphRecallService,
        *,
        validator: GraphRetrievalPlanValidator | None = None,
    ) -> None:
        self._recall = recall
        self._validator = validator or GraphRetrievalPlanValidator()

    def execute(
        self,
        plan: GraphRetrievalPlan,
        context: GraphPlanExecutionContext,
        *,
        now: datetime | None = None,
    ) -> GraphPlanExecutionResult:
        validated = self._validator.validate(plan, context)
        bindings = dict(context.entity_bindings)
        outputs: dict[str, tuple[GraphRecallResult, ...]] = {}
        executions: list[GraphPlanStepExecution] = []

        for step in validated.plan.steps:
            parameters = dict(step.parameters)
            counterpart_ids: tuple[str | None, ...]
            if step.input_ref is not None:
                source_step = step.input_ref.split(".", 1)[0]
                candidate_ids = _world_character_refs(
                    outputs[source_step],
                    subject_id=context.scope.subject_world_character_id,
                )[: context.fanout_limit]
                if not candidate_ids:
                    result = GraphRecallResult(
                        operation=GraphRecallOperation(step.operation),
                        status=GraphRecallStatus.READY,
                        source=GraphRecallSource.NONE,
                        reason_code="graph_dependency_empty",
                    )
                    outputs[step.id] = (result,)
                    executions.append(
                        GraphPlanStepExecution(
                            step_id=step.id,
                            queries=(),
                            results=(result,),
                            dependency_short_circuited=True,
                        )
                    )
                    continue
                counterpart_ids = tuple(candidate_ids)
            else:
                counterpart_ref = parameters.get("counterpart_ref")
                counterpart_ids = (
                    None if counterpart_ref is None else bindings[str(counterpart_ref)],
                )

            queries: list[GraphRecallQuery] = []
            results: list[GraphRecallResult] = []
            for counterpart_id in counterpart_ids:
                query = GraphRecallQuery(
                    operation=GraphRecallOperation(step.operation),
                    scope=context.scope,
                    counterpart_world_character_id=counterpart_id,
                    direction=GraphRecallDirection(str(parameters["direction"])),
                    ranking=GraphRecallRanking(
                        str(parameters.get("ranking", GraphRecallRanking.POSITIVE.value))
                    ),
                    max_hops=min(
                        int(parameters.get("max_hops", context.max_hops)),
                        context.max_hops,
                    ),
                    depth=int(parameters.get("depth", 1)),
                    limit=min(
                        int(parameters.get("limit", context.row_limit)),
                        context.row_limit,
                        GRAPH_RECALL_PRIMITIVE_REGISTRY[
                            GraphRecallOperation(step.operation)
                        ].max_results,
                    ),
                )
                queries.append(query)
                results.append(
                    self._recall.execute(
                        query,
                        graph_projection_enabled=context.graph_projection_enabled,
                        now=now,
                    )
                )
            outputs[step.id] = tuple(results)
            executions.append(
                GraphPlanStepExecution(
                    step_id=step.id,
                    queries=tuple(queries),
                    results=tuple(results),
                )
            )

        return GraphPlanExecutionResult(
            request_id=context.request_id,
            plan=validated.plan,
            steps=tuple(executions),
            limit_clamped_steps=validated.limit_clamped_steps,
            hop_clamped_steps=validated.hop_clamped_steps,
        )


def _world_character_refs(
    results: tuple[GraphRecallResult, ...],
    *,
    subject_id: str,
) -> tuple[str, ...]:
    candidates: list[str] = []
    for result in results:
        candidates.extend(result.world_character_ids)
        if result.path is not None:
            candidates.extend(result.path.world_character_ids)
        for relationship in result.relationships:
            candidates.extend(
                (
                    relationship.actor_world_character_id,
                    relationship.target_world_character_id,
                )
            )
        for evidence in result.evidence:
            candidates.append(evidence.actor_world_character_id)
            if evidence.target_world_character_id is not None:
                candidates.append(evidence.target_world_character_id)
    return tuple(
        identifier
        for identifier in dict.fromkeys(candidates)
        if identifier and identifier != subject_id
    )


__all__ = [
    "GraphPlanExecutionContext",
    "GraphPlanExecutionResult",
    "GraphPlanStepExecution",
    "GraphPlanValidationResult",
    "GraphRetrievalPlanExecutor",
    "GraphRetrievalPlanValidator",
]
