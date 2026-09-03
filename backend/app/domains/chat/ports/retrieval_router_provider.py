"""Provider-neutral Retrieval Router port owned by the Chat domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.chat.domain.retrieval_intent import (
    RetrievalContractError,
    RetrievalIntentEnvelope,
)
from app.domains.chat.domain.retrieval_router import normalize_router_validation_code


MAX_ROUTER_CONTEXT_MESSAGES = 20
MAX_ROUTER_CONTEXT_CHARACTERS = 12_000
MAX_ROUTER_MESSAGE_CHARACTERS = 4_000


class RetrievalRouterOutputError(RetrievalContractError):
    """Typed schema/semantic output failure that may consume one repair token."""

    def __init__(
        self,
        validation_code: str,
        *,
        physical_attempt_count: int = 1,
    ) -> None:
        if physical_attempt_count < 1 or physical_attempt_count > 2:
            raise RetrievalContractError("retrieval_router_physical_attempt_invalid")
        super().__init__("retrieval_router_output_invalid")
        self.validation_code = normalize_router_validation_code(validation_code)
        # Compatibility alias for the existing repair request field.  The value
        # is now always an allowlisted stable code, never arbitrary exception text.
        self.diagnostic = self.validation_code
        self.physical_attempt_count = physical_attempt_count


@dataclass(frozen=True, slots=True)
class RetrievalRouterContextMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"}:
            raise RetrievalContractError("retrieval_router_context_role_invalid")
        content = self.content.strip()
        if not content or len(content) > MAX_ROUTER_MESSAGE_CHARACTERS:
            raise RetrievalContractError("retrieval_router_context_content_invalid")


@dataclass(frozen=True, slots=True)
class RetrievalRouterRequest:
    """Bounded semantic input; canonical identifiers are deliberately absent."""

    user_message: str
    recent_context: tuple[RetrievalRouterContextMessage, ...] = ()
    responding_character_name: str | None = None
    world_language: str = "ko"
    repair_diagnostic: str | None = None

    def __post_init__(self) -> None:
        message = self.user_message.strip()
        if not message or len(message) > MAX_ROUTER_MESSAGE_CHARACTERS:
            raise RetrievalContractError("retrieval_router_message_invalid")
        if len(self.recent_context) > MAX_ROUTER_CONTEXT_MESSAGES:
            raise RetrievalContractError("retrieval_router_context_count_exceeded")
        if sum(len(item.content) for item in self.recent_context) > MAX_ROUTER_CONTEXT_CHARACTERS:
            raise RetrievalContractError("retrieval_router_context_size_exceeded")
        if self.responding_character_name is not None and (
            not self.responding_character_name.strip()
            or len(self.responding_character_name) > 160
        ):
            raise RetrievalContractError("retrieval_router_character_name_invalid")
        if not self.world_language.strip() or len(self.world_language) > 16:
            raise RetrievalContractError("retrieval_router_language_invalid")
        if self.repair_diagnostic is not None and (
            not self.repair_diagnostic.strip() or len(self.repair_diagnostic) > 160
        ):
            raise RetrievalContractError("retrieval_router_repair_diagnostic_invalid")


@dataclass(frozen=True, slots=True)
class RetrievalRouterProviderResult:
    intent: RetrievalIntentEnvelope
    provider: str
    model: str
    physical_attempt_count: int
    prompt_token_count: int | None = None
    output_token_count: int | None = None
    total_token_count: int | None = None
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        if self.physical_attempt_count < 1 or self.physical_attempt_count > 2:
            raise RetrievalContractError("retrieval_router_physical_attempt_invalid")


class RetrievalRouterProviderPort(Protocol):
    async def route(
        self,
        request: RetrievalRouterRequest,
    ) -> RetrievalRouterProviderResult: ...


__all__ = [
    "MAX_ROUTER_CONTEXT_CHARACTERS",
    "MAX_ROUTER_CONTEXT_MESSAGES",
    "MAX_ROUTER_MESSAGE_CHARACTERS",
    "RetrievalRouterContextMessage",
    "RetrievalRouterOutputError",
    "RetrievalRouterProviderPort",
    "RetrievalRouterProviderResult",
    "RetrievalRouterRequest",
]
