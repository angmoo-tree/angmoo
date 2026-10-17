"""Request-local immutable recall binding, with a fresh read at each boundary."""
from datetime import datetime
from typing import Protocol

from app.domains.chat.contracts.evidence_bundle import EvidenceBundle
from app.domains.chat.contracts.retrieval_intent import RetrievalContractError


class RecallEvidenceChanged(RetrievalContractError):
    pass


class RecallCurrentnessPort(Protocol):
    async def assert_current(self, bundle: EvidenceBundle, *, deadline_at: datetime) -> None: ...
