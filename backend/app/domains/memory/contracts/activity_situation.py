"""Versioned values for activity-owned situation admission; no I/O or commits."""
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Literal

from app.domains.memory.contracts.scope import MemoryScope
from app.contracts.activity_situation import SITUATION_POLICY, SituationDraft

SITUATION_REPRESENTATION = "activity_situation_v1"
DESCRIPTION_LIMIT = 1000
Lane = Literal["chat", "inbox", "feed", "routine"]


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

    def __post_init__(self):
        if (not self.source_type or not self.source_id or not self.payload_path
                or not self.world_id or self.ordinal < 0
                or any(len(value) != 64 for value in (self.source_digest, self.delivered_digest))
                or self.role not in {"core", "background", "prior", "committed_result", "thought"}
                or any(start < 0 or end < start for start, end in (*self.ranges, *self.delivered_ranges))
                or (self.delivered_ranges and len(self.ranges) != len(self.delivered_ranges))):
            raise ValueError("situation_source_invalid")


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
        if (self.version != 1 or not self.call_identity or len(self.payload_digest) != 64
                or len(self.sources) > 256 or len(threads) > 1
                or (threads and threads != {self.private_thread_id})
                or any(row.world_id != self.snapshot.scope.world_id for row in self.sources)
                or len({row.ordinal for row in self.sources}) != len(self.sources)):
            raise ValueError("situation_manifest_invalid")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict):
        snapshot = dict(value["snapshot"])
        snapshot["scope"] = MemoryScope(**snapshot["scope"])
        return cls(call_identity=value["call_identity"],
            snapshot=SituationPolicySnapshot(**snapshot), payload_digest=value["payload_digest"],
            sources=tuple(DeliveredSourceEntry(**{**row,
                "ranges": tuple(tuple(pair) for pair in row.get("ranges", ()))}) for row in value["sources"]),
            private_thread_id=value.get("private_thread_id"), version=value["version"])


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
