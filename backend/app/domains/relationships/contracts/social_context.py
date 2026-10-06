"""Immutable, scoped relationship facts shared by one Chat/SNS activity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal, Protocol
import hashlib
import json

from app.contracts.relationship_currentness import (
    CURRENTNESS_REVISION, LEGACY_CURRENTNESS, CURRENTNESS_POLICY_KEY,
)

from app.domains.relationships.contracts.graph_recall import (
    GraphRecallRelationship,
    GraphRecallScope, GraphRecallScopeAccess,
)
from app.domains.relationships.contracts.graph_query import GraphNodeCandidate, RelationshipRevalidationFacts


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


MAX_RECEIPT_BYTES = 16 * 1024


def read_currentness_policy(value: dict | None) -> str:
    """Absence identifies old inputs; never install today's default on resume."""
    if value is not None and type(value) is not dict:
        raise SocialContextValidationError("receipt_invalid")
    revision = (value or {}).get(CURRENTNESS_POLICY_KEY, LEGACY_CURRENTNESS)
    if type(revision) is not str or revision not in {CURRENTNESS_REVISION, LEGACY_CURRENTNESS}:
        raise SocialContextValidationError("receipt_invalid")
    return revision


class SocialContextValidationError(SocialContextChangedError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _receipt_reference(value, label):
    from app.domains.relationships.exceptions import RelationshipGraphRequestError
    from app.domains.relationships.policies.graph_recall import _validate_reference
    try:
        _validate_reference(value, label)
    except RelationshipGraphRequestError as exc:
        raise SocialContextValidationError("receipt_invalid") from exc


@dataclass(frozen=True, slots=True)
class RelationshipValidationReference:
    relationship_state_id: str
    target_world_character_id: str
    relationship_version: int
    view_version: int
    facts_digest: str

    def __post_init__(self):
        _receipt_reference(self.relationship_state_id, "state")
        _receipt_reference(self.target_world_character_id, "target")
        if (type(self.relationship_version) is not int or self.relationship_version < 0
                or type(self.view_version) is not int or self.view_version < 0
                or not _digest_valid(self.facts_digest)):
            raise SocialContextValidationError("receipt_invalid")


def _digest_valid(value) -> bool:
    return (type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


@dataclass(frozen=True, slots=True)
class RelationshipValidationBinding:
    activity_id: str
    lane: Literal["inbox", "feed", "routine"]
    target_id: str
    counterpart_id: str | None

    def __post_init__(self):
        _receipt_reference(self.activity_id, "activity")
        _receipt_reference(self.target_id, "target")
        if self.counterpart_id is not None:
            _receipt_reference(self.counterpart_id, "counterpart")
        if self.lane not in {"inbox", "feed", "routine"}:
            raise SocialContextValidationError("receipt_invalid")


@dataclass(frozen=True, slots=True)
class RelationshipValidationReceipt:
    revision: str
    scope: GraphRecallScope
    binding: RelationshipValidationBinding
    snapshot_id: str
    input_content_hash: str
    basis: Literal["facts", "no_facts", "unavailable", "disabled"]
    references: tuple[RelationshipValidationReference, ...]

    def __post_init__(self):
        for value in (self.scope.owner_id, self.scope.world_id, self.scope.subject_world_character_id):
            _receipt_reference(value, "scope")
        _receipt_reference(self.snapshot_id, "snapshot")
        if (self.revision != CURRENTNESS_REVISION or not _digest_valid(self.input_content_hash)
                or self.basis not in {"facts", "no_facts", "unavailable", "disabled"}
                or type(self.references) is not tuple or len(self.references) > 12
                or bool(self.references) != (self.basis == "facts")
                or any(not isinstance(ref, RelationshipValidationReference) for ref in self.references)
                or len({ref.relationship_state_id for ref in self.references}) != len(self.references)
                or len({ref.target_world_character_id for ref in self.references}) != len(self.references)
                or any(ref.target_world_character_id == self.scope.subject_world_character_id for ref in self.references)):
            raise SocialContextValidationError("receipt_invalid")
        if len(json.dumps(asdict(self), ensure_ascii=False, allow_nan=False).encode()) > MAX_RECEIPT_BYTES:
            raise SocialContextValidationError("receipt_invalid")

    def to_dict(self) -> dict:
        value = asdict(self)
        value["references"] = list(value["references"])
        return value

    @classmethod
    def from_dict(cls, value: dict) -> RelationshipValidationReceipt:
        try:
            if type(value) is not dict or len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > MAX_RECEIPT_BYTES:
                raise ValueError()
            if set(value) != set(cls.__dataclass_fields__):
                raise ValueError()
            if type(value["references"]) is not list:
                raise ValueError()
            return cls(**{**value, "scope": GraphRecallScope(**value["scope"]),
                "binding": RelationshipValidationBinding(**value["binding"]),
                "references": tuple(RelationshipValidationReference(**ref) for ref in value["references"])})
        except (TypeError, ValueError, AttributeError, OverflowError) as exc:
            raise SocialContextValidationError("receipt_invalid") from exc


@dataclass(frozen=True, slots=True)
class CanonicalSocialContextReference:
    """An explicit reference; a missing state ID is only for legacy hash proof."""
    target_world_character_id: str
    relationship_state_id: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalSocialContextFacts:
    scope_access: GraphRecallScopeAccess
    relationships: dict[str, RelationshipRevalidationFacts]
    nodes: dict[str, GraphNodeCandidate]


@dataclass(frozen=True, slots=True)
class SocialContextValidationResult:
    revision: str
    outcome: str
    checked_count: int
    reason: str | None = None
