"""Request-local Chat execution values; no graph SDK or persistence policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypedDict

from app.domains.chat.contracts.character_response_generator import (
    CharacterResponseContextMessage,
    CharacterResponseGenerationResult,
    CharacterResponseProfile,
)
from app.domains.chat.contracts.evidence_bundle import EvidenceBundle
from app.domains.chat.contracts.generation_lifecycle import GenerationContractError
from app.domains.chat.contracts.response_request import ResponseRequestRecord
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand
from app.domains.chat.contracts.retrieval_router_provider import (
    RetrievalRouterContextMessage,
)
from app.domains.chat.contracts.routing_result import RetrievalRoutingResult
from app.domains.chat.contracts.today_sns_activity import TodaySnsActivitySnapshot
from app.domains.chat.contracts.workflow_recipe import WorkflowRecipe
from app.domains.chat.contracts.recall_mode import ChatRecallMode
from app.domains.relationships.contracts.social_context import SocialContextSnapshot


class ResponseExecutionError(GenerationContractError):
    """A closed, non-retryable execution contract error."""


class ResponsePhase(StrEnum):
    ROUTE = "route_required"
    BRANCH = "branch_required"
    EVIDENCE = "evidence_required"
    RESPONSE = "response_required"
    COMPLETE = "graph_complete"


class ResponseAction(StrEnum):
    ROUTE = "route_and_resolve"
    CURRENT = "current_context"
    CANONICAL = "canonical_retrieval"
    GRAPH = "graph_retrieval"
    BOTH = "both_retrieval"
    CLARIFY = "clarification"
    FREEZE = "freeze_evidence"
    GENERATE = "generate_response"
    END = "end"


@dataclass(frozen=True, slots=True)
class ResponseWorkflowCommand:
    request: ResponseRequestRecord
    preflight: RetrievalPreflightCommand
    profile: CharacterResponseProfile
    router_context: tuple[RetrievalRouterContextMessage, ...]
    response_context: tuple[CharacterResponseContextMessage, ...]
    character_labels: Mapping[str, str]
    today_sns_snapshot: TodaySnsActivitySnapshot | None = None
    graph_projection_enabled: bool = True
    lease_seconds: int = 180
    recall_mode: ChatRecallMode = ChatRecallMode.LEGACY
    social_snapshot: SocialContextSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.recall_mode, ChatRecallMode):
            raise RetrievalContractError("chat_recall_mode_invalid")
        if self.social_snapshot is not None and (
            self.social_snapshot.scope.owner_id != self.preflight.owner_id
            or self.social_snapshot.scope.world_id != self.preflight.world_id
            or self.social_snapshot.scope.subject_world_character_id != self.preflight.responding_world_character_id
        ):
            raise RetrievalContractError("chat_social_snapshot_scope_mismatch")
        if self.request.request_id != self.preflight.request_id:
            raise RetrievalContractError("response_workflow_request_mismatch")
        if self.request.thread_id != self.preflight.thread_id:
            raise RetrievalContractError("response_workflow_thread_mismatch")
        if self.today_sns_snapshot is not None and (
            self.today_sns_snapshot.owner_id != self.preflight.owner_id
            or self.today_sns_snapshot.world_id != self.preflight.world_id
            or self.today_sns_snapshot.subject_world_character_id
            != self.preflight.responding_world_character_id
        ):
            raise RetrievalContractError("response_workflow_today_scope_mismatch")
        if not 30 <= self.lease_seconds <= 300:
            raise RetrievalContractError("response_workflow_lease_invalid")


class ResponseGraphState(TypedDict):
    request_id: str
    request_scope_hash: str
    phase: ResponsePhase
    visits: int
    action: ResponseAction | None
    routing: RetrievalRoutingResult | None
    bundle: EvidenceBundle | None
    response: CharacterResponseGenerationResult | None
    workflow_recipe: WorkflowRecipe | None


def initial_response_state(record: ResponseRequestRecord) -> ResponseGraphState:
    return ResponseGraphState(
        request_id=record.request_id,
        request_scope_hash=record.request_scope_hash,
        phase=ResponsePhase.ROUTE,
        visits=0,
        action=None,
        routing=None,
        bundle=None,
        response=None,
        workflow_recipe=None,
    )


class ResponseStepRunner(Protocol):
    def assert_active(self, state: ResponseGraphState) -> None: ...

    async def execute(
        self, action: ResponseAction, state: ResponseGraphState
    ) -> ResponseGraphState: ...


class ResponseGraphExecutor(Protocol):
    async def run(
        self, state: ResponseGraphState, steps: ResponseStepRunner
    ) -> ResponseGraphState: ...
