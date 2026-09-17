"""Bounded policy constants for canonical and World-scoped Chat."""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.chat.contracts.character_response_generator import (
    CharacterResponseGenerationResult,
)
from app.domains.chat.contracts.evidence_bundle import EvidenceBundle
from app.domains.chat.contracts.response_execution import (
    ResponseAction,
    ResponseExecutionError,
    ResponseGraphState,
    ResponsePhase,
)
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.domains.chat.contracts.routing_result import RetrievalRoutingResult

MAX_ACTIVE_THREADS = 5
CONTEXT_MESSAGE_LIMIT = 20
CONTEXT_CHAR_LIMIT = 12_000
USER_MESSAGE_LIMIT = 2_000
MODEL_OUTPUT_TOKENS = 1024
DEFAULT_MESSAGE_MODEL = "gemini-3.1-flash-lite"
MESSAGE_RESPONSE_LEASE_SECONDS = 150
WORLD_CHAT_FOREGROUND_MAX_OUTPUT_TOKENS = 3_072

THREAD_LIMIT_MESSAGE = "쪽지는 최대 5개까지 보관할 수 있습니다. 쪽지함에서 기존 쪽지 내역을 삭제한 뒤 다시 시작해주세요."
MODEL_BUSY_MESSAGE = "현재 선택한 모델이 바쁘거나 응답하지 않습니다. 잠시 뒤 다시 시도하거나 다른 모델로 바꿔서 시도해주세요."
API_KEY_INVALID_MESSAGE = "API key를 확인해주세요."
API_KEY_MISSING_MESSAGE = "쪽지를 시작하려면 API key를 등록해주세요."
CHARACTER_DISABLED_MESSAGE = "이 앵무는 아직 쪽지를 받을 수 없습니다."
LOCAL_CHARACTER_MESSAGES_DISABLED_MESSAGE = "외부 연결 앵무는 쪽지를 받을 수 없습니다."
PROMPT_INJECTION_BLOCKED_MESSAGE = (
    "그건 말해줄 수 없지만, 다른 이야기는 편하게 해도 돼."
)

MESSAGE_MODELS = {"gemini-3.1-flash-lite", "gemini-3.5-flash-lite"}


@dataclass(frozen=True, slots=True)
class MessageModelExecutionPolicy:
    """Provider-neutral execution intent for one foreground Chat model."""

    model: str
    thinking_level: str | None
    max_output_tokens: int = WORLD_CHAT_FOREGROUND_MAX_OUTPUT_TOKENS


def resolve_world_chat_model_execution_policy(
    model: str,
    thinking_level: str = "high",
) -> MessageModelExecutionPolicy:
    """Fail closed while keeping Gemini-family transport details out of Chat."""

    normalized = model.strip().lower()
    if normalized not in MESSAGE_MODELS:
        raise ValueError("world_chat_message_model_unsupported")
    if thinking_level not in {"high", "medium"}:
        raise ValueError("world_chat_thinking_level_unsupported")
    return MessageModelExecutionPolicy(
        model=normalized,
        thinking_level=thinking_level,
    )


BRANCH_ACTIONS = {
    RetrievalRoute.CURRENT_CONTEXT: ResponseAction.CURRENT,
    RetrievalRoute.CANONICAL: ResponseAction.CANONICAL,
    RetrievalRoute.GRAPH: ResponseAction.GRAPH,
    RetrievalRoute.BOTH: ResponseAction.BOTH,
    RetrievalRoute.CLARIFICATION: ResponseAction.CLARIFY,
}
_PHASE_VISITS = {phase: index for index, phase in enumerate(ResponsePhase)}


def select_response_action(state: ResponseGraphState) -> ResponseAction:
    """Select exactly one action; completion requires validated results."""
    visits = state.get("visits")
    if type(visits) is not int or visits < 0:
        raise ResponseExecutionError("chat_supervisor_invalid_state")
    if visits >= len(ResponsePhase):
        raise ResponseExecutionError("chat_supervisor_step_limit")
    phase = state.get("phase")
    if not isinstance(phase, ResponsePhase) or _PHASE_VISITS[phase] != visits:
        raise ResponseExecutionError("chat_supervisor_invalid_state")
    routing, bundle, response = (
        state.get("routing"),
        state.get("bundle"),
        state.get("response"),
    )
    if phase is ResponsePhase.ROUTE:
        if any(
            value is not None
            for value in (
                routing,
                bundle,
                response,
                state.get("action"),
                state.get("workflow_recipe"),
            )
        ):
            raise ResponseExecutionError("chat_supervisor_invalid_state")
        return ResponseAction.ROUTE
    if not isinstance(routing, RetrievalRoutingResult) or (
        routing.resolved.request_id != state.get("request_id")
        or routing.intent.route not in BRANCH_ACTIONS
    ):
        raise ResponseExecutionError("chat_supervisor_invalid_state")
    route = routing.intent.route
    if phase is ResponsePhase.BRANCH:
        if (
            bundle is not None
            or response is not None
            or state.get("action") is not ResponseAction.ROUTE
        ):
            raise ResponseExecutionError("chat_supervisor_invalid_state")
        return BRANCH_ACTIONS[route]
    if not isinstance(bundle, EvidenceBundle) or (
        bundle.request_id != state.get("request_id")
        or bundle.request_scope_hash != state.get("request_scope_hash")
        or bundle.route is not route
    ):
        raise ResponseExecutionError("chat_supervisor_invalid_state")
    if phase is ResponsePhase.EVIDENCE:
        if response is not None or state.get("action") is not BRANCH_ACTIONS[route]:
            raise ResponseExecutionError("chat_supervisor_invalid_state")
        return ResponseAction.FREEZE
    if phase is ResponsePhase.RESPONSE:
        if response is not None or state.get("action") is not ResponseAction.FREEZE:
            raise ResponseExecutionError("chat_supervisor_invalid_state")
        return ResponseAction.GENERATE
    if not isinstance(response, CharacterResponseGenerationResult) or (
        not response.text.strip() or state.get("action") is not ResponseAction.GENERATE
    ):
        raise ResponseExecutionError("chat_supervisor_invalid_state")
    return ResponseAction.END
