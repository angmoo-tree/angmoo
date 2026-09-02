"""Provider-neutral Character Response Generator boundary."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Protocol

from app.domains.chat.domain.evidence_bundle import EvidenceBundle


class CharacterResponseGeneratorError(RuntimeError):
    def __init__(
        self,
        failure_class: str,
        *,
        retryable: bool,
        physical_attempt_count: int = 1,
        provider_diagnostic: Mapping[str, Any] | None = None,
    ) -> None:
        if not failure_class or not 1 <= physical_attempt_count <= 2:
            raise ValueError("character_response_error_invalid")
        super().__init__(failure_class)
        self.failure_class = failure_class
        self.retryable = retryable
        self.physical_attempt_count = physical_attempt_count
        self.call_tracker: dict[str, Any] | None = None
        self.provider_diagnostic = (
            None if provider_diagnostic is None else dict(provider_diagnostic)
        )


@dataclass(frozen=True, slots=True)
class CharacterResponseProfile:
    name: str
    handle: str
    one_liner: str
    personality: str
    speech_style: str
    worldview: str
    topic_preferences: str
    safety_rules: str


@dataclass(frozen=True, slots=True)
class CharacterResponseContextMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"} or not self.content.strip():
            raise ValueError("character_response_context_invalid")


@dataclass(frozen=True, slots=True)
class CharacterResponseGeneratorRequest:
    user_message: str
    profile: CharacterResponseProfile
    recent_context: tuple[CharacterResponseContextMessage, ...]
    evidence: EvidenceBundle
    clarification_candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.user_message.strip() or len(self.user_message) > 4_000:
            raise ValueError("character_response_message_invalid")
        if len(self.recent_context) > 24:
            raise ValueError("character_response_context_limit_exceeded")
        if len(self.clarification_candidates) > 8:
            raise ValueError("character_response_clarification_limit_exceeded")


@dataclass(frozen=True, slots=True)
class CharacterResponseGeneratorResult:
    text: str
    provider: str
    model: str
    physical_attempt_count: int = 1

    def __post_init__(self) -> None:
        if (
            not self.text.strip()
            or len(self.text) > 16_000
            or not self.provider
            or not self.model
            or not 1 <= self.physical_attempt_count <= 2
        ):
            raise ValueError("character_response_result_invalid")


class CharacterResponseGeneratorPort(Protocol):
    async def generate(
        self,
        request: CharacterResponseGeneratorRequest,
    ) -> CharacterResponseGeneratorResult: ...


__all__ = [
    "CharacterResponseContextMessage",
    "CharacterResponseGeneratorPort",
    "CharacterResponseGeneratorError",
    "CharacterResponseGeneratorRequest",
    "CharacterResponseGeneratorResult",
    "CharacterResponseProfile",
]
