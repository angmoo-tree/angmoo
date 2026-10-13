"""Same-UoW participation and delivered-input capture supplied by runtime."""
from __future__ import annotations
from typing import Protocol, TYPE_CHECKING
from app.contracts.activity_situation import SituationDelivery
if TYPE_CHECKING:
    from app.domains.chat.contracts.response_execution import ResponseWorkflowCommand
    from app.domains.chat.contracts.response_request import ResponseRequestRecord
    from app.domains.chat.contracts.character_response_generator import CharacterResponseGenerationResult
    from app.domains.chat.contracts.evidence_bundle import EvidenceBundle


class ChatSituationMemoryPort(Protocol):
    def freeze(self, command: ResponseWorkflowCommand, bundle: EvidenceBundle, payload: dict) -> SituationDelivery: ...
    def admit(self, command: ResponseWorkflowCommand, committed: ResponseRequestRecord, response: CharacterResponseGenerationResult) -> None: ...
