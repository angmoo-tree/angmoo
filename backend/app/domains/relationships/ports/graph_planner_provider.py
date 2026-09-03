"""Provider-neutral Graph Retrieval Planner port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.relationships.domain.graph_retrieval_plan import (
    GraphPlanContractError,
    GraphRetrievalPlan,
)


MAX_GRAPH_PLANNER_MESSAGE_CHARACTERS = 4_000


class GraphPlannerOutputError(GraphPlanContractError):
    """Typed provider output failure eligible for request-wide repair."""

    def __init__(
        self,
        diagnostic: str,
        *,
        physical_attempt_count: int = 1,
    ) -> None:
        if physical_attempt_count < 1 or physical_attempt_count > 2:
            raise GraphPlanContractError("graph_planner_physical_attempt_invalid")
        super().__init__("graph_planner_output_invalid")
        self.diagnostic = diagnostic[:160]
        self.physical_attempt_count = physical_attempt_count


@dataclass(frozen=True, slots=True)
class GraphPlannerEntity:
    ref: str
    mention: str
    role: str

    def __post_init__(self) -> None:
        if not self.ref or not self.mention.strip() or not self.role.strip():
            raise GraphPlanContractError("graph_planner_entity_invalid")
        if len(self.ref) > 64 or len(self.mention) > 160 or len(self.role) > 64:
            raise GraphPlanContractError("graph_planner_entity_invalid")


@dataclass(frozen=True, slots=True)
class GraphPlannerRelationship:
    from_ref: str
    to_ref: str
    dimension: str | None = None
    requested_polarity: str | None = None

    def __post_init__(self) -> None:
        if not self.from_ref or not self.to_ref or self.from_ref == self.to_ref:
            raise GraphPlanContractError("graph_planner_relationship_invalid")


@dataclass(frozen=True, slots=True)
class GraphPlannerRequest:
    """Bounded semantic input; actual owner, World and graph IDs are absent."""

    request_id: str
    envelope_version: str
    envelope_hash: str
    user_message: str
    intent: str
    entities: tuple[GraphPlannerEntity, ...] = ()
    relationship: GraphPlannerRelationship | None = None
    aggregation_kind: str | None = None
    aggregation_target: str | None = None
    max_hops_hint: int = 3
    repair_diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 128:
            raise GraphPlanContractError("graph_planner_request_id_invalid")
        if not self.envelope_version or len(self.envelope_version) > 64:
            raise GraphPlanContractError("graph_planner_envelope_version_invalid")
        if len(self.envelope_hash) != 64:
            raise GraphPlanContractError("graph_planner_envelope_hash_invalid")
        if not self.user_message.strip() or (
            len(self.user_message) > MAX_GRAPH_PLANNER_MESSAGE_CHARACTERS
        ):
            raise GraphPlanContractError("graph_planner_message_invalid")
        if not self.intent.strip() or len(self.intent) > 96:
            raise GraphPlanContractError("graph_planner_intent_invalid")
        if len(self.entities) > 4 or len({item.ref for item in self.entities}) != len(
            self.entities
        ):
            raise GraphPlanContractError("graph_planner_entities_invalid")
        if (self.aggregation_kind is None) != (self.aggregation_target is None):
            raise GraphPlanContractError("graph_planner_aggregation_incomplete")
        if not 1 <= self.max_hops_hint <= 3:
            raise GraphPlanContractError("graph_planner_hop_hint_invalid")
        if self.repair_diagnostic is not None and (
            not self.repair_diagnostic.strip()
            or len(self.repair_diagnostic) > 160
        ):
            raise GraphPlanContractError("graph_planner_repair_diagnostic_invalid")


@dataclass(frozen=True, slots=True)
class GraphPlannerProviderResult:
    plan: GraphRetrievalPlan
    provider: str
    model: str
    physical_attempt_count: int
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    thought_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None
    thinking_level: str | None = None
    max_output_tokens: int | None = None
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        if self.physical_attempt_count < 1 or self.physical_attempt_count > 2:
            raise GraphPlanContractError("graph_planner_physical_attempt_invalid")


class GraphPlannerProviderPort(Protocol):
    async def plan(self, request: GraphPlannerRequest) -> GraphPlannerProviderResult: ...


__all__ = [
    "MAX_GRAPH_PLANNER_MESSAGE_CHARACTERS",
    "GraphPlannerEntity",
    "GraphPlannerOutputError",
    "GraphPlannerProviderPort",
    "GraphPlannerProviderResult",
    "GraphPlannerRelationship",
    "GraphPlannerRequest",
]
