"""Source validation values shared by runtime adapters and Memory owners."""
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry, SituationValidationContext
from app.domains.memory.contracts.source_evidence import CanonicalMemoryEvidence
from app.domains.memory.contracts.situation_source_binding import CanonicalParentBindingBasis


@dataclass(frozen=True)
class SituationSourceAccess:
    state: Literal["available", "deleted", "changed", "forbidden"]
    evidence: CanonicalMemoryEvidence | None = None
    reason: str | None = None
    proof_origin: str | None = None


class SituationSourceValidator(Protocol):
    def validate(self, context: SituationValidationContext, source: DeliveredSourceEntry,
                 *, now: datetime, validation=None) -> SituationSourceAccess: ...


@runtime_checkable
class SituationValidationPreparer(Protocol):
    """Optional batched canonical reads within one post-binding validation."""
    def prepare_validation(self, context: SituationValidationContext, *, validation) -> None: ...


@runtime_checkable
class SituationParentBindingResolver(Protocol):
    """Optional same-session canonical port; fixtures without it cannot infer."""
    def parent_binding_basis(self, context: SituationValidationContext,
                             original: DeliveredSourceEntry, *, child: DeliveredSourceEntry,
                             now: datetime) -> CanonicalParentBindingBasis: ...
