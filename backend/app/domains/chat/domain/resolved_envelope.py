"""Code-resolved immutable identity, policy, and hard-cap envelope."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from app.domains.chat.domain.retrieval_intent import (
    RETRIEVAL_INTENT_VERSION,
    RetrievalContractError,
    RetrievalIntentEnvelope,
)


RESOLVED_RETRIEVAL_VERSION = "resolved-retrieval.v1"


@dataclass(frozen=True, slots=True)
class RetrievalHardCaps:
    row_limit: int = 20
    max_hops: int = 3
    fanout_limit: int = 20
    timeout_ms: int = 4_000
    token_budget: int = 4_000

    def __post_init__(self) -> None:
        if not 1 <= self.row_limit <= 50:
            raise RetrievalContractError("resolved_retrieval_row_limit_invalid")
        if not 1 <= self.max_hops <= 3:
            raise RetrievalContractError("resolved_retrieval_hop_limit_invalid")
        if not 1 <= self.fanout_limit <= 40:
            raise RetrievalContractError("resolved_retrieval_fanout_invalid")
        if not 100 <= self.timeout_ms <= 30_000:
            raise RetrievalContractError("resolved_retrieval_timeout_invalid")
        if not 256 <= self.token_budget <= 32_000:
            raise RetrievalContractError("resolved_retrieval_token_budget_invalid")

    def payload(self) -> dict[str, int]:
        return {
            "row_limit": self.row_limit,
            "max_hops": self.max_hops,
            "fanout_limit": self.fanout_limit,
            "timeout_ms": self.timeout_ms,
            "token_budget": self.token_budget,
        }


@dataclass(frozen=True, slots=True)
class ResolvedEntityBinding:
    ref: str
    world_character_id: str

    def __post_init__(self) -> None:
        if not self.ref or not self.world_character_id:
            raise RetrievalContractError("resolved_retrieval_entity_binding_invalid")


@dataclass(frozen=True, slots=True)
class ResolvedRetrievalEnvelope:
    request_id: str
    intent_hash: str
    owner_id: str
    world_id: str
    requester_world_character_id: str
    responding_world_character_id: str
    entity_bindings: tuple[ResolvedEntityBinding, ...]
    relationship_from_world_character_id: str | None
    relationship_to_world_character_id: str | None
    absolute_time_from: str | None
    absolute_time_to: str | None
    memory_enabled: bool
    canonical_operation_allowlist: tuple[str, ...]
    graph_operation_allowlist: tuple[str, ...]
    caps: RetrievalHardCaps
    membership_active: bool = True
    blocked: bool = False
    visible: bool = True
    observable: bool = True
    intent_version: str = RETRIEVAL_INTENT_VERSION
    version: str = RESOLVED_RETRIEVAL_VERSION

    def __post_init__(self) -> None:
        if self.version != RESOLVED_RETRIEVAL_VERSION:
            raise RetrievalContractError("resolved_retrieval_version_mismatch")
        if self.intent_version != RETRIEVAL_INTENT_VERSION:
            raise RetrievalContractError("resolved_retrieval_intent_version_mismatch")
        if len(self.intent_hash) != 64:
            raise RetrievalContractError("resolved_retrieval_intent_hash_invalid")
        required = (
            self.request_id,
            self.owner_id,
            self.world_id,
            self.requester_world_character_id,
            self.responding_world_character_id,
        )
        if any(not value for value in required):
            raise RetrievalContractError("resolved_retrieval_identity_missing")
        if self.requester_world_character_id == self.responding_world_character_id:
            raise RetrievalContractError("resolved_retrieval_self_chat_invalid")
        refs = [binding.ref for binding in self.entity_bindings]
        if len(refs) != len(set(refs)):
            raise RetrievalContractError("resolved_retrieval_entity_ref_duplicate")
        if not self.membership_active or self.blocked or not self.visible:
            raise RetrievalContractError("resolved_retrieval_policy_denied")
        if (self.relationship_from_world_character_id is None) != (
            self.relationship_to_world_character_id is None
        ):
            raise RetrievalContractError("resolved_retrieval_direction_incomplete")
        if (
            self.relationship_from_world_character_id is not None
            and self.relationship_from_world_character_id
            == self.relationship_to_world_character_id
        ):
            raise RetrievalContractError("resolved_retrieval_direction_self_invalid")
        if len(set(self.canonical_operation_allowlist)) != len(
            self.canonical_operation_allowlist
        ):
            raise RetrievalContractError("resolved_retrieval_canonical_allowlist_duplicate")
        if len(set(self.graph_operation_allowlist)) != len(
            self.graph_operation_allowlist
        ):
            raise RetrievalContractError("resolved_retrieval_graph_allowlist_duplicate")

    @classmethod
    def bind_intent(cls, intent: RetrievalIntentEnvelope, **values: Any) -> "ResolvedRetrievalEnvelope":
        return cls(intent_hash=intent.envelope_hash, **values)

    def payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "request_id": self.request_id,
            "intent_version": self.intent_version,
            "intent_hash": self.intent_hash,
            "owner_id": self.owner_id,
            "world_id": self.world_id,
            "requester_world_character_id": self.requester_world_character_id,
            "responding_world_character_id": self.responding_world_character_id,
            "entity_bindings": [
                {"ref": binding.ref, "world_character_id": binding.world_character_id}
                for binding in self.entity_bindings
            ],
            "relationship_from_world_character_id": self.relationship_from_world_character_id,
            "relationship_to_world_character_id": self.relationship_to_world_character_id,
            "absolute_time_from": self.absolute_time_from,
            "absolute_time_to": self.absolute_time_to,
            "memory_enabled": self.memory_enabled,
            "canonical_operation_allowlist": list(self.canonical_operation_allowlist),
            "graph_operation_allowlist": list(self.graph_operation_allowlist),
            "caps": self.caps.payload(),
            "membership_active": self.membership_active,
            "blocked": self.blocked,
            "visible": self.visible,
            "observable": self.observable,
        }

    @property
    def envelope_hash(self) -> str:
        encoded = json.dumps(
            self.payload(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "RESOLVED_RETRIEVAL_VERSION",
    "ResolvedEntityBinding",
    "ResolvedRetrievalEnvelope",
    "RetrievalHardCaps",
]
