"""Normalize observed actions, conversation decisions, and combined plans."""

from __future__ import annotations

from typing import Any

from app.domains.routines.contracts.action_planning import ActionPlanningWorkflows
from app.domains.routines.contracts.planning_context import ResidentPlanningContext
from app.domains.routines.policies.action_matching import (
    _action_name_for_policy,
    _coerce_item_index,
    _matching_relationship_candidate,
    _normalize_planned_action,
    _observation_items,
    _relationship_allowed_actions,
    _relationship_candidate_counts,
)
from app.domains.routines.policies.handoff_coverage import (
    _handoff_covered_by_today_post,
)
from app.domains.routines.policies.writing_contract import (
    _OWNER_FEED_CUE_MODE,
    _RELATIONSHIP_POINT_MODE,
    _subjective_plan_fields,
)
from app.domains.routines.repository import (
    independent_topics as independent_topic_queries,
)

_INBOX_CONVERSATION_JUDGMENTS = {
    "continue_reply",
    "closing_reply",
    "ack_without_reply",
    "no_action_closed",
}


def _filter_action_plan(
    plan: dict[str, Any],
    ctx: ResidentPlanningContext,
    *,
    feed_observation: dict[str, Any],
    inbox_observation: dict[str, Any],
    independent_post_roll: dict[str, Any] | None = None,
    active_topic_arc: dict[str, Any] | None = None,
    workflows: ActionPlanningWorkflows,
) -> dict[str, Any]:
    allowed = set(ctx.activity_policy.allowed_actions)

    def _normalize(action: dict[str, Any], scope: str) -> dict[str, Any] | None:
        if action.get("scope") != scope:
            action["scope"] = scope
        if _action_name_for_policy(str(action.get("action_type"))) not in allowed:
            return None
        observation = feed_observation if scope == "feed" else inbox_observation
        return _normalize_planned_action(action, scope=scope, observation=observation)

    def _normalized_actions(key: str, scope: str) -> list[dict[str, Any]]:
        normalized_actions: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        max_actions = 6 if scope == "inbox" else 4
        raw_actions = plan.get(key, [])
        if not isinstance(raw_actions, list):
            return normalized_actions
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            normalized = _normalize(item, scope)
            if normalized is None:
                continue
            dedupe_key = (
                normalized.get("scope"),
                normalized.get("action_type"),
                normalized.get("post_id"),
                normalized.get("notification_id"),
                normalized.get("target_type"),
                normalized.get("target_id"),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized_actions.append(normalized)
            if len(normalized_actions) >= max_actions:
                break
        return normalized_actions

    def _normalized_relationship_actions() -> list[dict[str, Any]]:
        raw_actions = plan.get("relationship_actions", [])
        if not isinstance(raw_actions, list):
            return []
        normalized_actions: list[dict[str, Any]] = []
        allowed_relationship = set(_relationship_allowed_actions(ctx))
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("action_type") or "").strip()
            if action_type not in {"follow", "unfollow"}:
                continue
            if action_type not in allowed_relationship:
                continue
            target_id = str(item.get("target_id") or "").strip()
            if item.get("target_type") != "character" or not target_id:
                continue
            normalized = dict(item)
            normalized["scope"] = "relationship"
            normalized["target_type"] = "character"
            normalized["target_id"] = target_id
            normalized_actions.append(normalized)
            break
        return normalized_actions

    feed_actions = _normalized_actions("feed_actions", "feed")
    inbox_actions = _normalized_actions("inbox_actions", "inbox")
    relationship_actions = _normalized_relationship_actions()
    writing = plan.get("writing")
    if not isinstance(writing, dict):
        writing = {"mode": "none"}
    else:
        writing = dict(writing)
    if writing.get("mode") == "post_seed":
        source_item_index = _coerce_item_index(writing.get("source_item_index"))
        if source_item_index is not None:
            feed_items = _observation_items(feed_observation, scope="feed")
            if source_item_index < len(feed_items) and isinstance(
                feed_items[source_item_index], dict
            ):
                source_post_id = str(
                    feed_items[source_item_index].get("post_id") or ""
                ).strip()
                writing["source_post_id"] = source_post_id or None
            else:
                writing = {
                    "mode": "none",
                    "brief": None,
                    "source_post_id": None,
                    "skip_reason": "post_seed_source_item_not_found",
                }
        if (
            writing.get("mode") == "post_seed"
            and not str(writing.get("brief") or "").strip()
        ):
            writing = {
                "mode": "none",
                "brief": None,
                "source_post_id": writing.get("source_post_id"),
                "skip_reason": "post_seed_brief_missing",
            }
        if writing.get("mode") == "post_seed":
            writing.pop("topic_arc", None)
        if isinstance(writing, dict):
            writing.pop("source_item_index", None)
    if writing.get("mode") != "none" and "post" not in allowed:
        writing = {
            "mode": "none",
            "brief": None,
            "source_post_id": None,
            "skip_reason": "post_not_allowed",
        }
    elif writing.get("mode") == "independent":
        roll = independent_post_roll or {}
        topics = roll.get("topics") if isinstance(roll, dict) else None
        mandatory_root_post = bool(
            isinstance(roll, dict)
            and roll.get("mandatory")
            and roll.get("passed")
            and not roll.get("blocked_reason")
        )
        ordered_topic_keys = (
            [
                str(topic.get("key"))
                for topic in topics
                if isinstance(topic, dict) and topic.get("key")
            ]
            if isinstance(topics, list)
            else []
        )
        valid_topic_keys = set(ordered_topic_keys)

        def _fallback_topic_key() -> str | None:
            used_today = independent_topic_queries._today_independent_topic_keys(ctx)
            for candidate in ordered_topic_keys:
                if candidate not in used_today:
                    return candidate
            return ordered_topic_keys[0] if ordered_topic_keys else None

        if not str(writing.get("brief") or "").strip():
            fallback_key = _fallback_topic_key()
            fallback_topic = next(
                (
                    topic
                    for topic in topics or []
                    if isinstance(topic, dict)
                    and str(topic.get("key") or "") == str(fallback_key or "")
                ),
                None,
            )
            fallback_brief = workflows.clip(
                fallback_topic.get("prompt")
                if isinstance(fallback_topic, dict)
                else None,
                800,
            ) or workflows.clip(
                fallback_topic.get("label")
                if isinstance(fallback_topic, dict)
                else None,
                800,
            )
            if mandatory_root_post and fallback_brief:
                writing = dict(writing)
                writing["brief"] = fallback_brief
                if fallback_key:
                    writing["topic_key"] = fallback_key
                writing["mandatory_brief_fallback"] = True
            else:
                writing = {
                    "mode": "none",
                    "brief": None,
                    "source_post_id": None,
                    "skip_reason": "independent_brief_missing",
                }
        elif not str(writing.get("topic_key") or "").strip():
            fallback_key = _fallback_topic_key()
            if mandatory_root_post:
                writing = dict(writing)
                if fallback_key:
                    writing["topic_key"] = fallback_key
                    writing["mandatory_topic_fallback"] = "missing_topic"
            else:
                writing = {
                    "mode": "none",
                    "brief": None,
                    "source_post_id": None,
                    "skip_reason": "independent_topic_missing",
                }
        elif not roll.get("passed") or not isinstance(topics, list) or not topics:
            if mandatory_root_post:
                writing = dict(writing)
            else:
                writing = {
                    "mode": "none",
                    "brief": None,
                    "source_post_id": None,
                    "skip_reason": roll.get("blocked_reason") or "roll_failed",
                }
        else:
            writing = dict(writing)
            topic_key = str(writing.get("topic_key") or "").strip()
            if topic_key in independent_topic_queries._today_independent_topic_keys(
                ctx
            ):
                fallback_key = _fallback_topic_key()
                if mandatory_root_post and fallback_key:
                    writing["topic_key"] = fallback_key
                    writing["mandatory_topic_fallback"] = "topic_used_today"
                elif mandatory_root_post:
                    writing["mandatory_topic_fallback"] = "topic_used_today"
                else:
                    writing = {
                        "mode": "none",
                        "brief": None,
                        "source_post_id": None,
                        "skip_reason": "independent_topic_used_today",
                        "topic_key": topic_key,
                    }
            elif writing.get("topic_key") not in valid_topic_keys:
                fallback_key = _fallback_topic_key()
                if mandatory_root_post:
                    if fallback_key:
                        writing["topic_key"] = fallback_key
                    else:
                        writing.pop("topic_key", None)
                    writing["mandatory_topic_fallback"] = "invalid_topic"
                else:
                    writing = {
                        "mode": "none",
                        "brief": None,
                        "source_post_id": None,
                        "skip_reason": "independent_topic_invalid",
                    }
            else:
                covered_handoff = _covered_handoff_matches_independent_writing(
                    writing, roll, workflows.yesterday_handoff(ctx), workflows=workflows
                )
                if covered_handoff is not None and not mandatory_root_post:
                    writing = {
                        "mode": "none",
                        "brief": None,
                        "source_post_id": None,
                        "skip_reason": "independent_handoff_already_covered_today",
                        "covered_handoff_id": covered_handoff.get("handoff_id"),
                        "covered_by_recent_post_id": covered_handoff.get(
                            "covered_by_recent_post_id"
                        ),
                    }
                else:
                    writing["source_post_id"] = None
                    writing.pop("topic_arc", None)
    elif writing.get("mode") == _RELATIONSHIP_POINT_MODE:
        if not str(writing.get("brief") or "").strip():
            writing = {
                "mode": "none",
                "brief": None,
                "source_post_id": None,
                "skip_reason": "relationship_point_brief_missing",
                "relationship_point_id": writing.get("relationship_point_id"),
            }
        elif not writing.get("relationship_point_id"):
            writing = {
                "mode": "none",
                "brief": None,
                "source_post_id": None,
                "skip_reason": "relationship_point_missing",
            }
        else:
            writing = dict(writing)
            writing["source_post_id"] = (
                str(writing.get("source_post_id") or "").strip() or None
            )
            writing.pop("topic_arc", None)
    elif writing.get("mode") == "arc_continuation":
        writing = {
            "mode": "none",
            "brief": None,
            "source_post_id": None,
            "skip_reason": "topic_arc_disabled_v8",
        }
    return {
        **plan,
        "feed_actions": feed_actions,
        "inbox_actions": inbox_actions,
        "relationship_actions": relationship_actions,
        "writing": writing,
    }


def _normalize_feed_action_plan(
    plan: dict[str, Any],
    ctx: ResidentPlanningContext,
    *,
    feed_observation: dict[str, Any],
    active_topic_arc: dict[str, Any] | None = None,
    workflows: ActionPlanningWorkflows,
) -> dict[str, Any]:
    normalized_plan = {
        "selection_reason": plan.get("selection_reason")
        or "feed action planner completed",
        "feed_actions": plan.get("feed_actions", []),
        "inbox_actions": [],
        "writing": {
            "mode": "none",
            "skip_reason": "feed_writing_moved_to_seed_selector",
        },
    }
    if isinstance(plan.get("planner_error"), dict):
        normalized_plan["planner_error"] = plan["planner_error"]
    return _filter_action_plan(
        normalized_plan,
        ctx,
        feed_observation=feed_observation,
        inbox_observation={"items": []},
        active_topic_arc=active_topic_arc,
        workflows=workflows,
    )


def _normalized_inbox_conversation_decisions(
    raw: Any, *, workflows: ActionPlanningWorkflows
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    decisions: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        item_index = _coerce_item_index(item.get("item_index"))
        if item_index is None or item_index > 9 or item_index in seen:
            continue
        judgment = str(item.get("conversation_judgment") or "").strip()
        if judgment not in _INBOX_CONVERSATION_JUDGMENTS:
            continue
        seen.add(item_index)
        decisions.append(
            {
                "item_index": item_index,
                "conversation_judgment": judgment,
                "conversation_reason": workflows.clip(
                    item.get("conversation_reason"), 500
                )
                or None,
            }
        )
    return decisions


def _inbox_actions_with_conversation_decisions(
    actions: Any, decisions: list[dict[str, Any]]
) -> list[Any]:
    if not isinstance(actions, list):
        return []
    decisions_by_index = {
        int(decision["item_index"]): decision
        for decision in decisions
        if isinstance(decision.get("item_index"), int)
    }
    result: list[Any] = []
    for action in actions:
        if not isinstance(action, dict):
            result.append(action)
            continue
        updated = dict(action)
        item_index = _coerce_item_index(updated.get("item_index"))
        decision = (
            decisions_by_index.get(item_index) if item_index is not None else None
        )
        if decision is not None:
            updated["conversation_judgment"] = decision["conversation_judgment"]
            if decision.get("conversation_reason"):
                updated["conversation_reason"] = decision["conversation_reason"]
        elif updated.get("action_type") == "reply":
            updated["conversation_judgment"] = "continue_reply"
        result.append(updated)
    return result


def _normalize_inbox_action_plan(
    plan: dict[str, Any],
    ctx: ResidentPlanningContext,
    *,
    inbox_observation: dict[str, Any],
    workflows: ActionPlanningWorkflows,
) -> dict[str, Any]:
    conversation_decisions = _normalized_inbox_conversation_decisions(
        plan.get("conversation_decisions"), workflows=workflows
    )
    normalized_plan = {
        "selection_reason": plan.get("selection_reason")
        or "inbox action planner completed",
        "feed_actions": [],
        "inbox_actions": _inbox_actions_with_conversation_decisions(
            plan.get("inbox_actions", []),
            conversation_decisions,
        ),
        "conversation_decisions": conversation_decisions,
        "writing": {"mode": "none"},
    }
    if isinstance(plan.get("planner_error"), dict):
        normalized_plan["planner_error"] = plan["planner_error"]
    return _filter_action_plan(
        normalized_plan,
        ctx,
        feed_observation={"selected_posts": []},
        inbox_observation=inbox_observation,
        workflows=workflows,
    )


def _normalize_relationship_action_plan(
    plan: dict[str, Any],
    ctx: ResidentPlanningContext,
    *,
    candidates: list[dict[str, Any]],
    allowed_relationship_actions: list[str],
    workflows: ActionPlanningWorkflows,
) -> dict[str, Any]:
    allowed = set(allowed_relationship_actions)
    decision = str(plan.get("decision") or "none").strip()
    if decision not in {"none", "follow", "unfollow_watch", "unfollow"}:
        decision = "none"
    target_id = str(plan.get("target_character_id") or "").strip()
    reason_tag = workflows.clip(plan.get("reason_tag"), 80) or None
    evidence_summary = workflows.clip(plan.get("evidence_summary"), 800) or None
    blocked_reason = None
    actions: list[dict[str, Any]] = []
    counts = _relationship_candidate_counts(candidates)

    if decision == "follow":
        candidate = _matching_relationship_candidate(
            candidates, action_type="follow", target_id=target_id
        )
        if "follow" not in allowed:
            blocked_reason = "follow_not_allowed"
        elif candidate is None:
            blocked_reason = "follow_candidate_missing"
        elif counts.get(("follow", target_id), 0) < 2:
            blocked_reason = "follow_evidence_insufficient"
        elif workflows.target_following(ctx, target_id):
            blocked_reason = "already_following"
        else:
            actions.append(
                {
                    "scope": "relationship",
                    "action_type": "follow",
                    "target_type": "character",
                    "target_id": target_id,
                    "brief": evidence_summary,
                    **_subjective_plan_fields(plan),
                }
            )
    elif decision in {"unfollow_watch", "unfollow"}:
        candidate = _matching_relationship_candidate(
            candidates, action_type="unfollow_watch", target_id=target_id
        )
        if decision not in allowed:
            blocked_reason = "unfollow_not_allowed"
        elif candidate is None:
            blocked_reason = "unfollow_candidate_missing"
        elif not workflows.target_following(ctx, target_id):
            blocked_reason = "not_following"
        elif decision == "unfollow" and not workflows.has_unfollow_watch(
            ctx, target_id=target_id, reason_tag=reason_tag
        ):
            decision = "unfollow_watch"
        elif decision == "unfollow":
            actions.append(
                {
                    "scope": "relationship",
                    "action_type": "unfollow",
                    "target_type": "character",
                    "target_id": target_id,
                    "brief": evidence_summary,
                    **_subjective_plan_fields(plan),
                }
            )
    if decision == "none" or blocked_reason:
        decision = "none" if blocked_reason else decision
        actions = []

    review = {
        "decision": decision,
        "target_character_id": target_id or None,
        "reason_tag": reason_tag,
        "evidence_summary": evidence_summary,
        "evidence_count": counts.get(("follow", target_id), 0) if target_id else 0,
        "allowed_relationship_actions": allowed_relationship_actions,
        "blocked_reason": blocked_reason,
        "relationship_actions": actions,
        "candidate_count": len(candidates),
    }
    normalized = {
        "selection_reason": plan.get("selection_reason")
        or "relationship planner completed",
        "decision": decision,
        "target_character_id": target_id or None,
        "reason_tag": reason_tag,
        "evidence_summary": evidence_summary,
        "relationship_actions": actions[:1],
        "relationship_review": review,
    }
    if isinstance(plan.get("planner_error"), dict):
        normalized["planner_error"] = plan["planner_error"]
        normalized["relationship_review"]["planner_error"] = plan["planner_error"]
    return normalized


def _normalize_independent_writing_plan(
    plan: dict[str, Any],
    ctx: ResidentPlanningContext,
    *,
    independent_post_roll: dict[str, Any],
    active_topic_arc: dict[str, Any] | None = None,
    workflows: ActionPlanningWorkflows,
) -> dict[str, Any]:
    writing = plan.get("writing") if isinstance(plan, dict) else None
    if not isinstance(writing, dict):
        writing = {"mode": "none"}
    if writing.get("mode") == "independent":
        writing = {
            "mode": "independent",
            "source_post_id": None,
            "topic_key": writing.get("topic_key"),
            "brief": writing.get("brief"),
            "topic_arc": writing.get("topic_arc"),
            **_subjective_plan_fields(writing),
        }
    else:
        writing = {
            "mode": "none",
            "brief": None,
            "source_post_id": None,
            "skip_reason": writing.get("skip_reason") or "planner_skipped",
        }
    normalized_plan = {
        "selection_reason": plan.get("selection_reason")
        or "independent writing planner completed",
        "feed_actions": [],
        "inbox_actions": [],
        "writing": writing,
    }
    if isinstance(plan.get("planner_error"), dict):
        normalized_plan["planner_error"] = plan["planner_error"]
    return _filter_action_plan(
        normalized_plan,
        ctx,
        feed_observation={"selected_posts": []},
        inbox_observation={"items": []},
        independent_post_roll=independent_post_roll,
        active_topic_arc=active_topic_arc,
        workflows=workflows,
    )


def _empty_action_plan(selection_reason: str) -> dict[str, Any]:
    return {
        "selection_reason": selection_reason,
        "feed_actions": [],
        "inbox_actions": [],
        "relationship_actions": [],
        "writing": {"mode": "none", "brief": None, "source_post_id": None},
    }


def _empty_relationship_plan(reason: str) -> dict[str, Any]:
    return {
        "selection_reason": reason,
        "decision": "none",
        "relationship_actions": [],
        "relationship_review": {
            "decision": "none",
            "blocked_reason": reason,
            "relationship_actions": [],
        },
    }


def _independent_writing_skip_reason(
    independent_post_roll: dict[str, Any],
) -> str | None:
    if not independent_post_roll.get("passed"):
        return str(independent_post_roll.get("blocked_reason") or "roll_failed")
    topics = independent_post_roll.get("topics")
    if not isinstance(topics, list) or not topics:
        return "independent_post_topics_missing"
    return None


def _owner_feed_cue_writing(
    feed_cue: Any, *, workflows: ActionPlanningWorkflows
) -> dict[str, Any] | None:
    if feed_cue is None:
        return None
    topic = workflows.clip(getattr(feed_cue, "topic", ""), 800)
    if not topic:
        return None
    return {
        "mode": _OWNER_FEED_CUE_MODE,
        "feed_cue_id": getattr(feed_cue, "id", None),
        "brief": topic,
        "source_post_id": None,
        "topic_key": None,
    }


def _compose_action_bundle(
    *,
    feed_action_plan: dict[str, Any],
    inbox_action_plan: dict[str, Any],
    independent_writing_plan: dict[str, Any],
    relationship_action_plan: dict[str, Any] | None = None,
    owner_feed_cue: Any = None,
    workflows: ActionPlanningWorkflows,
) -> dict[str, Any]:
    if relationship_action_plan is None:
        relationship_action_plan = {}
    post_seed_writing = (
        feed_action_plan.get("writing") if isinstance(feed_action_plan, dict) else None
    )
    independent_writing = (
        independent_writing_plan.get("writing")
        if isinstance(independent_writing_plan, dict)
        else None
    )
    writing: dict[str, Any]
    owner_feed_cue_writing = _owner_feed_cue_writing(
        owner_feed_cue, workflows=workflows
    )
    if owner_feed_cue_writing is not None:
        writing = owner_feed_cue_writing
    elif (
        isinstance(independent_writing, dict)
        and independent_writing.get("mode") == "arc_continuation"
    ):
        writing = dict(independent_writing)
    elif (
        isinstance(independent_writing, dict)
        and independent_writing.get("mode") == "independent"
    ):
        writing = dict(independent_writing)
    elif (
        isinstance(independent_writing, dict)
        and independent_writing.get("mode") == _RELATIONSHIP_POINT_MODE
    ):
        writing = dict(independent_writing)
    elif (
        isinstance(post_seed_writing, dict)
        and post_seed_writing.get("mode") == "post_seed"
    ):
        writing = dict(post_seed_writing)
    else:
        writing = {"mode": "none", "brief": None, "source_post_id": None}

    return {
        "selection_reason": "feed, inbox, and writing planners composed independently",
        "feed_actions": list(feed_action_plan.get("feed_actions", []))
        if isinstance(feed_action_plan, dict)
        else [],
        "inbox_actions": list(inbox_action_plan.get("inbox_actions", []))
        if isinstance(inbox_action_plan, dict)
        else [],
        "relationship_actions": list(
            relationship_action_plan.get("relationship_actions", [])
        )
        if isinstance(relationship_action_plan, dict)
        else [],
        "relationship_review": relationship_action_plan.get("relationship_review", {})
        if isinstance(relationship_action_plan, dict)
        else {},
        "writing": writing,
        "component_selection_reasons": {
            "feed": feed_action_plan.get("selection_reason")
            if isinstance(feed_action_plan, dict)
            else None,
            "inbox": inbox_action_plan.get("selection_reason")
            if isinstance(inbox_action_plan, dict)
            else None,
            "relationship": relationship_action_plan.get("selection_reason")
            if isinstance(relationship_action_plan, dict)
            else None,
            "independent_writing": independent_writing_plan.get("selection_reason")
            if isinstance(independent_writing_plan, dict)
            else None,
            "owner_feed_cue": (
                f"pending owner feed cue {getattr(owner_feed_cue, 'id', '-')}"
                if owner_feed_cue_writing is not None
                else None
            ),
        },
    }


def _independent_topic_prompt_text(
    writing: dict[str, Any],
    independent_post_roll: dict[str, Any],
    *,
    workflows: ActionPlanningWorkflows,
) -> str:
    topic_key = str(writing.get("topic_key") or "").strip()
    parts = [workflows.clip(writing.get("brief"), 800)]
    topics = independent_post_roll.get("topics")
    if isinstance(topics, list):
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            if str(topic.get("key") or "").strip() != topic_key:
                continue
            parts.append(workflows.clip(topic.get("label"), 200))
            parts.append(workflows.clip(topic.get("prompt"), 500))
            break
    return " ".join(part for part in parts if part)


def _covered_handoff_matches_independent_writing(
    writing: dict[str, Any],
    independent_post_roll: dict[str, Any],
    handoffs: list[dict[str, Any]],
    *,
    workflows: ActionPlanningWorkflows,
) -> dict[str, Any] | None:
    writing_text = _independent_topic_prompt_text(
        writing, independent_post_roll, workflows=workflows
    )
    if not writing_text:
        return None
    for handoff in handoffs:
        if not isinstance(handoff, dict) or not handoff.get("already_covered_today"):
            continue
        summary = workflows.clip(handoff.get("summary"), 500)
        if summary and _handoff_covered_by_today_post(summary, writing_text):
            return handoff
    return None
