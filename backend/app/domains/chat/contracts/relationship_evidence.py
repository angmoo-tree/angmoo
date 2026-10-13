"""Private, immutable delivery receipts for committed Chat relationship evidence."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal
from app.domains.relationships.contracts.graph_recall import GraphRecallRelationship

DELIVERY_KEY = "_relationship_evidence_delivery_v2"
DELIVERY_REVISION = "relationship-evidence-delivery.v2"
MAX_DELIVERY_BYTES = 80 * 1024


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        allow_nan=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RelationshipEvidenceBinding:
    owner_id: str
    world_id: str
    thread_id: str
    actor_id: str
    requester_id: str
    request_id: str
    request_scope_hash: str
    response_slot_id: str
    generation_id: str
    attempt_number: int

    def __post_init__(self):
        if any(type(v) is not str or not v or len(v) > 128 for k, v in asdict(self).items() if k != "attempt_number") or type(self.attempt_number) is not int or self.attempt_number < 1:
            raise ValueError("relationship_evidence_binding_invalid")

    @classmethod
    def for_request(cls, request, *, owner_id, world_id, actor_id, requester_id):
        return cls(owner_id, world_id, request.thread_id, actor_id, requester_id,
            request.request_id, request.request_scope_hash, request.response_slot_id,
            request.generation_id, request.attempt_number)


@dataclass(frozen=True, slots=True)
class RelationshipDeliveredItem:
    section: Literal["items", "current_context"]
    reference: str
    state_id: str
    actor_id: str
    target_id: str
    version: int
    view_version: int
    facts_digest: str
    basis: Literal["social", "graph"]
    name: str | None
    path: str
    fragment: str
    fragment_digest: str
    inspector_digest: str
    projection: dict | None = None

    def __post_init__(self):
        if self.section not in {"items", "current_context"} or self.basis not in {"social", "graph"} or any(
                type(v) is not str or not v or len(v) > 128 for v in (self.reference, self.state_id, self.actor_id, self.target_id)):
            raise ValueError("relationship_evidence_item_invalid")
        if any(type(v) is not int or v < 0 for v in (self.version, self.view_version)) or any(
                type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
                for v in (self.facts_digest, self.fragment_digest, self.inspector_digest)):
            raise ValueError("relationship_evidence_item_invalid")
        if self.name is not None and (type(self.name) is not str or not self.name or len(self.name) > 80):
            raise ValueError("relationship_evidence_item_invalid")
        if type(self.fragment) is not str or not self.fragment or len(self.fragment) > 3000 or digest(self.fragment) != self.fragment_digest or type(self.path) is not str or len(self.path) > 100:
            raise ValueError("relationship_evidence_fragment_invalid")
        prefix = "/social_context/context/row/" if self.section == "current_context" else "/frozen_evidence/items/"
        suffix = "" if self.section == "current_context" else "/text"
        index = self.path[len(prefix):len(self.path)-len(suffix) if suffix else None]
        if not self.path.startswith(prefix) or not self.path.endswith(suffix) or not index.isdecimal() or not 0 <= int(index) < 12:
            raise ValueError("relationship_evidence_path_invalid")
        if self.projection is not None:
            validate_projection(self.projection)


@dataclass(frozen=True, slots=True)
class RelationshipEvidenceDelivery:
    binding: RelationshipEvidenceBinding
    payload_digest: str
    prompt_digest: str
    items: tuple[RelationshipDeliveredItem, ...]
    revision: str = DELIVERY_REVISION
    hash_scope: str = "chat-final-json.v1+serialized-user-prompt.sha256"

    def __post_init__(self):
        if self.revision != DELIVERY_REVISION or self.hash_scope != "chat-final-json.v1+serialized-user-prompt.sha256" or len(self.items) > 24 or any(
                sum(item.section == section for item in self.items) > 12 for section in ("items", "current_context")):
            raise ValueError("relationship_evidence_delivery_invalid")
        if len({(item.section, item.reference) for item in self.items}) != len(self.items) or any(
                item.actor_id != self.binding.actor_id or item.actor_id == item.target_id for item in self.items):
            raise ValueError("relationship_evidence_delivery_invalid")
        if any(type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v)
                for v in (self.payload_digest, self.prompt_digest)):
            raise ValueError("relationship_evidence_delivery_invalid")

    def to_dict(self):
        value = asdict(self)
        value["items"] = list(value["items"])
        return {**value, "digest": digest(value)}

    @classmethod
    def from_dict(cls, raw):
        try:
            if type(raw) is not dict or set(raw) != {*cls.__dataclass_fields__, "digest"} or len(json.dumps(raw, ensure_ascii=False).encode()) > MAX_DELIVERY_BYTES:
                raise ValueError()
            value = {k: v for k, v in raw.items() if k != "digest"}
            if digest(value) != raw["digest"] or type(value["items"]) is not list:
                raise ValueError()
            return cls(**{**value, "binding": RelationshipEvidenceBinding(**value["binding"]),
                "items": tuple(RelationshipDeliveredItem(**item) for item in value["items"])})
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
            raise ValueError("relationship_evidence_delivery_invalid") from exc


@dataclass(frozen=True, slots=True)
class RelationshipCurrentRead:
    access_allowed: bool
    relationship: GraphRecallRelationship | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RelationshipEvidenceRead:
    excerpt: str | None = None
    name: str | None = None
    change: Literal["same", "changed", "not_checked"] | None = None
    reason: Literal["historical_unverified", "current_unavailable", "read_unavailable"] | None = None


def validate_projection(value):
    keys = {"familiarity", "affinity", "trust", "tension", "interactions", "relationship_label", "perception"}
    if type(value) is not dict or set(value) != keys:
        raise ValueError("relationship_projection_invalid")
    for key, lower, upper in (("familiarity", 0, 100), ("affinity", -100, 100),
            ("trust", -100, 100), ("tension", 0, 100), ("interactions", 0, None)):
        if type(value[key]) is not int or value[key] < lower or (upper is not None and value[key] > upper):
            raise ValueError("relationship_projection_invalid")
    for key in ("relationship_label", "perception"):
        if value[key] is not None and (type(value[key]) is not str or len(value[key]) > 2000):
            raise ValueError("relationship_projection_invalid")
    return value
