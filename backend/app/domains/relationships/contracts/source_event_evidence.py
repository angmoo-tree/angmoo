"""Read-only source facts; no ORM, runtime or permission cache."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class SourceEvent(Protocol):
    id: str
    world_id: str
    actor_world_character_id: str
    target_world_character_id: str | None
    event_type: str
    result: str
    retrieval_status: str
    occurred_at: datetime
    invalidated_at: datetime | None
    invalidation_reason: str | None


class SourceEvidence(Protocol):
    id: str
    social_event_id: str
    evidence_kind: str
    source_object_type: str
    source_object_id: str
    source_post_id: str | None
    target_post_id: str | None
    root_post_id: str | None
    source_author_id_at_event: str | None
    source_visibility_at_event: str | None
    content_sha256: str | None
    public_action_execution_id: int | None
    agent_run_id: str | None


class SourcePost(Protocol):
    id: str
    world_id: str | None
    author_world_character_id: str | None
    reply_to_post_id: str | None
    title: str
    body: str
    visibility: str
    deleted_at: datetime | None
    report_hidden_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class SourceEventBasis:
    event_id: str
    event_type: str
    actor_id: str
    counterpart_id: str | None
    source_post_id: str
    target_post_id: str | None
    root_post_id: str
    parent_post_id: str | None
    digest: str

    def matches_record(self, record):
        return isinstance(record, dict) and all(record.get(key) == value for key, value in {
            "source_type": "social_event", "source_id": self.event_id,
            "event_type": self.event_type, "actor_world_character_id": self.actor_id,
            "counterpart_world_character_id": self.counterpart_id,
            "source_post_id": self.source_post_id, "target_post_id": self.target_post_id,
            "root_post_id": self.root_post_id, "parent_post_id": self.parent_post_id,
            "source_revision": self.digest,
        }.items())
