"""Immutable, scoped relationship facts shared by one Chat/SNS activity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
import hashlib
import json

from app.domains.relationships.contracts.graph_recall import (
    GraphRecallRelationship,
    GraphRecallScope,
)


@dataclass(frozen=True, slots=True)
class SocialContextItem:
    relationship: GraphRecallRelationship
    display_name: str
    selection_reasons: tuple[str, ...]
    source: str


@dataclass(frozen=True, slots=True)
class SocialContextSnapshot:
    snapshot_id: str
    scope: GraphRecallScope
    validated_at: datetime
    items: tuple[SocialContextItem, ...]
    status: Literal["ready", "partial", "empty", "unavailable"]
    coverage: Literal["partial", "unknown"]
    candidate_count: int
    excluded_count: int
    query_count: int
    truncation_reasons: tuple[str, ...]
    context_text: str
    content_hash: str
    schema_revision: str = "social-context.v1"
    selection_policy_revision: str = "outgoing-balanced.v1"

    def __post_init__(self):
        if (not self.snapshot_id or self.validated_at.tzinfo is None or len(self.content_hash) != 64
            or not isinstance(self.items, tuple) or len(self.items) > 12 or len(self.context_text) > 3000
            or self.status not in {"ready", "partial", "empty", "unavailable"}
            or self.coverage not in {"partial", "unknown"}
            or min(self.candidate_count, self.excluded_count, self.query_count) < 0):
            raise ValueError("social_context_snapshot_invalid")
        if any(item.relationship.world_id != self.scope.world_id
            or item.relationship.actor_world_character_id != self.scope.subject_world_character_id
            or item.relationship.target_world_character_id == self.scope.subject_world_character_id
            for item in self.items):
            raise ValueError("social_context_snapshot_scope_invalid")

    @property
    def scope_hash(self):
        return hashlib.sha256(json.dumps([self.scope.owner_id, self.scope.world_id,
            self.scope.subject_world_character_id, self.selection_policy_revision]).encode()).hexdigest()

    def prompt_view(self) -> dict:
        return {"snapshot_id": self.snapshot_id, "content_hash": self.content_hash,
                "status": self.status, "coverage": self.coverage,
                "validated_at": self.validated_at.isoformat(), "context": self.context_text}

    def manifest(self) -> dict:
        """Content-free diagnostic metadata; never invent a total population."""
        return {
            "schema_revision": self.schema_revision,
            "selection_policy_revision": self.selection_policy_revision,
            "snapshot_id": self.snapshot_id,
            "content_hash": self.content_hash,
            "validated_at": self.validated_at.isoformat(),
            "scope": "outgoing_direct_visible",
            "scope_hash": self.scope_hash,
            "status": self.status,
            "coverage": self.coverage,
            "selected_count": len(self.items),
            "candidate_count": self.candidate_count,
            "excluded_count": self.excluded_count,
            "query_count": self.query_count,
            "total_count": None,
            "truncation_reasons": list(self.truncation_reasons),
            "relationship_versions": [
                [item.relationship.relationship_state_id,
                 item.relationship.relationship_version]
                for item in self.items
            ],
        }


class SocialContextProvider(Protocol):
    def prepare(self, scope: GraphRecallScope, *, counterpart_id: str | None = None) -> SocialContextSnapshot: ...
    def assert_current(self, snapshot: SocialContextSnapshot) -> None: ...


class SocialContextChangedError(ValueError):
    """Previously prepared facts cannot be used after this activity boundary."""
