"""Persona topic criteria, repeat avoidance, and deterministic posting initiative."""

from __future__ import annotations

import hashlib
from typing import Any

from app.domains.routines.contracts.planning_context import (
    ClipContextText,
    ResidentPlanningContext,
)
from app.domains.routines.repository import (
    independent_topics as independent_topic_queries,
)

_INDEPENDENT_TOPIC_PROMPT_COUNT = 10

_INDEPENDENT_TOPIC_SELECTION_SALT = "independent_topics"


def _planner_tendency_profile(ctx: ResidentPlanningContext) -> dict[str, Any]:
    profile = getattr(ctx.activity_policy, "planner_tendency_profile", None)
    return profile if isinstance(profile, dict) else {}


def _feed_seed_interest_criteria(
    ctx: ResidentPlanningContext, *, clip: ClipContextText
) -> str:
    criteria = _planner_tendency_profile(ctx).get("feed_seed_interest_criteria")
    return clip(criteria, 1200)


def _independent_post_topics(
    ctx: ResidentPlanningContext, *, clip: ClipContextText
) -> list[dict[str, str]]:
    raw_topics = _planner_tendency_profile(ctx).get("independent_post_topics")
    if not isinstance(raw_topics, list):
        return []
    topics: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for raw in raw_topics:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        label = str(raw.get("label") or "").strip()
        prompt = str(raw.get("prompt") or "").strip()
        if not key or not label or not prompt or key in seen_keys:
            continue
        seen_keys.add(key)
        topics.append(
            {
                "key": clip(key, 80),
                "label": clip(label, 80),
                "prompt": clip(prompt, 300),
            }
        )
    return topics


def _select_independent_post_topics_for_tick(
    ctx: ResidentPlanningContext, topics: list[dict[str, str]]
) -> list[dict[str, str]]:
    if len(topics) <= _INDEPENDENT_TOPIC_PROMPT_COUNT:
        return list(topics)
    recent_topic_keys = independent_topic_queries._recent_independent_topic_keys(ctx)
    decorated: list[tuple[int, str, int, dict[str, str]]] = []
    for index, topic in enumerate(topics):
        key = str(topic.get("key") or "").strip()
        digest = hashlib.sha256(
            (
                f"{ctx.run_id}:{ctx.character.id}:"
                f"{_INDEPENDENT_TOPIC_SELECTION_SALT}:{key}:{index}"
            ).encode("utf-8")
        ).hexdigest()
        recent_rank = 1 if key in recent_topic_keys else 0
        decorated.append((recent_rank, digest, index, topic))
    decorated.sort()
    return [
        topic
        for _recent_rank, _digest, _index, topic in decorated[
            :_INDEPENDENT_TOPIC_PROMPT_COUNT
        ]
    ]


def _independent_post_initiative(
    ctx: ResidentPlanningContext,
) -> dict[str, str | float] | None:
    profile = _planner_tendency_profile(ctx)
    raw = profile.get("independent_post_initiative")
    if not isinstance(raw, dict):
        return None
    level = str(raw.get("level") or "").strip()
    if level not in {"very_low", "low", "medium", "high", "very_high"}:
        return None
    try:
        probability = float(raw.get("tick_probability"))
    except (TypeError, ValueError):
        return None
    probability = max(0.0, min(probability, 0.45))
    return {"level": level, "tick_probability": round(probability, 4)}


def _deterministic_independent_post_roll(ctx: ResidentPlanningContext) -> float:
    digest = hashlib.sha256(
        f"{ctx.run_id}:{ctx.character.id}:independent_post".encode("utf-8")
    ).digest()
    return round(int.from_bytes(digest[:8], "big") / float(2**64 - 1), 6)


def _build_independent_post_roll(
    ctx: ResidentPlanningContext, *, clip: ClipContextText
) -> dict[str, Any]:
    initiative = _independent_post_initiative(ctx)
    all_topics = _independent_post_topics(ctx, clip=clip)
    used_topic_keys_today = independent_topic_queries._today_independent_topic_keys(ctx)
    topics = [
        topic
        for topic in all_topics
        if str(topic.get("key") or "").strip() not in used_topic_keys_today
    ]
    allowed = "post" in set(ctx.activity_policy.allowed_actions)
    result: dict[str, Any] = {
        "available": False,
        "level": initiative.get("level") if initiative else None,
        "tick_probability": (
            initiative.get("tick_probability") if initiative else None
        ),
        "roll": None,
        "passed": False,
        "topics": [],
        "topic_pool_size": len(all_topics),
        "topic_prompt_count": 0,
        "used_topic_keys_today": sorted(used_topic_keys_today),
        "available_topic_count_after_today_filter": len(topics),
        "blocked_reason": None,
    }
    if initiative is None:
        result["blocked_reason"] = "planner_tendency_profile_missing"
        return result
    if not allowed:
        result["blocked_reason"] = "post_not_allowed"
        return result
    if not all_topics:
        result["blocked_reason"] = "independent_post_topics_missing"
        return result
    if not topics:
        result["blocked_reason"] = "independent_topics_exhausted_today"
        return result
    roll = _deterministic_independent_post_roll(ctx)
    probability = float(initiative["tick_probability"])
    passed = roll <= probability
    selected_topics = (
        _select_independent_post_topics_for_tick(ctx, topics) if passed else []
    )
    result.update(
        {
            "available": True,
            "roll": roll,
            "passed": passed,
            "topics": selected_topics,
            "topic_prompt_count": len(selected_topics),
            "blocked_reason": None if passed else "roll_failed",
        }
    )
    return result


def _base_independent_topic_candidates(
    ctx: ResidentPlanningContext, *, clip: ClipContextText
) -> list[dict[str, Any]]:
    all_topics = _independent_post_topics(ctx, clip=clip)
    used = independent_topic_queries._today_independent_topic_keys(ctx)
    topics = [
        topic for topic in all_topics if str(topic.get("key") or "").strip() not in used
    ]
    return _select_independent_post_topics_for_tick(ctx, topics) if topics else []
