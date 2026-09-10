"""Code-owned validation and typed execution for Graph Retrieval Plans."""

from __future__ import annotations

from app.contracts.retrieval_observation import observe, detail, observing_step

from dataclasses import dataclass, replace
from datetime import datetime

from app.domains.relationships.contracts.graph_plan import (
    GraphPlanContractError,
    GraphPlanStep,
    GraphRetrievalPlan,
)
from app.domains.relationships.policies.graph_plan_schema import (parse_graph_retrieval_plan_payload)
from app.domains.relationships.contracts.graph_recall import (
    GraphRecallDirection,
    GraphRecallOperation,
    GraphRecallQuery,
    GraphRecallRanking,
    GraphRecallResult,
    GraphRecallScope,
    GraphRecallSource,
    GraphRecallStatus,
)
from app.domains.relationships.contracts.graph_recall_gateway import (GRAPH_RECALL_PRIMITIVE_REGISTRY)
from app.domains.relationships.service.graph_recall import (GraphRecallService)
from app.domains.relationships.contracts.graph_execution import (
    GraphPlanExecutionContext,
    GraphPlanValidationResult,
    GraphPlanStepExecution,
    GraphPlanExecutionResult,
)


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

        for ordinal, step in enumerate(validated.plan.steps, 1):
            with observing_step("graph", ordinal):
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
                        observe("step", operation=step.operation, skipped=True, executed=False, reason="graph_dependency_empty", queries=0)
                        continue
                    counterpart_ids = tuple(candidate_ids)
                else:
                    counterpart_ref = parameters.get("counterpart_ref")
                    counterpart_ids = (
                        None if counterpart_ref is None else bindings[str(counterpart_ref)],
                    )

                observe("step", operation=step.operation, executed=True, skipped=False, queries=len(counterpart_ids), fanout=context.fanout_limit)
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
                    observe("graph_query", operation=query.operation.value, direction=query.direction.value, ranking=query.ranking.value, limit=query.limit, hops=query.max_hops, depth=query.depth, counterpart_filter=query.counterpart_world_character_id is not None)
                    detail(counterpart=query.counterpart_world_character_id, subject=query.scope.subject_world_character_id, operation=query.operation.value)
                    queries.append(query)
                    results.append(
                        self._recall.execute(
                            query,
                            graph_projection_enabled=context.graph_projection_enabled,
                            now=now,
                        )
                    )
                for result in results:
                    observe("validated_result", status=result.status.value, source=result.source.value, reason=result.reason_code, candidates=result.candidate_count, excluded=result.excluded_count, relationships=len(result.relationships), evidence=len(result.evidence), nodes=len(result.world_character_ids), paths=int(result.path is not None), limit_reached=result.truncated)
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
