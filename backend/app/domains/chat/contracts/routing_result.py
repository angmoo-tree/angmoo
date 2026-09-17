"""Typed routing and resolution results shared with Chat execution."""

from dataclasses import dataclass
from app.domains.chat.contracts.recall_interpretation import RecallInterpretationContext
from app.domains.chat.contracts.supervisor_selection import SelectionToolCall

from app.domains.chat.contracts.resolved_envelope import ResolvedRetrievalEnvelope
from app.domains.chat.contracts.retrieval_intent import (
    RetrievalIntentEnvelope,
    RetrievalRoute,
)


@dataclass(frozen=True, slots=True)
class ClarificationCandidate:
    ref: str
    display_name: str
    handle: str


@dataclass(frozen=True, slots=True)
class ClarificationResolution:
    slot: str
    candidates: tuple[ClarificationCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class RetrievalRoutingMetrics:
    route: RetrievalRoute
    router_proposed_route: RetrievalRoute
    sufficiency_guard_reason: str | None
    first_pass_valid: bool
    repair_used: bool
    rejected: bool
    clarification: bool
    entity_resolution_outcome: str
    direction_resolution_outcome: str
    time_resolution_outcome: str
    router_logical_calls: int
    router_physical_attempts: int
    provider: str
    model: str
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    thought_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None
    thinking_level: str | None = None
    max_output_tokens: int | None = None
    finish_reason: str | None = None
    admission_policy: str = "legacy"
    route_change_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalRoutingResult:
    intent: RetrievalIntentEnvelope
    resolved: ResolvedRetrievalEnvelope
    clarification: ClarificationResolution | None
    metrics: RetrievalRoutingMetrics
    call_tracker: dict
    proposed_tool_calls: tuple[SelectionToolCall, ...] = ()
    selection_mode: str = "legacy"
    interpretation: RecallInterpretationContext | None = None

    def __post_init__(self):
        if self.interpretation is not None:
            self.interpretation.assert_routing(self.intent, self.resolved)
