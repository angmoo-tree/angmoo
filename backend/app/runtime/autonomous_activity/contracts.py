"""Serializable graph channels. Live sessions/providers remain outside State."""
from hashlib import sha256
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = 1
FEED_TARGET_LIMIT = 1
INBOX_TARGET_LIMIT = 3
RECALL_CONCURRENCY = 2
AI_QUERY_CHARS = 400
NATURAL_QUERY_CHARS = 800
MEMORY_LIMIT = 3
MEMORY_CHARS = 3000
TODAY_LIMIT = 12


def identity_key(*parts: str) -> str:
    # Length-prefix avoids ambiguity if a source ID contains a separator.
    return sha256("".join(f"{len(p)}:{p}" for p in parts).encode()).hexdigest()


class ActivityIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    activity_id: str
    world_id: str
    actor_id: str
    engine: Literal["personalized_graph_v2"] = "personalized_graph_v2"
    contract_version: Literal[1] = 1
    cause: Literal["manual", "scheduled", "recovery"]
    generation_model: str | None = None
    thinking_level: str | None = None


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: str
    counterpart_id: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    source_revisions: dict[str, str] = Field(default_factory=dict)
    text: str
    parent_text: str = ""
    topic_signature: str | None = None
    allowed_actions: list[str]
    relationship: dict[str, Any] = Field(default_factory=dict)
    waiting_since: str | None = None
    activity_proposal: dict[str, Any] | None = None
    proposal_eligible: bool = False


class Selection(BaseModel):
    target_id: str
    # Auxiliary parsing intentionally occurs after target identity validation.
    memory_query: Any = None


class SelectionOutput(BaseModel):
    selections: list[Selection]


class ResolvedQuery(BaseModel):
    target_id: str
    query: str
    origin: Literal["selector", "natural", "routine"]
    fallback_reason: str | None = None


class PathResult(BaseModel):
    path: Literal["inbox", "routine", "feed"]
    status: Literal["completed", "no_action", "waiting", "failed"]
    public_action_count: int = 0
    selected_ids: list[str] = Field(default_factory=list)
    recall_status: dict[str, str] = Field(default_factory=dict)
    reason: str | None = None


class LaneState(TypedDict, total=False):
    identity: dict
    shared_context: dict
    candidates: list[dict]
    selections: list[dict]
    queries: list[dict]
    memories: dict[str, dict]
    decision_context: dict
    decision: dict
    assignments: list[dict]
    drafts: list[dict]
    executions: list[dict]
    settlement: dict
    result: dict
    lane_data: dict
    failure: dict


class ParentState(TypedDict, total=False):
    identity: dict
    shared_context: dict
    inbox_result: dict
    routine_result: dict
    feed_result: dict
    result: dict
