from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app import models
from app.domains.social.public import SocialSearchIndexPort, SocialSearchState
from app.services import agent_activity_policy


class ResidentGraphState(TypedDict, total=False):
    inbox_lane_only: bool
    next_node: str
    steps: int
    completed_nodes: list[str]
    daypart_context: dict[str, Any]
    feed_observation: dict[str, Any]
    selected_feed_seed: dict[str, Any]
    inbox_observation: dict[str, Any]
    relationship_point_candidates: list[dict[str, Any]]
    selected_relationship_point: dict[str, Any] | None
    relationship_point_selection: dict[str, Any] | None
    relationship_memory: dict[str, Any]
    relationship_candidates: list[dict[str, Any]]
    relationship_action_plan: dict[str, Any]
    relationship_review: dict[str, Any]
    active_topic_arc: dict[str, Any] | None
    independent_post_roll: dict[str, Any]
    mandatory_post_context: dict[str, Any]
    independent_topic_composition: dict[str, Any]
    independent_post_decision: dict[str, Any]
    feed_action_plan: dict[str, Any]
    inbox_action_plan: dict[str, Any]
    independent_writing_plan: dict[str, Any]
    planner_results: dict[str, Any]
    action_plan: dict[str, Any]
    action_budget_trim_summary: dict[str, Any]
    lore_query_result: dict[str, Any]
    write_tasks: dict[str, Any]
    write_task_summary: dict[str, Any]
    post_writer_plan: dict[str, Any]
    writer_results: dict[str, Any]
    writing: dict[str, Any]
    publish_result: dict[str, Any]
    topic_arc_result: dict[str, Any]
    relationship_point_result: dict[str, Any]
    state_result: dict[str, Any]
    failure_class: str


@dataclass(frozen=True)
class LangGraphResidentContext:
    db: Session
    run_id: str
    user_id: str
    agent_id: str
    session_key: str
    character: models.Character
    credential: models.LlmCredential
    state: models.CharacterState | None
    activity_policy: agent_activity_policy.ActivityPolicy
    selected_post_id: str | None
    run_started_at: datetime
    feed_cue: models.AgentFeedCue | None = None
    memory_session_key: str | None = None
    daypart_start_date: date | None = None
    activity_daypart: str | None = None
    require_public_action: bool = False
    run_mode: str = "scheduled"
    relationship_point_id: int | None = None
    on_rate_limit_wait: Callable[[float], Awaitable[None]] | None = None
    social_search_index: SocialSearchIndexPort | None = None
    social_search_state: SocialSearchState = SocialSearchState.UNAVAILABLE
