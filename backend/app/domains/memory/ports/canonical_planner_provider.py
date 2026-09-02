"""Provider-neutral Canonical Retrieval Planner port."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.memory.domain.canonical_retrieval_plan import (
    CanonicalPlanContractError,
    CanonicalRetrievalPlan,
)

MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS = 4_000


class CanonicalPlannerOutputError(CanonicalPlanContractError):
    """Typed provider output failure eligible for request-wide repair."""

    def __init__(
        self,
        diagnostic: str,
        *,
        physical_attempt_count: int = 1,
    ) -> None:
        if physical_attempt_count < 1 or physical_attempt_count > 2:
            raise CanonicalPlanContractError(
                "canonical_planner_physical_attempt_invalid"
            )
        super().__init__("canonical_planner_output_invalid")
        self.diagnostic = diagnostic[:160]
        self.physical_attempt_count = physical_attempt_count


@dataclass(frozen=True, slots=True)
class CanonicalPlannerEntity:
    ref: str
    mention: str
    role: str

    def __post_init__(self) -> None:
        if not self.ref or not self.mention.strip() or not self.role.strip():
            raise CanonicalPlanContractError("canonical_planner_entity_invalid")
        if len(self.ref) > 64 or len(self.mention) > 160 or len(self.role) > 64:
            raise CanonicalPlanContractError("canonical_planner_entity_invalid")


@dataclass(frozen=True, slots=True)
class CanonicalPlannerRelationship:
    from_ref: str
    to_ref: str
    dimension: str | None = None
    requested_polarity: str | None = None

    def __post_init__(self) -> None:
        if not self.from_ref or not self.to_ref or self.from_ref == self.to_ref:
            raise CanonicalPlanContractError(
                "canonical_planner_relationship_invalid"
            )


@dataclass(frozen=True, slots=True)
class CanonicalPlannerRequest:
    """Bounded semantic input; no canonical owner/World/Character ID exists."""

    request_id: str
    envelope_version: str
    envelope_hash: str
    user_message: str
    intent: str
    entities: tuple[CanonicalPlannerEntity, ...] = ()
    relationship: CanonicalPlannerRelationship | None = None
    resolved_time_available: bool = False
    aggregation_kind: str | None = None
    aggregation_target: str | None = None
    repair_diagnostic: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id or len(self.request_id) > 128:
            raise CanonicalPlanContractError("canonical_planner_request_id_invalid")
        if not self.envelope_version or len(self.envelope_version) > 64:
            raise CanonicalPlanContractError(
                "canonical_planner_envelope_version_invalid"
            )
        if len(self.envelope_hash) != 64:
            raise CanonicalPlanContractError("canonical_planner_envelope_hash_invalid")
        if not self.user_message.strip() or (
            len(self.user_message) > MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS
        ):
            raise CanonicalPlanContractError("canonical_planner_message_invalid")
        if not self.intent.strip() or len(self.intent) > 96:
            raise CanonicalPlanContractError("canonical_planner_intent_invalid")
        if len(self.entities) > 4 or len({item.ref for item in self.entities}) != len(
            self.entities
        ):
            raise CanonicalPlanContractError("canonical_planner_entities_invalid")
        if (self.aggregation_kind is None) != (self.aggregation_target is None):
            raise CanonicalPlanContractError(
                "canonical_planner_aggregation_incomplete"
            )
        if self.repair_diagnostic is not None and (
            not self.repair_diagnostic.strip()
            or len(self.repair_diagnostic) > 160
        ):
            raise CanonicalPlanContractError(
                "canonical_planner_repair_diagnostic_invalid"
            )


@dataclass(frozen=True, slots=True)
class CanonicalPlannerProviderResult:
    plan: CanonicalRetrievalPlan
    provider: str
    model: str
    physical_attempt_count: int
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        if self.physical_attempt_count < 1 or self.physical_attempt_count > 2:
            raise CanonicalPlanContractError(
                "canonical_planner_physical_attempt_invalid"
            )


class CanonicalPlannerProviderPort(Protocol):
    async def plan(
        self,
        request: CanonicalPlannerRequest,
    ) -> CanonicalPlannerProviderResult: ...


__all__ = [
    "MAX_CANONICAL_PLANNER_MESSAGE_CHARACTERS",
    "CanonicalPlannerEntity",
    "CanonicalPlannerOutputError",
    "CanonicalPlannerProviderPort",
    "CanonicalPlannerProviderResult",
    "CanonicalPlannerRelationship",
    "CanonicalPlannerRequest",
]
