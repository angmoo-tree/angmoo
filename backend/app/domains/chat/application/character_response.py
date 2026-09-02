"""Exactly-once logical Character Response Generator use case."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.domains.chat.domain.call_tracker import (
    LlmNode,
    restore_call_tracker_snapshot,
)
from app.domains.chat.domain.retrieval_intent import RetrievalContractError
from app.domains.chat.ports.character_response_generator import (
    CharacterResponseGeneratorError,
    CharacterResponseGeneratorPort,
    CharacterResponseGeneratorRequest,
)


@dataclass(frozen=True, slots=True)
class CharacterResponseGenerationResult:
    text: str
    provider: str
    model: str
    call_tracker: dict[str, Any]


class CharacterResponseGenerationService:
    def __init__(self, generator: CharacterResponseGeneratorPort) -> None:
        self._generator = generator

    @staticmethod
    def reserve_call(
        *,
        call_tracker: Mapping[str, Any],
        now: datetime,
        deadline_at: datetime,
    ) -> dict[str, Any]:
        """Fence the exactly-once logical CRG call before provider I/O."""

        if now.tzinfo is None or deadline_at.tzinfo is None:
            raise RetrievalContractError("character_response_deadline_timezone_required")
        tracker = restore_call_tracker_snapshot(
            call_tracker,
            deadline_at=deadline_at,
        )
        tracker.record_logical_call(
            LlmNode.CHARACTER_RESPONSE_GENERATOR,
            now=now,
        )
        return tracker.snapshot()

    async def generate(
        self,
        request: CharacterResponseGeneratorRequest,
        *,
        call_tracker: Mapping[str, Any],
        now: datetime,
        deadline_at: datetime,
    ) -> CharacterResponseGenerationResult:
        if now.tzinfo is None or deadline_at.tzinfo is None:
            raise RetrievalContractError("character_response_deadline_timezone_required")
        tracker = restore_call_tracker_snapshot(
            call_tracker,
            deadline_at=deadline_at,
        )
        if tracker.route is not request.evidence.route:
            raise RetrievalContractError("character_response_route_mismatch")
        if tracker.logical_counts[LlmNode.CHARACTER_RESPONSE_GENERATOR] != 1:
            raise RetrievalContractError("character_response_call_not_reserved")
        try:
            result = await self._generator.generate(request)
        except CharacterResponseGeneratorError as exc:
            for _ in range(exc.physical_attempt_count):
                tracker.record_physical_attempt(
                    LlmNode.CHARACTER_RESPONSE_GENERATOR,
                    now=datetime.now(UTC),
                )
            exc.call_tracker = tracker.snapshot()
            raise
        for _ in range(result.physical_attempt_count):
            physical_now = datetime.now(UTC)
            tracker.record_physical_attempt(
                LlmNode.CHARACTER_RESPONSE_GENERATOR,
                now=physical_now,
            )
        text = result.text.strip()
        if not text:
            raise RetrievalContractError("character_response_empty")
        return CharacterResponseGenerationResult(
            text=text,
            provider=result.provider,
            model=result.model,
            call_tracker=tracker.snapshot(),
        )


def character_response_deltas(text: str, *, max_chars: int = 48) -> tuple[str, ...]:
    """Split only verified CRG text into bounded transport deltas."""

    if not text or not 1 <= max_chars <= 512:
        raise RetrievalContractError("character_response_delta_input_invalid")
    return tuple(text[index : index + max_chars] for index in range(0, len(text), max_chars))


__all__ = [
    "CharacterResponseGenerationResult",
    "CharacterResponseGenerationService",
    "character_response_deltas",
]
