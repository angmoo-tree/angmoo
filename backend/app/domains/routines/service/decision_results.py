from __future__ import annotations

from app.core.context_text import neutralize_context_text
from app.domains.routines import models
from app.domains.routines.constants import ACTION_DECISION_TYPES
from app.domains.routines.constants import DEFAULT_ACTIVITY_ACTIONS
from app.domains.routines.contracts import activity_policy as agent_activity_policy
from app.domains.routines.utils.context_text import _clip_text
from typing import Any
import json


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _safe_perception_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    return _clip_text(neutralize_context_text(str(value)), limit)


def _normalize_feed_perception_text(text: str) -> str:
    payload = _parse_json_object(text)
    if payload is None:
        fallback_text = _safe_perception_text(text, 500)
        payload = {
            "interesting_posts": [],
            "character_thoughts": fallback_text,
            "post_seed": "",
            "no_relevant_signal": not bool(fallback_text),
        }

    interesting_posts: list[dict[str, str]] = []
    raw_posts = payload.get("interesting_posts")
    if isinstance(raw_posts, list):
        for item in raw_posts[:5]:
            if not isinstance(item, dict):
                continue
            post_id = _safe_perception_text(item.get("post_id"), 80)
            thought = _safe_perception_text(item.get("character_thought"), 180)
            if post_id and thought:
                interesting_posts.append(
                    {
                        "post_id": post_id,
                        "character_thought": thought,
                    }
                )

    character_thoughts = _safe_perception_text(
        payload.get("character_thoughts"), 500
    )
    post_seed = _safe_perception_text(payload.get("post_seed"), 240)
    no_relevant_signal = bool(payload.get("no_relevant_signal"))
    if not interesting_posts and not character_thoughts and not post_seed:
        no_relevant_signal = True

    normalized = {
        "interesting_posts": interesting_posts,
        "character_thoughts": character_thoughts,
        "post_seed": post_seed,
        "no_relevant_signal": no_relevant_signal,
    }
    return json.dumps(normalized, ensure_ascii=False)


def _feed_perception_payload(
    *,
    status: str,
    reason: str,
    character_thoughts: str = "",
    post_seed: str = "",
    no_relevant_signal: bool = True,
) -> tuple[str, dict[str, Any]]:
    payload = {
        "interesting_posts": [],
        "character_thoughts": character_thoughts,
        "post_seed": post_seed,
        "no_relevant_signal": no_relevant_signal,
    }
    return (
        json.dumps(payload, ensure_ascii=False),
        {"status": status, "reason": reason, "perception": payload},
    )


def _fallback_action_decision(
    *,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    feed_cue: models.AgentFeedCue | None,
    allow_thread_tool: bool,
) -> str:
    allowed_actions = (
        activity_policy.allowed_actions if activity_policy else DEFAULT_ACTIVITY_ACTIONS
    )
    allowed = set(allowed_actions)
    if feed_cue is not None and "post" in allowed:
        return "create_post"
    if allow_thread_tool and "reply" in allowed:
        return "existing_post_interaction"
    if {"like", "repost", "follow"} & allowed:
        return "existing_post_interaction"
    if "post" in allowed:
        return "create_post"
    if "observe" in allowed:
        return "observe"
    if "unfollow" in allowed:
        return "relationship_review"
    return "observe"


def _normalize_action_decision_text(
    text: str,
    *,
    activity_policy: agent_activity_policy.ActivityPolicy | None,
    feed_cue: models.AgentFeedCue | None,
    allow_thread_tool: bool,
) -> dict[str, Any]:
    payload = _parse_json_object(text) or {}
    decision_type = _safe_perception_text(payload.get("decision_type"), 80)
    if decision_type not in ACTION_DECISION_TYPES:
        decision_type = _fallback_action_decision(
            activity_policy=activity_policy,
            feed_cue=feed_cue,
            allow_thread_tool=allow_thread_tool,
        )

    allowed_actions = (
        activity_policy.allowed_actions if activity_policy else DEFAULT_ACTIVITY_ACTIONS
    )
    allowed = set(allowed_actions)
    if decision_type == "create_post" and "post" not in allowed:
        decision_type = _fallback_action_decision(
            activity_policy=activity_policy,
            feed_cue=None,
            allow_thread_tool=allow_thread_tool,
        )
    if decision_type == "observe" and "observe" not in allowed:
        decision_type = _fallback_action_decision(
            activity_policy=activity_policy,
            feed_cue=None,
            allow_thread_tool=allow_thread_tool,
        )

    needs_thread = (
        decision_type == "existing_post_interaction"
        and allow_thread_tool
        and bool(payload.get("needs_thread"))
    )
    focus_post_ids: list[str] = []
    raw_focus_post_ids = payload.get("focus_post_ids")
    if isinstance(raw_focus_post_ids, list):
        for item in raw_focus_post_ids[:5]:
            value = _safe_perception_text(item, 80)
            if value:
                focus_post_ids.append(value)
    return {
        "decision_type": decision_type,
        "needs_thread": needs_thread,
        "thread_candidate_id": _safe_perception_text(
            payload.get("thread_candidate_id"), 120
        ),
        "focus_post_ids": focus_post_ids,
        "reason": _safe_perception_text(payload.get("reason"), 400),
    }
