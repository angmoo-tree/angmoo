"""Successful source evidence, results and read-only policy facts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Protocol
from app.domains.relationships import models


class EventWorld(Protocol):
    @property
    def timezone(self) -> str: ...


class RelationshipStateValues(Protocol):
    familiarity: int
    affinity: int
    trust: int
    tension: int
    interaction_count: int
    version: int


@dataclass(frozen=True)
class EvidenceInput:
    evidence_kind: Literal[
        "post",
        "reply_post",
        "like",
        "repost",
        "follow",
        "notification",
        "execution",
        "joint_activity",
    ]
    source_object_type: Literal[
        "post",
        "post_like",
        "post_repost",
        "profile_follow",
        "notification",
        "agent_public_action_execution",
        "joint_activity",
    ]
    source_object_id: str
    root_post_id: str | None = None
    source_post_id: str | None = None
    target_post_id: str | None = None
    source_notification_id: int | None = None
    agent_run_id: str | None = None
    public_action_execution_id: int | None = None
    interaction_intent: str | None = None
    comment_purpose: str | None = None
    proposal_decision: str | None = None
    source_text: str | None = None
    source_visibility_at_event: str | None = None
    source_author_id_at_event: str | None = None


@dataclass(frozen=True)
class EventApplyResult:
    event: models.SocialEvent
    relationship_state: models.RelationshipState | None
    relationship_change: models.RelationshipStateChange | None
    reused: bool


@dataclass(frozen=True)
class _Delta:
    familiarity: int = 0
    affinity: int = 0
    trust: int = 0
    tension: int = 0
    valence: str = "neutral"
    intensity: str = "low"
