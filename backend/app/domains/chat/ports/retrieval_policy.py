"""Canonical scope facts required by the code-owned retrieval resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domains.chat.domain.retrieval_intent import RetrievalContractError


@dataclass(frozen=True, slots=True)
class RetrievalPreflightCommand:
    request_id: str
    owner_id: str
    world_id: str
    thread_id: str
    requester_world_character_id: str
    responding_world_character_id: str
    user_message: str
    request_is_active: bool = True
    idempotency_conflict: bool = False
    router_runtime_available: bool = True

    def __post_init__(self) -> None:
        identifiers = (
            self.request_id,
            self.owner_id,
            self.world_id,
            self.thread_id,
            self.requester_world_character_id,
            self.responding_world_character_id,
        )
        if any(not value.strip() or len(value) > 128 for value in identifiers):
            raise RetrievalContractError("retrieval_preflight_identity_invalid")
        if self.requester_world_character_id == self.responding_world_character_id:
            raise RetrievalContractError("retrieval_preflight_self_chat_invalid")
        if not self.user_message.strip() or len(self.user_message) > 4_000:
            raise RetrievalContractError("retrieval_preflight_message_invalid")
        if not self.request_is_active:
            raise RetrievalContractError("retrieval_preflight_request_inactive")
        if self.idempotency_conflict:
            raise RetrievalContractError("retrieval_preflight_idempotency_conflict")
        if not self.router_runtime_available:
            raise RetrievalContractError("retrieval_preflight_router_unavailable")


@dataclass(frozen=True, slots=True)
class CanonicalRetrievalScope:
    request_id: str
    owner_id: str
    world_id: str
    thread_id: str
    requester_world_character_id: str
    responding_world_character_id: str
    world_timezone: str
    world_language: str
    responding_character_name: str
    memory_enabled: bool
    membership_active: bool = True
    blocked: bool = False
    visible: bool = True
    observable: bool = True
    world_ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class RetrievalEntityCandidate:
    world_character_id: str
    display_name: str
    handle: str
    active: bool
    blocked: bool
    visible: bool
    observable: bool

    @property
    def safe_for_clarification(self) -> bool:
        return self.active and not self.blocked and self.visible and self.observable


@dataclass(frozen=True, slots=True)
class RetrievalEntityResolution:
    ref: str
    candidates: tuple[RetrievalEntityCandidate, ...]


class RetrievalPolicyResolverPort(Protocol):
    def load_scope(self, command: RetrievalPreflightCommand) -> CanonicalRetrievalScope: ...

    def resolve_entity_mentions(
        self,
        scope: CanonicalRetrievalScope,
        mentions: tuple[tuple[str, str], ...],
    ) -> tuple[RetrievalEntityResolution, ...]: ...


__all__ = [
    "CanonicalRetrievalScope",
    "RetrievalEntityCandidate",
    "RetrievalEntityResolution",
    "RetrievalPolicyResolverPort",
    "RetrievalPreflightCommand",
]
