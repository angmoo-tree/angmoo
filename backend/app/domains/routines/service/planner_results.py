"""Compact observations and actual planner outcomes for resident execution."""

from __future__ import annotations

from typing import Any

from app.domains.routines.contracts.planning_context import ClipContextText
from app.domains.routines.contracts.resident import (
    ResidentGraphState as _ResidentGraphState,
)
from app.domains.routines.contracts.topic_arcs import TopicArcWorkflows
from app.domains.routines.policies.writing_contract import (
    _OWNER_FEED_CUE_MODE,
    _RELATIONSHIP_POINT_MODE,
)
from app.domains.routines.service import topic_arcs as topic_arc_service
from app.domains.routines.service.action_plans import _INBOX_CONVERSATION_JUDGMENTS


def _planner_feed_observation_for_prompt(
    feed_observation: dict[str, Any],
) -> dict[str, Any]:
    selected_posts = feed_observation.get("selected_posts")
    items = selected_posts if isinstance(selected_posts, list) else []
    return {
        "selected_posts": [
            {
                "item_index": item.get("item_index", index),
                "author": item.get("author"),
                "author_character_id": item.get("author_character_id"),
                "author_handle": item.get("author_handle"),
                "topic_signature": item.get("topic_signature"),
                "semantic_summary": item.get("semantic_summary"),
                "why_it_mattered": item.get("why_it_mattered"),
                "available_actions": item.get("available_actions", []),
                "blocked_actions": item.get("blocked_actions", {}),
            }
            for index, item in enumerate(items)
            if isinstance(item, dict)
        ],
        "feed_theme_topics": feed_observation.get("feed_theme_topics") or [],
        "returned_count": feed_observation.get("returned_count") or 0,
        "excluded_seen_count": feed_observation.get("excluded_seen_count") or 0,
        "excluded_reply_already_answered_count": feed_observation.get(
            "excluded_reply_already_answered_count"
        )
        or 0,
    }


def _planner_inbox_observation_for_prompt(
    inbox_observation: dict[str, Any],
) -> dict[str, Any]:
    raw_items = inbox_observation.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    return {
        "items": [
            {
                "item_index": item.get("item_index", index),
                "notification_type": item.get("notification_type"),
                "actor_name": item.get("actor_name"),
                "semantic_summary": item.get("semantic_summary"),
                "why_it_mattered": item.get("why_it_mattered"),
                "conversation_context": item.get("conversation_context"),
                "activity_proposal": item.get("activity_proposal"),
                "available_actions": item.get("available_actions", []),
                "blocked_actions": item.get("blocked_actions", {}),
            }
            for index, item in enumerate(items)
            if isinstance(item, dict)
        ],
        "returned_count": inbox_observation.get("returned_count") or 0,
        "excluded_seen_count": inbox_observation.get("excluded_seen_count") or 0,
        "excluded_reply_already_answered_count": inbox_observation.get(
            "excluded_reply_already_answered_count"
        )
        or 0,
    }


def _empty_lore_query_result(mode: str) -> dict[str, Any]:
    return {
        "lore_query_mode": mode,
        "retrieval_mode": None,
        "lore_chunk_ids": [],
    }


def _langgraph_tick_payload(
    state: _ResidentGraphState,
    *,
    state_result: dict[str, Any] | None = None,
    topic_workflows: TopicArcWorkflows,
) -> dict[str, Any]:
    payload = {
        "daypart_context": state.get("daypart_context", {}),
        "mandatory_post_context": state.get("mandatory_post_context", {}),
        "independent_topic_composition": state.get("independent_topic_composition", {}),
        "action_plan": state.get("action_plan", {}),
        "planner_results": state.get("planner_results", {}),
        "independent_post_decision": state.get("independent_post_decision", {}),
        "active_topic_arc": topic_arc_service._topic_arc_for_prompt(
            state.get("active_topic_arc"), workflows=topic_workflows
        ),
        "topic_arc_result": state.get("topic_arc_result", {}),
        "publish_result": state.get("publish_result", {}),
        "action_budget_trim_summary": state.get("action_budget_trim_summary", {}),
        "write_task_summary": state.get("write_task_summary", {}),
        "writer_results": state.get("writer_results", {}),
    }
    if state_result is not None:
        payload["state_result"] = state_result
    return payload


def _independent_post_decision_meta(
    independent_post_roll: dict[str, Any],
    *,
    independent_writing_plan: dict[str, Any] | None = None,
    action_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    writing = None
    if isinstance(independent_writing_plan, dict):
        writing = independent_writing_plan.get("writing")
    if not isinstance(writing, dict) and isinstance(action_plan, dict):
        writing = action_plan.get("writing")
    if not isinstance(writing, dict):
        writing = {}

    roll_passed = bool(independent_post_roll.get("passed"))
    blocked_reason = independent_post_roll.get("blocked_reason")
    mode = writing.get("mode")
    planner_called = independent_writing_plan is not None
    if isinstance(independent_writing_plan, dict):
        planner_called = bool(independent_writing_plan.get("planner_called", True))
    topic_key = None
    planner_decision = "not_called"
    skip_reason = str(blocked_reason or "roll_failed") if not roll_passed else None
    if mode == "arc_continuation":
        planner_decision = "arc_continuation"
        skip_reason = None
        topic_key = str(writing.get("topic_key") or "").strip() or None
    elif mode == _OWNER_FEED_CUE_MODE:
        planner_decision = "write_owner_feed_cue"
        skip_reason = None
        topic_key = None
    elif mode == _RELATIONSHIP_POINT_MODE:
        planner_decision = "write_relationship_point"
        skip_reason = None
        topic_key = None
    elif mode == "independent":
        planner_decision = "write"
        skip_reason = None
        topic_key = str(writing.get("topic_key") or "").strip() or None
    elif planner_called:
        planner_decision = "skip"
        skip_reason = str(writing.get("skip_reason") or "").strip() or (
            "planner_skipped" if roll_passed else skip_reason
        )
    elif roll_passed:
        skip_reason = "planner_not_called"

    return {
        "available": bool(independent_post_roll.get("available")),
        "level": independent_post_roll.get("level"),
        "tick_probability": independent_post_roll.get("tick_probability"),
        "roll": independent_post_roll.get("roll"),
        "roll_passed": roll_passed,
        "topic_pool_size": independent_post_roll.get("topic_pool_size"),
        "topic_prompt_count": independent_post_roll.get("topic_prompt_count"),
        "blocked_reason": blocked_reason,
        "planner_decision": planner_decision,
        "skip_reason": skip_reason,
        "topic_key": topic_key,
    }


def _planner_results_summary(
    state: _ResidentGraphState,
    *,
    clip: ClipContextText,
    topic_workflows: TopicArcWorkflows,
) -> dict[str, Any]:
    feed_plan = state.get("feed_action_plan", {})
    inbox_plan = state.get("inbox_action_plan", {})
    relationship_plan = state.get("relationship_action_plan", {})
    independent_plan = state.get("independent_writing_plan", {})
    action_plan = state.get("action_plan", {})
    writing = action_plan.get("writing") if isinstance(action_plan, dict) else {}
    errors = [
        plan["planner_error"]
        for plan in (feed_plan, inbox_plan, relationship_plan, independent_plan)
        if isinstance(plan, dict) and isinstance(plan.get("planner_error"), dict)
    ]
    inbox_conversation_decisions = (
        inbox_plan.get("conversation_decisions", [])
        if isinstance(inbox_plan, dict)
        else []
    )
    if not isinstance(inbox_conversation_decisions, list):
        inbox_conversation_decisions = []
    inbox_conversation_counts: dict[str, int] = {}
    inbox_conversation_summary: list[dict[str, Any]] = []
    for decision in inbox_conversation_decisions:
        if not isinstance(decision, dict):
            continue
        judgment = str(decision.get("conversation_judgment") or "").strip()
        if judgment not in _INBOX_CONVERSATION_JUDGMENTS:
            continue
        inbox_conversation_counts[judgment] = (
            inbox_conversation_counts.get(judgment, 0) + 1
        )
        inbox_conversation_summary.append(
            {
                "item_index": decision.get("item_index"),
                "conversation_judgment": judgment,
                "conversation_reason": clip(decision.get("conversation_reason"), 300)
                or None,
            }
        )
    return {
        "feed": {
            "selection_reason": feed_plan.get("selection_reason")
            if isinstance(feed_plan, dict)
            else None,
            "action_count": len(feed_plan.get("feed_actions", []))
            if isinstance(feed_plan, dict)
            else 0,
            "post_seed_selected": bool(
                isinstance(feed_plan, dict)
                and isinstance(feed_plan.get("writing"), dict)
                and feed_plan["writing"].get("mode") == "post_seed"
            ),
            "topic_arc": topic_arc_service._topic_arc_for_prompt(
                feed_plan.get("writing", {}).get("topic_arc"), workflows=topic_workflows
            )
            if isinstance(feed_plan, dict)
            and isinstance(feed_plan.get("writing"), dict)
            else None,
        },
        "inbox": {
            "selection_reason": inbox_plan.get("selection_reason")
            if isinstance(inbox_plan, dict)
            else None,
            "action_count": len(inbox_plan.get("inbox_actions", []))
            if isinstance(inbox_plan, dict)
            else 0,
            "conversation_judgment_counts": inbox_conversation_counts,
            "conversation_decisions": inbox_conversation_summary,
        },
        "independent_writing": {
            "selection_reason": independent_plan.get("selection_reason")
            if isinstance(independent_plan, dict)
            else None,
            "mode": (
                independent_plan.get("writing", {}).get("mode")
                if isinstance(independent_plan, dict)
                and isinstance(independent_plan.get("writing"), dict)
                else None
            ),
            "topic_arc": topic_arc_service._topic_arc_for_prompt(
                independent_plan.get("writing", {}).get("topic_arc"),
                workflows=topic_workflows,
            )
            if isinstance(independent_plan, dict)
            and isinstance(independent_plan.get("writing"), dict)
            else None,
        },
        "relationship": {
            "selection_reason": relationship_plan.get("selection_reason")
            if isinstance(relationship_plan, dict)
            else None,
            "decision": relationship_plan.get("decision")
            if isinstance(relationship_plan, dict)
            else None,
            "action_count": len(relationship_plan.get("relationship_actions", []))
            if isinstance(relationship_plan, dict)
            else 0,
            "blocked_reason": (
                relationship_plan.get("relationship_review", {}).get("blocked_reason")
                if isinstance(relationship_plan, dict)
                and isinstance(relationship_plan.get("relationship_review"), dict)
                else None
            ),
        },
        "composed": {
            "feed_action_count": len(action_plan.get("feed_actions", []))
            if isinstance(action_plan, dict)
            else 0,
            "inbox_action_count": len(action_plan.get("inbox_actions", []))
            if isinstance(action_plan, dict)
            else 0,
            "relationship_action_count": len(
                action_plan.get("relationship_actions", [])
            )
            if isinstance(action_plan, dict)
            else 0,
            "writing_mode": writing.get("mode") if isinstance(writing, dict) else None,
            "topic_arc": topic_arc_service._topic_arc_for_prompt(
                writing.get("topic_arc"), workflows=topic_workflows
            )
            if isinstance(writing, dict)
            else None,
        },
        "errors": errors,
    }
