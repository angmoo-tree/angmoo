"""Versioned values for activity-owned situation admission; no I/O or commits."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Literal

from app.domains.memory.contracts.scope import MemoryScope
from app.contracts.activity_situation import SITUATION_POLICY, SituationDraft

PARENT_BINDING_POLICY = "sns-today-parent-binding.v1"
SITUATION_REPRESENTATION = "activity_situation_v1"
DESCRIPTION_LIMIT = 1000
DELIVERED_SOURCE_LIMIT = 256
SITUATION_BASIS_DOCUMENT_MAX_BYTES = 8 * 1024 * 1024
Lane = Literal["chat", "inbox", "feed", "routine"]
VALIDATION_REVISION = "situation-validation.v4"
PARENT_BINDING_REVISIONS = frozenset({"situation-validation.v3", VALIDATION_REVISION})
LEGACY_VALIDATION_REVISION = "situation-validation.v2"
SUPPORTED_VALIDATION_REVISIONS = frozenset({LEGACY_VALIDATION_REVISION, *PARENT_BINDING_REVISIONS})


@dataclass(frozen=True)
class RelationshipDeliveryBasis:
    state_id: str
    actor_id: str
    target_id: str
    version: int
    view_version: int
    facts_digest: str

    def __post_init__(self):
        if (not self.state_id or not self.actor_id or not self.target_id
                or type(self.version) is not int or self.version < 0
                or type(self.view_version) is not int or self.view_version < 0
                or len(self.facts_digest) != 64):
            raise ValueError("situation_relationship_basis_invalid")


@dataclass(frozen=True)
class FinalDeliveredFragment:
    """A bounded fragment located in the final code-owned provider payload."""
    payload_digest: str
    path: str
    text: str

    @classmethod
    def capture(cls, payload, *, path, text, payload_digest):
        value = payload
        if not path.startswith("/") or len(payload_digest) != 64:
            raise ValueError("situation_delivery_path_invalid")
        for part in path[1:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, (list, tuple)) else value[key]
        transmitted = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        if not isinstance(text, str) or not text or text not in transmitted:
            raise ValueError("situation_delivery_fragment_missing")
        return cls(payload_digest, path, text)


def stable_digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SituationPolicySnapshot:
    scope: MemoryScope
    setting_id: str
    activation_epoch: str
    scope_version: int
    memory_search_locale: str
    environment_revision: int = 0
    policy_version: str = SITUATION_POLICY

    def __post_init__(self):
        if (self.policy_version != SITUATION_POLICY or not self.setting_id
                or not self.activation_epoch or self.scope_version < 1
                or not self.memory_search_locale or len(self.memory_search_locale) > 80
                or self.environment_revision < 0):
            raise ValueError("situation_policy_snapshot_invalid")


@dataclass(frozen=True)
class DeliveredSourceEntry:
    source_type: str
    source_id: str
    source_version: str
    source_digest: str
    delivered_digest: str
    payload_path: str
    role: Literal["core", "background", "prior", "committed_result", "thought"]
    ordinal: int
    world_id: str
    target_key: str | None = None
    thread_id: str | None = None
    actor_id: str | None = None
    counterpart_id: str | None = None
    ranges: tuple[tuple[int, int], ...] = ()
    partial: bool = False
    transformation: str | None = None
    delivered_ranges: tuple[tuple[int, int], ...] = ()
    relationship_basis: RelationshipDeliveryBasis | None = None
    delivery_payload_digest: str | None = None

    def __post_init__(self):
        if (not self.source_type or not self.source_id or not self.payload_path
                or not self.world_id or self.ordinal < 0
                or any(len(value) != 64 for value in (self.source_digest, self.delivered_digest))
                or self.role not in {"core", "background", "prior", "committed_result", "thought"}
                or any(start < 0 or end < start for start, end in (*self.ranges, *self.delivered_ranges))
                or (self.delivered_ranges and len(self.ranges) != len(self.delivered_ranges))):
            raise ValueError("situation_source_invalid")
        if self.relationship_basis is not None and (
                self.source_type != "RELATIONSHIP" or self.role != "background"
                or self.relationship_basis.state_id != self.source_id
                or self.relationship_basis.actor_id != self.actor_id
                or self.relationship_basis.target_id != self.counterpart_id
                or str(self.relationship_basis.version) != self.source_version
                or self.relationship_basis.facts_digest != self.source_digest):
            raise ValueError("situation_relationship_basis_mismatch")
        if self.delivery_payload_digest is not None and len(self.delivery_payload_digest) != 64:
            raise ValueError("situation_delivery_digest_invalid")

    def to_dict(self, *, version=2):
        value = asdict(self)
        if version == 1:
            value.pop("relationship_basis", None)
            value.pop("delivery_payload_digest", None)
        return value

    @classmethod
    def from_dict(cls, value):
        material = dict(value)
        for field in ("ranges", "delivered_ranges"):
            material[field] = tuple(tuple(pair) for pair in material.get(field, ()))
        if material.get("relationship_basis") is not None:
            material["relationship_basis"] = RelationshipDeliveryBasis(**material["relationship_basis"])
        return cls(**material)


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



@dataclass(frozen=True)
class DeliveredInputManifest:
    call_identity: str
    snapshot: SituationPolicySnapshot
    payload_digest: str
    sources: tuple[DeliveredSourceEntry, ...]
    private_thread_id: str | None = None
    version: int = 1

    def __post_init__(self):
        threads = {row.thread_id for row in self.sources if row.thread_id}
        if (self.version not in {1, 2} or not self.call_identity or len(self.payload_digest) != 64
                or len(self.sources) > DELIVERED_SOURCE_LIMIT or len(threads) > 1
                or (threads and threads != {self.private_thread_id})
                or any(row.world_id != self.snapshot.scope.world_id for row in self.sources)
                or len({row.ordinal for row in self.sources}) != len(self.sources)):
            raise ValueError("situation_manifest_invalid")

    def to_dict(self) -> dict:
        value = asdict(self)
        if self.version == 1:
            for source in value["sources"]:
                source.pop("relationship_basis", None)
                source.pop("delivery_payload_digest", None)
        return value

    @classmethod
    def from_dict(cls, value: dict):
        snapshot = dict(value["snapshot"])
        snapshot["scope"] = MemoryScope(**snapshot["scope"])
        return cls(call_identity=value["call_identity"],
            snapshot=SituationPolicySnapshot(**snapshot), payload_digest=value["payload_digest"],
            sources=tuple(DeliveredSourceEntry.from_dict(row) for row in value["sources"]),
            private_thread_id=value.get("private_thread_id"), version=value["version"])


@dataclass(frozen=True)
class DeliveredObservationProof:
    receipt_sequence: int
    manifest_digest: str
    entry: DeliveredSourceEntry
    origin: Literal["situation_delivered", "committed_result", "situation_source_binding"]


@dataclass(frozen=True)
class SituationValidationContext:
    """Restored only from Memory's persisted receipt/manifest FK boundary."""
    manifest: DeliveredInputManifest
    receipt_sequence: int
    manifest_digest: str
    result_sources: tuple[DeliveredSourceEntry, ...]
    target_key: str
    logical_activity_id: str
    lane: Lane
    revision: str = VALIDATION_REVISION
    source_bindings: tuple[SituationSourceBinding, ...] = ()

    @property
    def snapshot(self):
        return self.manifest.snapshot

    @property
    def sources(self):
        replacements = {binding.entry_ordinal: binding.resolved_source for binding in self.source_bindings}
        return tuple(replacements.get(entry.ordinal, entry) for entry in self.manifest.sources)

    @property
    def private_thread_id(self):
        return self.manifest.private_thread_id

    @property
    def version(self):
        return self.manifest.version

    def proof_for(self, source):
        for binding in self.source_bindings:
            if binding.resolved_source == source:
                return DeliveredObservationProof(self.receipt_sequence, self.manifest_digest,
                    source, "situation_source_binding")
        for entry in self.sources:
            if entry == source:
                if self.version == 2 and entry.delivery_payload_digest != self.manifest.payload_digest:
                    return None
                return DeliveredObservationProof(self.receipt_sequence, self.manifest_digest,
                    entry, "situation_delivered")
        for entry in self.result_sources:
            if entry == source:
                return DeliveredObservationProof(self.receipt_sequence, self.manifest_digest,
                    entry, "committed_result")
        return None


@dataclass(frozen=True)
class CommittedEffect:
    kind: str
    source_type: str
    source_id: str
    status: Literal["succeeded", "failed", "unknown"]


@dataclass(frozen=True)
class CommittedActivityResult:
    logical_activity_id: str
    lane: Lane
    target_key: str
    planned_effects: tuple[str, ...]
    effects: tuple[CommittedEffect, ...]
    planned_output_digest: str
    final_output_digest: str
    occurred_at: datetime
    counterpart_id: str | None = None
    thought_reference: str | None = None
    result_sources: tuple[DeliveredSourceEntry, ...] = ()

    def __post_init__(self):
        if (not self.logical_activity_id or not self.target_key
                or self.lane not in {"chat", "inbox", "feed", "routine"}
                or self.occurred_at.tzinfo is None
                or len(self.planned_output_digest) != 64 or len(self.final_output_digest) != 64):
            raise ValueError("situation_result_invalid")

    @property
    def eligibility_code(self) -> str | None:
        if not self.planned_effects:
            return "situation_no_action"
        if any(effect.status == "unknown" for effect in self.effects):
            return "situation_result_unknown"
        if (self.planned_output_digest != self.final_output_digest
                or sorted(self.planned_effects) != sorted(effect.kind for effect in self.effects if effect.status == "succeeded")
                or any(effect.status != "succeeded" for effect in self.effects)):
            return "situation_result_mismatch"
        return None
