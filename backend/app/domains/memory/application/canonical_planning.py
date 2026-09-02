"""Code-owned validation and typed execution for Canonical Retrieval Plans."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from app.domains.memory.application.recall import (
    CANONICAL_PRIMITIVE_REGISTRY,
    CanonicalRecallService,
)
from app.domains.memory.domain.canonical_retrieval_plan import (
    CanonicalPlanContractError,
    CanonicalPlanStep,
    CanonicalRetrievalPlan,
)
from app.domains.memory.domain.canonical_retrieval_planner import (
    parse_canonical_retrieval_plan_payload,
)
from app.domains.memory.domain.recall import (
    CanonicalRecallOperation,
    CanonicalRecallQuery,
    CanonicalRecallResult,
    CanonicalRecallStatus,
)
from app.domains.memory.domain.scope import MemoryScope


@dataclass(frozen=True, slots=True)
class CanonicalPlanExecutionContext:
    """Canonical values injected by code and never shown to the Planner."""

    request_id: str
    envelope_version: str
    envelope_hash: str
    scope: MemoryScope
    thread_id: str
    entity_bindings: tuple[tuple[str, str], ...]
    operation_allowlist: tuple[str, ...]
    row_limit: int
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None

    def __post_init__(self) -> None:
        if not self.request_id or not self.thread_id:
            raise CanonicalPlanContractError("canonical_execution_binding_invalid")
        if not self.envelope_version or len(self.envelope_hash) != 64:
            raise CanonicalPlanContractError("canonical_execution_binding_invalid")
        refs = [ref for ref, _identifier in self.entity_bindings]
        identifiers = [identifier for _ref, identifier in self.entity_bindings]
        if (
            len(refs) != len(set(refs))
            or any(not ref for ref in refs)
            or any(not identifier for identifier in identifiers)
        ):
            raise CanonicalPlanContractError(
                "canonical_execution_entity_binding_invalid"
            )
        if len(set(self.operation_allowlist)) != len(self.operation_allowlist):
            raise CanonicalPlanContractError(
                "canonical_execution_allowlist_duplicate"
            )
        if not 1 <= self.row_limit <= 50:
            raise CanonicalPlanContractError("canonical_execution_row_limit_invalid")


@dataclass(frozen=True, slots=True)
class CanonicalPlanValidationResult:
    plan: CanonicalRetrievalPlan
    limit_clamped_steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CanonicalPlanStepExecution:
    step_id: str
    query: CanonicalRecallQuery | None
    result: CanonicalRecallResult
    dependency_short_circuited: bool = False


@dataclass(frozen=True, slots=True)
class CanonicalPlanExecutionResult:
    request_id: str
    plan: CanonicalRetrievalPlan
    steps: tuple[CanonicalPlanStepExecution, ...]
    limit_clamped_steps: tuple[str, ...]

    @property
    def records(self):
        return tuple(record for step in self.steps for record in step.result.records)


class CanonicalRetrievalPlanValidator:
    """Bind an untrusted typed plan to one immutable execution context."""

    def validate(
        self,
        plan: CanonicalRetrievalPlan,
        context: CanonicalPlanExecutionContext,
    ) -> CanonicalPlanValidationResult:
        # Provider adapters normally return a parser-produced value object, but
        # ports and tests may supply one directly. Re-enter the strict wire
        # parser so no caller can bypass operation-specific shape validation.
        plan = parse_canonical_retrieval_plan_payload(
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
            raise CanonicalPlanContractError("canonical_plan_binding_mismatch")

        registry = {operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY}
        allowed = set(context.operation_allowlist)
        if not allowed <= registry:
            raise CanonicalPlanContractError(
                "canonical_execution_allowlist_operation_unknown"
            )
        entity_refs = {ref for ref, _identifier in context.entity_bindings}
        normalized_steps: list[CanonicalPlanStep] = []
        clamped: list[str] = []
        seen: set[str] = set()
        for step in plan.steps:
            if step.operation not in registry or step.operation not in allowed:
                raise CanonicalPlanContractError(
                    "canonical_plan_operation_forbidden"
                )
            parameters = dict(step.parameters)
            if "counterpart_ref" in parameters and (
                parameters["counterpart_ref"] not in entity_refs
            ):
                raise CanonicalPlanContractError(
                    "canonical_plan_entity_ref_unresolved"
                )
            if "entity_ref" in parameters and parameters["entity_ref"] not in entity_refs:
                raise CanonicalPlanContractError(
                    "canonical_plan_entity_ref_unresolved"
                )
            if step.input_ref is not None:
                source_step, _, slot = step.input_ref.partition(".")
                if source_step not in seen or slot != "source_refs":
                    raise CanonicalPlanContractError(
                        "canonical_plan_reference_invalid"
                    )
            if "limit" in parameters:
                raw_limit = parameters["limit"]
                if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
                    raise CanonicalPlanContractError("canonical_plan_limit_invalid")
                if raw_limit > context.row_limit:
                    parameters["limit"] = context.row_limit
                    clamped.append(step.id)
            normalized_steps.append(
                replace(step, parameters=tuple(sorted(parameters.items())))
            )
            seen.add(step.id)

        return CanonicalPlanValidationResult(
            plan=replace(plan, steps=tuple(normalized_steps)),
            limit_clamped_steps=tuple(clamped),
        )


class CanonicalRetrievalPlanExecutor:
    """Translate typed steps into P8-L-H queries and execute revalidated reads."""

    def __init__(
        self,
        recall: CanonicalRecallService,
        *,
        validator: CanonicalRetrievalPlanValidator | None = None,
    ) -> None:
        self._recall = recall
        self._validator = validator or CanonicalRetrievalPlanValidator()

    def execute(
        self,
        plan: CanonicalRetrievalPlan,
        context: CanonicalPlanExecutionContext,
        *,
        now: datetime | None = None,
    ) -> CanonicalPlanExecutionResult:
        validated = self._validator.validate(plan, context)
        outputs: dict[str, CanonicalRecallResult] = {}
        executions: list[CanonicalPlanStepExecution] = []
        entity_bindings = dict(context.entity_bindings)

        for step in validated.plan.steps:
            parameters = dict(step.parameters)
            source_references: tuple[str, ...] = ()
            if step.input_ref is not None:
                source_step = step.input_ref.split(".", 1)[0]
                source_references = tuple(
                    dict.fromkeys(record.reference for record in outputs[source_step].records)
                )
                if not source_references:
                    result = CanonicalRecallResult(
                        operation=CanonicalRecallOperation(step.operation),
                        status=CanonicalRecallStatus.READY,
                        records=(),
                        reason_code="canonical_dependency_empty",
                    )
                    outputs[step.id] = result
                    executions.append(
                        CanonicalPlanStepExecution(
                            step_id=step.id,
                            query=None,
                            result=result,
                            dependency_short_circuited=True,
                        )
                    )
                    continue

            counterpart_ref = parameters.get("counterpart_ref")
            entity_ref = parameters.get("entity_ref")
            limit_value = parameters.get("limit", context.row_limit)
            if isinstance(limit_value, bool) or not isinstance(limit_value, int):
                raise CanonicalPlanContractError("canonical_plan_limit_invalid")
            query = CanonicalRecallQuery(
                operation=CanonicalRecallOperation(step.operation),
                scope=context.scope,
                text=_optional_parameter(parameters, "search_text", str),
                counterpart_world_character_id=(
                    None
                    if counterpart_ref is None
                    else entity_bindings[str(counterpart_ref)]
                ),
                thread_id=(
                    context.thread_id
                    if parameters.get("current_thread") is True
                    else None
                ),
                source_references=source_references,
                world_character_references=(
                    ()
                    if entity_ref is None
                    else (entity_bindings[str(entity_ref)],)
                ),
                occurred_from=context.occurred_from,
                occurred_to=context.occurred_to,
                limit=min(limit_value, context.row_limit),
            )
            result = self._recall.execute(query, now=now)
            outputs[step.id] = result
            executions.append(
                CanonicalPlanStepExecution(
                    step_id=step.id,
                    query=query,
                    result=result,
                )
            )

        return CanonicalPlanExecutionResult(
            request_id=context.request_id,
            plan=validated.plan,
            steps=tuple(executions),
            limit_clamped_steps=validated.limit_clamped_steps,
        )


def _optional_parameter(
    parameters: dict[str, str | int | bool],
    key: str,
    expected_type: type,
):
    value = parameters.get(key)
    if value is None:
        return None
    if not isinstance(value, expected_type):
        raise CanonicalPlanContractError(f"canonical_plan_{key}_invalid")
    return value


__all__ = [
    "CanonicalPlanExecutionContext",
    "CanonicalPlanExecutionResult",
    "CanonicalPlanStepExecution",
    "CanonicalPlanValidationResult",
    "CanonicalRetrievalPlanExecutor",
    "CanonicalRetrievalPlanValidator",
]
