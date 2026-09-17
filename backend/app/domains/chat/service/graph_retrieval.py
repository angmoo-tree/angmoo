"""GRAPH-route orchestration for the P8-L-M specialist Planner."""

from __future__ import annotations

from app.contracts.decision_observation import decision_scope, emit

from app.contracts.retrieval_observation import observe
from app.domains.chat.contracts.graph_failure import GraphFailureDiagnostic
from app.domains.chat.service.planner_diagnostics import observe_graph_rejection
from app.domains.relationships.contracts.graph_diagnostics import (
    GraphAttemptObservation, GraphRejection, graph_rejection,
)

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from time import monotonic
from typing import Any

from app.domains.chat.contracts.call_tracker import (
    LlmNode,
    RouteAwareCallTracker,
    restore_call_tracker_snapshot,
)
from app.domains.chat.contracts.resolved_envelope import ResolvedRetrievalEnvelope
from app.domains.chat.contracts.retrieval_intent import (
    RetrievalContractError,
    RetrievalIntentEnvelope,
    RetrievalRoute,
)
from app.domains.chat.contracts.workflow_recipe import (
    WorkflowAxis,
    WorkflowDependencyBinding,
)
from app.domains.relationships.contracts.graph_plan import GraphPlanContractError
from app.domains.relationships.contracts.graph_execution import GraphPlanExecutionContext
from app.domains.relationships.contracts.graph_execution import GraphPlanExecutionResult
from app.domains.relationships.contracts.graph_planner import GraphPlannerEntity
from app.domains.relationships.contracts.graph_planner import GraphPlannerOutputError
from app.domains.relationships.contracts.graph_planner import GraphPlannerProviderPort
from app.domains.relationships.contracts.graph_planner import GraphPlannerRelationship
from app.domains.relationships.contracts.graph_planner import GraphPlannerRequest
from app.domains.relationships.contracts.graph_recall import GraphRecallScope
from app.domains.relationships.contracts.graph_plan import GraphRetrievalPlan
from app.domains.relationships.service.graph_planning import GraphRetrievalPlanExecutor
from app.domains.relationships.service.graph_planning import GraphRetrievalPlanValidator


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


@dataclass
class _PlanningProgress:
    rejections: list[GraphRejection] = field(default_factory=list)
    physical_count_complete: bool = True
    phase: str = "request"
    stage: str = "request"


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
        tracker = _tracker or restore_call_tracker_snapshot(command.call_tracker, deadline_at=deadline_at)
        progress = _PlanningProgress()
        try:
            return await self._plan_and_execute(command, now=now, deadline_at=deadline_at,
                tracker=tracker, progress=progress, coordinator_owned=_tracker is not None)
        except (Exception, asyncio.CancelledError) as exc:
            # This copy belongs to the standalone request; BOTH replaces it with
            # its final shared snapshot after all sibling tasks are settled.
            emit("graph_execution", axis="graph", phase="execution",
                 execution_state="failed" if progress.phase == "execution" else "not_entered",
                 basic={"status": "failed", "check": "executor_entered" if progress.phase == "execution" else "not_entered"})
            exc.call_tracker = tracker.snapshot()
            terminal = str(exc)
            if isinstance(exc, asyncio.CancelledError):
                terminal = "graph_retrieval_cancelled"
            elif terminal not in {"graph_planner_request_wide_repair_exhausted", "graph_retrieval_deadline_exceeded"}:
                terminal = "graph_retrieval_failed"
            rows = list(progress.rejections)
            if not rows or rows[-1].phase != progress.phase:
                rows.append(graph_rejection(exc, phase=progress.phase, stage=progress.stage))
            diagnostic = GraphFailureDiagnostic(terminal, tuple(rows),
                tracker.snapshot()["repair_node"], progress.physical_count_complete)
            exc.graph_failure_diagnostic = diagnostic
            observe("graph_failure", axis="graph", status="failed", terminal_code=terminal,
                **rows[-1].payload(), repair_node=diagnostic.repair_node,
                repair_exhausted=terminal == "graph_planner_request_wide_repair_exhausted",
                physical_count_complete=diagnostic.physical_count_complete,
                logical_calls=tracker.logical_counts[LlmNode.GRAPH_PLANNER],
                physical_attempts=tracker.physical_counts[LlmNode.GRAPH_PLANNER])
            raise

    async def _plan_and_execute(self, command: GraphRetrievalCommand, *, now: datetime,
        deadline_at: datetime, tracker: RouteAwareCallTracker, progress: _PlanningProgress,
        coordinator_owned: bool) -> GraphPlanningResult:
        if now.tzinfo is None or deadline_at.tzinfo is None:
            raise RetrievalContractError("graph_retrieval_deadline_timezone_required")
        if now >= deadline_at:
            raise RetrievalContractError("graph_retrieval_deadline_exceeded")
        self._validate_command(command, allow_both=coordinator_owned)
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
        observe("planner_attempt", axis="graph", phase="first", status="started")
        repair_used = False
        first_physical = 0
        repair_physical = 0
        physical_before = tracker.physical_counts[LlmNode.GRAPH_PLANNER]

        tracker.record_logical_call(LlmNode.GRAPH_PLANNER, now=now)
        progress.phase = "first"
        try:
            provider_result = await self._invoke_planner(
                request,
                timeout_seconds=remaining_seconds, tracker=tracker, progress=progress, now=now,
            )
            first_physical = provider_result.physical_attempt_count
            progress.stage = "execution_contract"
            with decision_scope("graph", "first"):
                validated = self._validator.validate(provider_result.plan, context)
        except (GraphPlannerOutputError, GraphPlanContractError) as exc:
            first_physical = tracker.physical_counts[LlmNode.GRAPH_PLANNER] - physical_before
            progress.rejections.append(observe_graph_rejection(exc, phase="first", stage=progress.stage, tracker=tracker))
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
            except RetrievalContractError:
                raise RetrievalContractError(
                    "graph_planner_request_wide_repair_exhausted"
                ) from exc
            # Reuse the same bounded cause-derived code as the diagnostic record.
            repaired_request = replace(
                request, repair_diagnostic=progress.rejections[-1].validation_code,
            )
            progress.phase = "repair"
            try:
                provider_result = await self._invoke_planner(
                    repaired_request,
                    timeout_seconds=remaining_seconds, tracker=tracker, progress=progress, now=now,
                )
                repair_physical = provider_result.physical_attempt_count
                progress.stage = "execution_contract"
                with decision_scope("graph", "repair"):
                    validated = self._validator.validate(provider_result.plan, context)
            except (GraphPlannerOutputError, GraphPlanContractError) as repaired:
                if isinstance(repaired, GraphPlannerOutputError):
                    repair_physical = repaired.physical_attempt_count
                progress.rejections.append(observe_graph_rejection(repaired, phase="repair", stage=progress.stage, tracker=tracker))
                raise RetrievalContractError(
                    "graph_planner_request_wide_repair_exhausted"
                ) from repaired

        observe("planner", axis="graph", planned=len(validated.plan.steps), repair_used=repair_used, first_pass_valid=not repair_used, limit_reached=bool(validated.limit_clamped_steps))
        progress.phase = "execution"
        progress.stage = "execution"
        emit("graph_execution", axis="graph", phase="execution", execution_state="executor_entered",
             basic={"status": "started", "stage": "execution"})
        with decision_scope("graph", "repair" if repair_used else "first", "executor"):
            execution = self._executor.execute(validated.plan, context, now=now)
        emit("graph_execution", axis="graph", phase="execution", execution_state="completed",
             basic={"status": "completed", "stage": "execution", "returned": len(execution.results)})
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

    async def _invoke_planner(self, request: GraphPlannerRequest, *, timeout_seconds: float,
        tracker: RouteAwareCallTracker, progress: _PlanningProgress, now: datetime):
        progress.stage = "provider_output"
        try:
            async with asyncio.timeout(timeout_seconds):
                result = await self._planner.plan(request)
        except (Exception, asyncio.CancelledError) as exc:
            current = exc
            attempt = None
            for _ in range(6):
                if current is None:
                    break
                candidate = getattr(current, "graph_attempt", None)
                if isinstance(candidate, GraphAttemptObservation):
                    attempt = candidate
                    break
                current = current.__cause__
            if attempt is None and isinstance(exc, GraphPlannerOutputError):
                attempt = GraphAttemptObservation(exc.physical_attempt_count)
            if attempt is None:
                attempt = GraphAttemptObservation(0, complete=False)
            for _ in range(attempt.physical_attempts):
                tracker.record_physical_attempt(LlmNode.GRAPH_PLANNER, now=now)
            progress.physical_count_complete &= attempt.complete
            if isinstance(exc, (TimeoutError, asyncio.CancelledError)):
                progress.stage = "cancelled" if isinstance(exc, asyncio.CancelledError) else "transport"
            elif not isinstance(exc, GraphPlanContractError):
                progress.stage = "transport"
            if isinstance(exc, TimeoutError):
                raise RetrievalContractError("graph_retrieval_deadline_exceeded") from exc
            raise
        for _ in range(result.physical_attempt_count):
            tracker.record_physical_attempt(LlmNode.GRAPH_PLANNER, now=now)
        return result

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
            graph_queries=command.intent.graph_queries,
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
            ) + ((("builtin-requester", resolved.requester_world_character_id),) if command.intent.graph_queries else ()),
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
            graph_queries=command.intent.graph_queries,
        )

    @staticmethod
    def _short_circuit(
        command: GraphRetrievalCommand,
        tracker: RouteAwareCallTracker,
        *,
        reason: str,
    ) -> GraphPlanningResult:
        observe("planner", axis="graph", skipped=True, executed=False, reason=reason)
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
