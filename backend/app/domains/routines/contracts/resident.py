"""Provider-independent state passed between resident graph steps."""
from __future__ import annotations
from typing import Any, TypedDict


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

