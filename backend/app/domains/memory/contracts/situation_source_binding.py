"""Typed, immutable evidence for a narrowly defined historic SNS parent binding."""
from dataclasses import dataclass
from datetime import datetime
from app.domains.memory.contracts.activity_situation import (
    DeliveredSourceEntry, stable_digest, SituationSourceBinding, PARENT_BINDING_POLICY,
)



@dataclass(frozen=True)
class CanonicalParentBindingBasis:
    child: DeliveredSourceEntry
    child_current_digest: str
    child_parent_id: str | None
    child_created_at: datetime
    parent: DeliveredSourceEntry
    parent_body_digest: str
    parent_created_at: datetime
    parent_accessible: bool
