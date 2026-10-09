"""Typed, immutable evidence for a narrowly defined historic SNS parent binding."""
from dataclasses import asdict, dataclass
from datetime import datetime
from app.domains.memory.contracts.activity_situation import DeliveredSourceEntry, stable_digest

PARENT_BINDING_POLICY = "sns-today-parent-binding.v1"


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


@dataclass(frozen=True)
class SituationSourceBinding:
    manifest_id: str
    entry_ordinal: int
    resolution_policy: str
    original_entry_digest: str
    basis_ordinal: int
    basis_source_id: str
    basis_source_digest: str
    resolved_source: DeliveredSourceEntry
    resolved_at: str
    resolution_digest: str

    def material(self):
        value = asdict(self)
        value.pop("resolution_digest")
        return value

    def check_integrity(self):
        if self.resolution_policy != PARENT_BINDING_POLICY or stable_digest(self.material()) != self.resolution_digest:
            raise ValueError("situation_parent_binding_integrity_invalid")
