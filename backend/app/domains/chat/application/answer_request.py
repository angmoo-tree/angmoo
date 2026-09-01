"""Provider-free P8-L-J workflow validation and bounded fake-node execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domains.chat.domain.call_tracker import LlmNode, RouteAwareCallTracker
from app.domains.chat.domain.resolved_envelope import ResolvedRetrievalEnvelope
from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalIntentEnvelope,
)
from app.domains.chat.domain.workflow_recipe import RetrievalWorkflow
from app.domains.memory.public import CANONICAL_PRIMITIVE_REGISTRY
from app.domains.relationships.public import GRAPH_RECALL_PRIMITIVE_REGISTRY


@dataclass(frozen=True, slots=True)
class FakeAnswerRequestResult:
    request_id: str
    route: str
    executed_nodes: tuple[str, ...]
    tracker: dict
    provider_calls: int = 0


class AnswerRequestContractValidator:
    """Bind strict plans to the resolved envelope and H/I primitive registries."""

    def validate(
        self,
        *,
        intent: RetrievalIntentEnvelope,
        resolved: ResolvedRetrievalEnvelope,
        workflow: RetrievalWorkflow,
    ) -> None:
        if intent.envelope_hash != resolved.intent_hash:
            raise RetrievalContractError("answer_request_intent_hash_mismatch")
        if intent.route is not workflow.route:
            raise RetrievalContractError("answer_request_route_mismatch")
        if workflow.request_id != resolved.request_id:
            raise RetrievalContractError("answer_request_request_id_mismatch")
        if (
            workflow.envelope_version != resolved.version
            or workflow.envelope_hash != resolved.envelope_hash
        ):
            raise RetrievalContractError("answer_request_resolved_envelope_mismatch")
        intent_refs = {entity.ref for entity in intent.entities}
        resolved_refs = {binding.ref for binding in resolved.entity_bindings}
        if not intent_refs <= resolved_refs:
            raise RetrievalContractError("answer_request_entity_binding_missing")

        canonical_registry = {operation.value for operation in CANONICAL_PRIMITIVE_REGISTRY}
        graph_registry = {operation.value for operation in GRAPH_RECALL_PRIMITIVE_REGISTRY}
        if workflow.canonical_plan is not None:
            for step in workflow.canonical_plan.steps:
                if (
                    step.operation not in canonical_registry
                    or step.operation not in resolved.canonical_operation_allowlist
                    or step.operation in graph_registry
                ):
                    raise RetrievalContractError("canonical_plan_operation_forbidden")
        if workflow.graph_plan is not None:
            for step in workflow.graph_plan.steps:
                if (
                    step.operation not in graph_registry
                    or step.operation not in resolved.graph_operation_allowlist
                    or step.operation in canonical_registry
                ):
                    raise RetrievalContractError("graph_plan_operation_forbidden")


class BoundedFakeAnswerRequestExecutor:
    """Exercise topology and budgets without making Router/Planner/CRG calls."""

    def __init__(self, validator: AnswerRequestContractValidator | None = None) -> None:
        self._validator = validator or AnswerRequestContractValidator()

    def execute(
        self,
        *,
        intent: RetrievalIntentEnvelope,
        resolved: ResolvedRetrievalEnvelope,
        workflow: RetrievalWorkflow,
        deadline_at: datetime,
        now: datetime,
        repair_node: LlmNode | None = None,
        physical_attempts_per_node: int = 1,
    ) -> FakeAnswerRequestResult:
        self._validator.validate(intent=intent, resolved=resolved, workflow=workflow)
        tracker = RouteAwareCallTracker(route=intent.route, deadline_at=deadline_at)
        executed: list[LlmNode] = []

        nodes = [LlmNode.RETRIEVAL_ROUTER]
        if workflow.canonical_plan is not None:
            nodes.append(LlmNode.CANONICAL_PLANNER)
        if workflow.graph_plan is not None:
            nodes.append(LlmNode.GRAPH_PLANNER)
        nodes.append(LlmNode.CHARACTER_RESPONSE_GENERATOR)

        for node in nodes:
            tracker.record_logical_call(node, now=now)
            executed.append(node)
            for _attempt in range(physical_attempts_per_node):
                tracker.record_physical_attempt(node, now=now)
            if repair_node is node:
                tracker.record_logical_call(node, now=now, repair=True)
                executed.append(node)
                for _attempt in range(physical_attempts_per_node):
                    tracker.record_physical_attempt(node, now=now)

        return FakeAnswerRequestResult(
            request_id=resolved.request_id,
            route=intent.route.value,
            executed_nodes=tuple(node.value for node in executed),
            tracker=tracker.snapshot(),
            provider_calls=0,
        )


__all__ = [
    "AnswerRequestContractValidator",
    "BoundedFakeAnswerRequestExecutor",
    "FakeAnswerRequestResult",
]
