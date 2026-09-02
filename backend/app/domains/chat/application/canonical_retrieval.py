"""CANONICAL-route orchestration for the P8-L-L specialist Planner."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from app.domains.chat.domain.call_tracker import (
    NORMAL_NODE_BUDGETS,
    LlmNode,
    RouteAwareCallTracker,
)
from app.domains.chat.domain.resolved_envelope import ResolvedRetrievalEnvelope
from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalIntentEnvelope,
    RetrievalRoute,
)
from app.domains.memory.public import (
    CanonicalPlanContractError,
    CanonicalPlanExecutionContext,
    CanonicalPlanExecutionResult,
    CanonicalPlannerEntity,
    CanonicalPlannerOutputError,
    CanonicalPlannerProviderPort,
    CanonicalPlannerRelationship,
    CanonicalPlannerRequest,
    CanonicalRetrievalPlan,
    CanonicalRetrievalPlanExecutor,
    CanonicalRetrievalPlanValidator,
    MemoryScope,
)


@dataclass(frozen=True, slots=True)
class CanonicalRetrievalCommand:
    user_message: str
    thread_id: str
    intent: RetrievalIntentEnvelope
    resolved: ResolvedRetrievalEnvelope
    call_tracker: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.user_message.strip() or len(self.user_message) > 4_000:
            raise RetrievalContractError("canonical_retrieval_message_invalid")
        if not self.thread_id:
            raise RetrievalContractError("canonical_retrieval_thread_id_invalid")


@dataclass(frozen=True, slots=True)
class CanonicalPlanningMetrics:
    first_pass_valid: bool
    repair_used: bool
    short_circuited: bool
    short_circuit_reason: str | None
    planner_logical_calls: int
    planner_physical_attempts: int
    executable_step_count: int
    limit_clamped_step_count: int
    result_record_count: int
    provider: str | None
    model: str | None


@dataclass(frozen=True, slots=True)
class CanonicalPlanningResult:
    request_id: str
    plan: CanonicalRetrievalPlan | None
    execution: CanonicalPlanExecutionResult | None
    metrics: CanonicalPlanningMetrics
    call_tracker: dict[str, Any]


class CanonicalRetrievalPlanningService:
    """Call one specialist Planner, validate it and execute only typed reads."""

    def __init__(
        self,
        *,
        planner: CanonicalPlannerProviderPort,
        executor: CanonicalRetrievalPlanExecutor,
        validator: CanonicalRetrievalPlanValidator | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._validator = validator or CanonicalRetrievalPlanValidator()

    async def plan_and_execute(
        self,
        command: CanonicalRetrievalCommand,
        *,
        now: datetime,
        deadline_at: datetime,
    ) -> CanonicalPlanningResult:
        if now.tzinfo is None or deadline_at.tzinfo is None:
            raise RetrievalContractError(
                "canonical_retrieval_deadline_timezone_required"
            )
        if now >= deadline_at:
            raise RetrievalContractError("canonical_retrieval_deadline_exceeded")
        self._validate_command(command)
        tracker = _restore_call_tracker_snapshot(
            command.call_tracker,
            deadline_at=deadline_at,
        )
        if tracker.route is not RetrievalRoute.CANONICAL:
            raise RetrievalContractError("canonical_retrieval_tracker_route_mismatch")

        if not command.resolved.memory_enabled:
            return self._short_circuit(
                command,
                tracker,
                reason="memory_opt_out",
            )
        if not command.resolved.canonical_operation_allowlist:
            return self._short_circuit(
                command,
                tracker,
                reason="canonical_operation_allowlist_empty",
            )

        context = self._execution_context(command)
        request = self._provider_request(command)
        remaining_seconds = (deadline_at - now).total_seconds()
        started = monotonic()
        repair_used = False
        first_physical = 0
        repair_physical = 0

        tracker.record_logical_call(LlmNode.CANONICAL_PLANNER, now=now)
        try:
            provider_result = await self._invoke_planner(
                request,
                timeout_seconds=remaining_seconds,
            )
            first_physical = provider_result.physical_attempt_count
            for _ in range(first_physical):
                tracker.record_physical_attempt(LlmNode.CANONICAL_PLANNER, now=now)
            validated = self._validator.validate(provider_result.plan, context)
        except (CanonicalPlannerOutputError, CanonicalPlanContractError) as exc:
            if isinstance(exc, CanonicalPlannerOutputError):
                first_physical = exc.physical_attempt_count
                for _ in range(first_physical):
                    tracker.record_physical_attempt(
                        LlmNode.CANONICAL_PLANNER,
                        now=now,
                    )
            repair_used = True
            remaining_seconds -= monotonic() - started
            if remaining_seconds <= 0:
                raise RetrievalContractError(
                    "canonical_retrieval_deadline_exceeded"
                ) from exc
            try:
                tracker.record_logical_call(
                    LlmNode.CANONICAL_PLANNER,
                    now=now,
                    repair=True,
                )
            except RetrievalContractError as budget_exc:
                raise RetrievalContractError(
                    "canonical_planner_request_wide_repair_exhausted"
                ) from budget_exc
            diagnostic = getattr(exc, "diagnostic", str(exc))
            repaired_request = replace(
                request,
                repair_diagnostic=diagnostic[:160],
            )
            try:
                provider_result = await self._invoke_planner(
                    repaired_request,
                    timeout_seconds=remaining_seconds,
                )
                repair_physical = provider_result.physical_attempt_count
                for _ in range(repair_physical):
                    tracker.record_physical_attempt(
                        LlmNode.CANONICAL_PLANNER,
                        now=now,
                    )
                validated = self._validator.validate(provider_result.plan, context)
            except (CanonicalPlannerOutputError, CanonicalPlanContractError) as repaired:
                if isinstance(repaired, CanonicalPlannerOutputError):
                    repair_physical = repaired.physical_attempt_count
                    for _ in range(repair_physical):
                        tracker.record_physical_attempt(
                            LlmNode.CANONICAL_PLANNER,
                            now=now,
                        )
                raise RetrievalContractError(
                    "canonical_planner_request_wide_repair_exhausted"
                ) from repaired

        execution = self._executor.execute(validated.plan, context, now=now)
        return CanonicalPlanningResult(
            request_id=command.resolved.request_id,
            plan=execution.plan,
            execution=execution,
            metrics=CanonicalPlanningMetrics(
                first_pass_valid=not repair_used,
                repair_used=repair_used,
                short_circuited=False,
                short_circuit_reason=None,
                planner_logical_calls=1 + int(repair_used),
                planner_physical_attempts=first_physical + repair_physical,
                executable_step_count=len(execution.steps),
                limit_clamped_step_count=len(execution.limit_clamped_steps),
                result_record_count=len(execution.records),
                provider=provider_result.provider,
                model=provider_result.model,
            ),
            call_tracker=tracker.snapshot(),
        )

    async def _invoke_planner(
        self,
        request: CanonicalPlannerRequest,
        *,
        timeout_seconds: float,
    ):
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._planner.plan(request)
        except TimeoutError as exc:
            raise RetrievalContractError(
                "canonical_retrieval_deadline_exceeded"
            ) from exc

    @staticmethod
    def _validate_command(command: CanonicalRetrievalCommand) -> None:
        if command.intent.route is not RetrievalRoute.CANONICAL:
            raise RetrievalContractError("canonical_retrieval_route_invalid")
        if command.intent.envelope_hash != command.resolved.intent_hash:
            raise RetrievalContractError("canonical_retrieval_intent_hash_mismatch")
        intent_refs = {entity.ref for entity in command.intent.entities}
        resolved_refs = {binding.ref for binding in command.resolved.entity_bindings}
        if intent_refs != resolved_refs:
            raise RetrievalContractError("canonical_retrieval_entity_binding_mismatch")
        if command.resolved.graph_operation_allowlist:
            raise RetrievalContractError(
                "canonical_retrieval_graph_allowlist_forbidden"
            )

    @staticmethod
    def _provider_request(
        command: CanonicalRetrievalCommand,
    ) -> CanonicalPlannerRequest:
        relationship = command.intent.relationship
        aggregation = command.intent.aggregation
        return CanonicalPlannerRequest(
            request_id=command.resolved.request_id,
            envelope_version=command.resolved.version,
            envelope_hash=command.resolved.envelope_hash,
            user_message=command.user_message,
            intent=command.intent.intent,
            entities=tuple(
                CanonicalPlannerEntity(
                    ref=entity.ref,
                    mention=entity.mention,
                    role=entity.role,
                )
                for entity in command.intent.entities
            ),
            relationship=(
                None
                if relationship is None
                else CanonicalPlannerRelationship(
                    from_ref=relationship.from_ref,
                    to_ref=relationship.to_ref,
                    dimension=relationship.dimension,
                    requested_polarity=relationship.requested_polarity,
                )
            ),
            resolved_time_available=(
                command.resolved.absolute_time_from is not None
                and command.resolved.absolute_time_to is not None
            ),
            aggregation_kind=(None if aggregation is None else aggregation.kind.value),
            aggregation_target=(
                None if aggregation is None else aggregation.target_role
            ),
        )

    @staticmethod
    def _execution_context(
        command: CanonicalRetrievalCommand,
    ) -> CanonicalPlanExecutionContext:
        resolved = command.resolved
        if (resolved.absolute_time_from is None) != (
            resolved.absolute_time_to is None
        ):
            raise RetrievalContractError("canonical_retrieval_time_binding_incomplete")
        return CanonicalPlanExecutionContext(
            request_id=resolved.request_id,
            envelope_version=resolved.version,
            envelope_hash=resolved.envelope_hash,
            scope=MemoryScope(
                owner_id=resolved.owner_id,
                world_id=resolved.world_id,
                subject_world_character_id=resolved.responding_world_character_id,
            ),
            thread_id=command.thread_id,
            entity_bindings=tuple(
                (binding.ref, binding.world_character_id)
                for binding in resolved.entity_bindings
            ),
            operation_allowlist=resolved.canonical_operation_allowlist,
            row_limit=resolved.caps.row_limit,
            occurred_from=_optional_utc(resolved.absolute_time_from),
            occurred_to=_optional_utc(resolved.absolute_time_to),
        )

    @staticmethod
    def _short_circuit(
        command: CanonicalRetrievalCommand,
        tracker: RouteAwareCallTracker,
        *,
        reason: str,
    ) -> CanonicalPlanningResult:
        return CanonicalPlanningResult(
            request_id=command.resolved.request_id,
            plan=None,
            execution=None,
            metrics=CanonicalPlanningMetrics(
                first_pass_valid=True,
                repair_used=False,
                short_circuited=True,
                short_circuit_reason=reason,
                planner_logical_calls=0,
                planner_physical_attempts=0,
                executable_step_count=0,
                limit_clamped_step_count=0,
                result_record_count=0,
                provider=None,
                model=None,
            ),
            call_tracker=tracker.snapshot(),
        )


def _optional_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RetrievalContractError("canonical_retrieval_time_binding_invalid") from exc
    if parsed.tzinfo is None:
        raise RetrievalContractError("canonical_retrieval_time_binding_invalid")
    return parsed.astimezone(UTC)


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


def _restore_call_tracker_snapshot(
    snapshot: Mapping[str, Any],
    *,
    deadline_at: datetime,
) -> RouteAwareCallTracker:
    """Restore the frozen P8-L-J tracker without changing its domain contract."""

    if set(snapshot) != _CALL_TRACKER_SNAPSHOT_KEYS:
        raise RetrievalContractError("canonical_retrieval_tracker_snapshot_invalid")
    try:
        route = RetrievalRoute(snapshot["route"])
    except (TypeError, ValueError) as exc:
        raise RetrievalContractError(
            "canonical_retrieval_tracker_snapshot_invalid"
        ) from exc

    logical_counts = _tracker_count_map(snapshot["logical_counts"])
    physical_counts = _tracker_count_map(snapshot["physical_counts"])
    repair_value = snapshot["repair_node"]
    try:
        repair_node = None if repair_value is None else LlmNode(repair_value)
    except (TypeError, ValueError) as exc:
        raise RetrievalContractError(
            "canonical_retrieval_tracker_snapshot_invalid"
        ) from exc
    cancelled = snapshot["cancelled"]
    if not isinstance(cancelled, bool):
        raise RetrievalContractError("canonical_retrieval_tracker_snapshot_invalid")

    normal_cap = sum(NORMAL_NODE_BUDGETS[route].values())
    if (
        snapshot["logical_total"] != sum(logical_counts.values())
        or snapshot["physical_total"] != sum(physical_counts.values())
        or snapshot["normal_full_path_cap"] != normal_cap
        or snapshot["request_maximum"] != normal_cap + 1
    ):
        raise RetrievalContractError("canonical_retrieval_tracker_snapshot_invalid")

    for node in LlmNode:
        allowed_logical = NORMAL_NODE_BUDGETS[route][node]
        if node is repair_node:
            if (
                node is LlmNode.CHARACTER_RESPONSE_GENERATOR
                or allowed_logical < 1
                or logical_counts[node] != allowed_logical + 1
            ):
                raise RetrievalContractError(
                    "canonical_retrieval_tracker_snapshot_invalid"
                )
            allowed_logical += 1
        if logical_counts[node] > allowed_logical:
            raise RetrievalContractError("canonical_retrieval_tracker_snapshot_invalid")
        if physical_counts[node] > logical_counts[node] * 2:
            raise RetrievalContractError("canonical_retrieval_tracker_snapshot_invalid")

    tracker = RouteAwareCallTracker(route=route, deadline_at=deadline_at)
    tracker.logical_counts = logical_counts
    tracker.physical_counts = physical_counts
    tracker.repair_node = repair_node
    tracker.cancelled = cancelled
    return tracker


def _tracker_count_map(value: Any) -> dict[LlmNode, int]:
    if not isinstance(value, Mapping) or set(value) != {node.value for node in LlmNode}:
        raise RetrievalContractError("canonical_retrieval_tracker_snapshot_invalid")
    counts: dict[LlmNode, int] = {}
    for node in LlmNode:
        count = value[node.value]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RetrievalContractError(
                "canonical_retrieval_tracker_snapshot_invalid"
            )
        counts[node] = count
    return counts


__all__ = [
    "CanonicalPlanningMetrics",
    "CanonicalPlanningResult",
    "CanonicalRetrievalCommand",
    "CanonicalRetrievalPlanningService",
]
