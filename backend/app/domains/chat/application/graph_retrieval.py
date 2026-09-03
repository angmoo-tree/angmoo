"""GRAPH-route orchestration for the P8-L-M specialist Planner."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from time import monotonic
from typing import Any

from app.domains.chat.domain.call_tracker import (
    LlmNode,
    RouteAwareCallTracker,
    restore_call_tracker_snapshot,
)
from app.domains.chat.domain.resolved_envelope import ResolvedRetrievalEnvelope
from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalIntentEnvelope,
    RetrievalRoute,
)
from app.domains.chat.domain.workflow_recipe import (
    WorkflowAxis,
    WorkflowDependencyBinding,
)
from app.domains.relationships.public import (
    GraphPlanContractError,
    GraphPlanExecutionContext,
    GraphPlanExecutionResult,
    GraphPlannerEntity,
    GraphPlannerOutputError,
    GraphPlannerProviderPort,
    GraphPlannerRelationship,
    GraphPlannerRequest,
    GraphRecallScope,
    GraphRetrievalPlan,
    GraphRetrievalPlanExecutor,
    GraphRetrievalPlanValidator,
)


@dataclass(frozen=True, slots=True)
class GraphRetrievalCommand:
    user_message: str
    intent: RetrievalIntentEnvelope
    resolved: ResolvedRetrievalEnvelope
    call_tracker: Mapping[str, Any]
    graph_projection_enabled: bool = True
    workflow_dependency: WorkflowDependencyBinding | None = None

    def __post_init__(self) -> None:
        if not self.user_message.strip() or len(self.user_message) > 4_000:
            raise RetrievalContractError("graph_retrieval_message_invalid")
        if not isinstance(self.graph_projection_enabled, bool):
            raise RetrievalContractError("graph_retrieval_projection_flag_invalid")
        if self.workflow_dependency is not None and (
            self.intent.route is not RetrievalRoute.BOTH
            or self.workflow_dependency.target_axis is not WorkflowAxis.GRAPH
        ):
            raise RetrievalContractError("graph_retrieval_workflow_dependency_invalid")


@dataclass(frozen=True, slots=True)
class GraphPlanningMetrics:
    first_pass_valid: bool
    repair_used: bool
    short_circuited: bool
    short_circuit_reason: str | None
    planner_logical_calls: int
    planner_physical_attempts: int
    executable_step_count: int
    limit_clamped_step_count: int
    hop_clamped_step_count: int
    result_count: int
    provider: str | None
    model: str | None
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    thought_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None
    thinking_level: str | None = None
    max_output_tokens: int | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class GraphPlanningResult:
    request_id: str
    plan: GraphRetrievalPlan | None
    execution: GraphPlanExecutionResult | None
    metrics: GraphPlanningMetrics
    call_tracker: dict[str, Any]


class GraphRetrievalPlanningService:
    """Call one graph specialist, validate it and execute P8-L-I typed reads."""

    def __init__(
        self,
        *,
        planner: GraphPlannerProviderPort,
        executor: GraphRetrievalPlanExecutor,
        validator: GraphRetrievalPlanValidator | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._validator = validator or GraphRetrievalPlanValidator()

    async def plan_and_execute(
        self,
        command: GraphRetrievalCommand,
        *,
        now: datetime,
        deadline_at: datetime,
        _tracker: RouteAwareCallTracker | None = None,
    ) -> GraphPlanningResult:
        if now.tzinfo is None or deadline_at.tzinfo is None:
            raise RetrievalContractError("graph_retrieval_deadline_timezone_required")
        if now >= deadline_at:
            raise RetrievalContractError("graph_retrieval_deadline_exceeded")
        coordinator_owned = _tracker is not None
        self._validate_command(command, allow_both=coordinator_owned)
        tracker = (
            _tracker
            if _tracker is not None
            else restore_call_tracker_snapshot(
                command.call_tracker,
                deadline_at=deadline_at,
            )
        )
        if tracker.route is not command.intent.route:
            raise RetrievalContractError("graph_retrieval_tracker_route_mismatch")

        if not command.resolved.observable:
            return self._short_circuit(command, tracker, reason="graph_scope_unobservable")
        if not command.resolved.graph_operation_allowlist:
            return self._short_circuit(
                command,
                tracker,
                reason="graph_operation_allowlist_empty",
            )

        context = self._execution_context(command)
        request = self._provider_request(command)
        remaining_seconds = (deadline_at - now).total_seconds()
        started = monotonic()
        repair_used = False
        first_physical = 0
        repair_physical = 0

        tracker.record_logical_call(LlmNode.GRAPH_PLANNER, now=now)
        try:
            provider_result = await self._invoke_planner(
                request,
                timeout_seconds=remaining_seconds,
            )
            first_physical = provider_result.physical_attempt_count
            for _ in range(first_physical):
                tracker.record_physical_attempt(LlmNode.GRAPH_PLANNER, now=now)
            validated = self._validator.validate(provider_result.plan, context)
        except (GraphPlannerOutputError, GraphPlanContractError) as exc:
            if isinstance(exc, GraphPlannerOutputError):
                first_physical = exc.physical_attempt_count
                for _ in range(first_physical):
                    tracker.record_physical_attempt(LlmNode.GRAPH_PLANNER, now=now)
            repair_used = True
            remaining_seconds -= monotonic() - started
            if remaining_seconds <= 0:
                raise RetrievalContractError("graph_retrieval_deadline_exceeded") from exc
            try:
                tracker.record_logical_call(
                    LlmNode.GRAPH_PLANNER,
                    now=now,
                    repair=True,
                )
            except RetrievalContractError as budget_exc:
                raise RetrievalContractError(
                    "graph_planner_request_wide_repair_exhausted"
                ) from budget_exc
            diagnostic = getattr(exc, "diagnostic", str(exc))
            repaired_request = replace(request, repair_diagnostic=diagnostic[:160])
            try:
                provider_result = await self._invoke_planner(
                    repaired_request,
                    timeout_seconds=remaining_seconds,
                )
                repair_physical = provider_result.physical_attempt_count
                for _ in range(repair_physical):
                    tracker.record_physical_attempt(LlmNode.GRAPH_PLANNER, now=now)
                validated = self._validator.validate(provider_result.plan, context)
            except (GraphPlannerOutputError, GraphPlanContractError) as repaired:
                if isinstance(repaired, GraphPlannerOutputError):
                    repair_physical = repaired.physical_attempt_count
                    for _ in range(repair_physical):
                        tracker.record_physical_attempt(
                            LlmNode.GRAPH_PLANNER,
                            now=now,
                        )
                raise RetrievalContractError(
                    "graph_planner_request_wide_repair_exhausted"
                ) from repaired

        execution = self._executor.execute(validated.plan, context, now=now)
        return GraphPlanningResult(
            request_id=command.resolved.request_id,
            plan=execution.plan,
            execution=execution,
            metrics=GraphPlanningMetrics(
                first_pass_valid=not repair_used,
                repair_used=repair_used,
                short_circuited=False,
                short_circuit_reason=None,
                planner_logical_calls=1 + int(repair_used),
                planner_physical_attempts=first_physical + repair_physical,
                executable_step_count=len(execution.steps),
                limit_clamped_step_count=len(execution.limit_clamped_steps),
                hop_clamped_step_count=len(execution.hop_clamped_steps),
                result_count=len(execution.results),
                provider=provider_result.provider,
                model=provider_result.model,
                prompt_token_count=provider_result.prompt_token_count,
                output_token_count=provider_result.output_token_count,
                thought_token_count=provider_result.thought_token_count,
                total_token_count=provider_result.total_token_count,
                latency_ms=provider_result.latency_ms,
                thinking_level=provider_result.thinking_level,
                max_output_tokens=provider_result.max_output_tokens,
                finish_reason=provider_result.finish_reason,
            ),
            call_tracker=tracker.snapshot(),
        )

    async def _invoke_planner(
        self,
        request: GraphPlannerRequest,
        *,
        timeout_seconds: float,
    ):
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._planner.plan(request)
        except TimeoutError as exc:
            raise RetrievalContractError("graph_retrieval_deadline_exceeded") from exc

    @staticmethod
    def _validate_command(
        command: GraphRetrievalCommand,
        *,
        allow_both: bool = False,
    ) -> None:
        allowed_routes = {RetrievalRoute.GRAPH}
        if allow_both:
            allowed_routes.add(RetrievalRoute.BOTH)
        if command.intent.route not in allowed_routes:
            raise RetrievalContractError("graph_retrieval_route_invalid")
        if command.intent.envelope_hash != command.resolved.intent_hash:
            raise RetrievalContractError("graph_retrieval_intent_hash_mismatch")
        intent_refs = {entity.ref for entity in command.intent.entities}
        resolved_refs = {binding.ref for binding in command.resolved.entity_bindings}
        if intent_refs != resolved_refs:
            raise RetrievalContractError("graph_retrieval_entity_binding_mismatch")
        if (
            command.intent.route is RetrievalRoute.GRAPH
            and command.resolved.canonical_operation_allowlist
        ):
            raise RetrievalContractError(
                "graph_retrieval_canonical_allowlist_forbidden"
            )

    @staticmethod
    def _provider_request(command: GraphRetrievalCommand) -> GraphPlannerRequest:
        relationship = command.intent.relationship
        aggregation = command.intent.aggregation
        return GraphPlannerRequest(
            request_id=command.resolved.request_id,
            envelope_version=command.resolved.version,
            envelope_hash=command.resolved.envelope_hash,
            user_message=command.user_message,
            intent=command.intent.intent,
            entities=tuple(
                GraphPlannerEntity(
                    ref=entity.ref,
                    mention=entity.mention,
                    role=entity.role,
                )
                for entity in command.intent.entities
            ),
            relationship=(
                None
                if relationship is None
                else GraphPlannerRelationship(
                    from_ref=relationship.from_ref,
                    to_ref=relationship.to_ref,
                    dimension=relationship.dimension,
                    requested_polarity=relationship.requested_polarity,
                )
            ),
            aggregation_kind=None if aggregation is None else aggregation.kind.value,
            aggregation_target=(
                None if aggregation is None else aggregation.target_role
            ),
            max_hops_hint=command.resolved.caps.max_hops,
        )

    @staticmethod
    def _execution_context(command: GraphRetrievalCommand) -> GraphPlanExecutionContext:
        resolved = command.resolved
        return GraphPlanExecutionContext(
            request_id=resolved.request_id,
            envelope_version=resolved.version,
            envelope_hash=resolved.envelope_hash,
            scope=GraphRecallScope(
                owner_id=resolved.owner_id,
                world_id=resolved.world_id,
                subject_world_character_id=resolved.responding_world_character_id,
            ),
            entity_bindings=tuple(
                (binding.ref, binding.world_character_id)
                for binding in resolved.entity_bindings
            ),
            operation_allowlist=resolved.graph_operation_allowlist,
            row_limit=resolved.caps.row_limit,
            max_hops=resolved.caps.max_hops,
            fanout_limit=resolved.caps.fanout_limit,
            relationship_from_world_character_id=(
                resolved.relationship_from_world_character_id
            ),
            relationship_to_world_character_id=(
                resolved.relationship_to_world_character_id
            ),
            graph_projection_enabled=command.graph_projection_enabled,
        )

    @staticmethod
    def _short_circuit(
        command: GraphRetrievalCommand,
        tracker: RouteAwareCallTracker,
        *,
        reason: str,
    ) -> GraphPlanningResult:
        return GraphPlanningResult(
            request_id=command.resolved.request_id,
            plan=None,
            execution=None,
            metrics=GraphPlanningMetrics(
                first_pass_valid=True,
                repair_used=False,
                short_circuited=True,
                short_circuit_reason=reason,
                planner_logical_calls=0,
                planner_physical_attempts=0,
                executable_step_count=0,
                limit_clamped_step_count=0,
                hop_clamped_step_count=0,
                result_count=0,
                provider=None,
                model=None,
            ),
            call_tracker=tracker.snapshot(),
        )


__all__ = [
    "GraphPlanningMetrics",
    "GraphPlanningResult",
    "GraphRetrievalCommand",
    "GraphRetrievalPlanningService",
]
