"""Source validation values shared by runtime adapters and Memory owners."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry, SituationValidationContext
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence


@dataclass(frozen=True)
class SituationSourceAccess:
    state: Literal["available", "deleted", "changed", "forbidden"]
    evidence: CanonicalMemoryEvidence | None = None
    reason: str | None = None
    proof_origin: str | None = None


class SituationSourceValidator(Protocol):
    def validate(self, context: SituationValidationContext, source: DeliveredSourceEntry,
                 *, now: datetime) -> SituationSourceAccess: ...
