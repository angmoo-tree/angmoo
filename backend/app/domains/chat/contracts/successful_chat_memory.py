"""After-commit boundary from successful Chat responses to Memory candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SuccessfulChatMemorySource:
    """Canonical identifiers for one already-committed assistant response."""

    request_id: str
    owner_id: str
    world_id: str
    subject_world_character_id: str
    assistant_message_id: int


class SuccessfulChatMemoryProducerPort(Protocol):
    """Propose a provider-free candidate without owning the Chat commit."""

    def propose_after_commit(self, source: SuccessfulChatMemorySource) -> None: ...


__all__ = ["SuccessfulChatMemoryProducerPort", "SuccessfulChatMemorySource"]
