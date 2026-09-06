"""Select valid feed seeds and preserve mandatory independent writing intent."""

from __future__ import annotations

from typing import Any

from app.domains.routines.contracts.planning_context import (
    ClipContextText,
    ResidentPlanningContext,
)
from app.domains.routines.policies.writing_contract import (
    _OWNER_FEED_CUE_MODE,
    _RELATIONSHIP_POINT_MODE,
    _coerce_action_step_count,
    _coerce_writing_form,
    _mandatory_post_required,
    _subjective_plan_fields,
)


def _feed_seed_candidates(feed_observation: dict[str, Any]) -> list[dict[str, Any]]:
    raw = feed_observation.get("seed_candidates")
    candidates = raw if isinstance(raw, list) else []
    return [
        item
        for item in candidates
        if isinstance(item, dict)
        and item.get("author_character_id")
        and item.get("post_id")
        and not item.get("is_self")
    ][:30]


def _normalize_feed_seed_selection(
    selection: dict[str, Any],
    *,
    candidates: list[dict[str, Any]],
    clip: ClipContextText,
) -> dict[str, Any]:
    candidate_by_post_id = {str(item.get("post_id")): item for item in candidates}
    post_id = str(selection.get("post_id") or "").strip()
    candidate = candidate_by_post_id.get(post_id)
    if selection.get("mode") != "use_seed" or candidate is None:
        return {"mode": "none", "mention_required": False}
    author_character_id = str(candidate.get("author_character_id") or "").strip()
    author_handle = str(candidate.get("author_handle") or "").strip()
    if not author_character_id or not author_handle:
        return {"mode": "none", "mention_required": False}
    return {
        "mode": "use_seed",
        "post_id": post_id,
        "author_character_id": author_character_id,
        "author_handle": author_handle,
        "author_name": clip(candidate.get("author_name"), 120) or None,
        "seed_brief": clip(
            selection.get("seed_brief") or candidate.get("body_summary"), 800
        )
        or None,
        "source_body": clip(candidate.get("source_body"), 1000) or None,
        "use_reason": clip(selection.get("use_reason"), 500) or None,
        "mention_required": True,
    }


def _normalize_independent_topic_composition(
    ctx: ResidentPlanningContext,
    raw: dict[str, Any],
    *,
    mandatory_context: dict[str, Any],
    clip: ClipContextText,
) -> dict[str, Any]:
    owner_cue = mandatory_context.get("owner_feed_cue")
    if isinstance(owner_cue, dict) and clip(owner_cue.get("topic"), 800):
        return {
            "source": "owner_feed_cue",
            "feed_cue_id": owner_cue.get("id"),
            "topic_key": None,
            "relationship_point_id": None,
            "writing_form": "thought",
            "action_step_count": 1,
            "brief": clip(owner_cue.get("topic"), 1000),
            "use_post_seed": False,
            "seed_post_id": None,
            "mention_target_handle": None,
            "selection_reason": "owner_feed_cue_highest_priority",
        }
    if not mandatory_context.get("post_required"):
        return {
            "source": "base_topic",
            "topic_key": None,
            "relationship_point_id": None,
            "writing_form": "thought",
            "action_step_count": 1,
            "brief": mandatory_context.get("blocked_reason") or "post not required",
            "use_post_seed": False,
            "seed_post_id": None,
            "mention_target_handle": None,
            "selection_reason": "post_not_required",
            "skip_reason": mandatory_context.get("blocked_reason"),
        }
    base_topics = {
        str(topic.get("key") or ""): topic
        for topic in mandatory_context.get("base_topic_candidates", [])
        if isinstance(topic, dict)
    }
    relationship_points = {
        int(point["id"]): point
        for point in mandatory_context.get("relationship_point_candidates", [])
        if isinstance(point, dict) and isinstance(point.get("id"), int)
    }
    source = str(raw.get("source") or "").strip()
    relationship_point_id = raw.get("relationship_point_id")
    if isinstance(relationship_point_id, bool):
        relationship_point_id = None
    try:
        relationship_point_id = int(relationship_point_id)
    except (TypeError, ValueError):
        relationship_point_id = None
    topic_key = str(raw.get("topic_key") or "").strip()
    if source == "relationship_point" and relationship_point_id in relationship_points:
        point = relationship_points[relationship_point_id]
        brief = clip(raw.get("brief") or point.get("topic_brief"), 1000)
        handle = str(point.get("source_handle") or "").strip()
        return {
            "source": "relationship_point",
            "topic_key": None,
            "relationship_point_id": relationship_point_id,
            "writing_form": _coerce_writing_form(raw.get("writing_form")),
            "action_step_count": _coerce_action_step_count(
                raw.get("action_step_count")
            ),
            "brief": brief
            or f"@{handle}와 이어진 대화에서 생긴 생각을 지금의 시점에 맞게 쓴다.",
            "use_post_seed": False,
            "seed_post_id": None,
            "source_post_id": point.get("source_post_id"),
            "source_body": point.get("source_post_body"),
            "mention_target_handle": handle,
            "selection_reason": clip(raw.get("selection_reason"), 600)
            or "relationship point selected",
            **_subjective_plan_fields(raw),
        }
    if topic_key not in base_topics and base_topics:
        topic_key = next(iter(base_topics))
    topic = base_topics.get(topic_key) if topic_key else None
    brief = clip(raw.get("brief"), 1000)
    if not brief and isinstance(topic, dict):
        brief = clip(topic.get("prompt") or topic.get("label"), 1000)
    selected_seed = mandatory_context.get("selected_feed_seed")
    use_seed = (
        bool(raw.get("use_post_seed"))
        and isinstance(selected_seed, dict)
        and selected_seed.get("mode") == "use_seed"
    )
    return {
        "source": "base_topic",
        "topic_key": topic_key or None,
        "relationship_point_id": None,
        "writing_form": _coerce_writing_form(raw.get("writing_form")),
        "action_step_count": _coerce_action_step_count(raw.get("action_step_count")),
        "brief": brief or "캐릭터의 평소 독립 주제에서 지금 쓸 만한 글감을 고른다.",
        "use_post_seed": use_seed,
        "seed_post_id": selected_seed.get("post_id") if use_seed else None,
        "mention_target_handle": selected_seed.get("author_handle")
        if use_seed
        else None,
        "selection_reason": clip(raw.get("selection_reason"), 600)
        or "base independent topic selected",
        **_subjective_plan_fields(raw),
    }


def _writing_from_topic_composition(
    composition: dict[str, Any],
    *,
    selected_feed_seed: dict[str, Any] | None,
    clip: ClipContextText,
) -> dict[str, Any]:
    source = composition.get("source")
    brief = clip(composition.get("brief"), 1000)
    if composition.get("skip_reason"):
        return {
            "mode": "none",
            "brief": None,
            "source_post_id": None,
            "skip_reason": composition.get("skip_reason"),
        }
    if source == "owner_feed_cue":
        return {
            "mode": _OWNER_FEED_CUE_MODE,
            "feed_cue_id": composition.get("feed_cue_id"),
            "brief": brief,
            "source_post_id": None,
            "topic_key": None,
            "writing_form": composition.get("writing_form"),
            "action_step_count": composition.get("action_step_count"),
            **_subjective_plan_fields(composition),
        }
    if source == "relationship_point":
        handle = str(composition.get("mention_target_handle") or "").strip()
        return {
            "mode": _RELATIONSHIP_POINT_MODE,
            "relationship_point_id": composition.get("relationship_point_id"),
            "brief": brief,
            "source_post_id": composition.get("source_post_id"),
            "topic_key": None,
            "source_mix": "relationship_point",
            "mention_required": bool(handle),
            "mention_target_handle": handle,
            "source_body": composition.get("source_body"),
            "writing_form": composition.get("writing_form"),
            "action_step_count": composition.get("action_step_count"),
            **_subjective_plan_fields(composition),
        }
    writing = {
        "mode": "independent",
        "brief": brief,
        "source_post_id": None,
        "topic_key": composition.get("topic_key"),
        "source_mix": "none",
        "mention_required": False,
        "mention_target_handle": None,
        "writing_form": composition.get("writing_form"),
        "action_step_count": composition.get("action_step_count"),
        **_subjective_plan_fields(composition),
    }
    if composition.get("use_post_seed") and isinstance(selected_feed_seed, dict):
        writing["source_mix"] = "feed_seed"
        writing["source_post_id"] = selected_feed_seed.get("post_id")
        writing["selected_feed_seed"] = selected_feed_seed
        writing["mention_required"] = bool(selected_feed_seed.get("mention_required"))
        writing["mention_target_handle"] = selected_feed_seed.get("author_handle")
        writing["mention_target_character_id"] = selected_feed_seed.get(
            "author_character_id"
        )
    return writing


def _mandatory_root_writing_from_composition(
    ctx: ResidentPlanningContext,
    *,
    mandatory_context: dict[str, Any],
    composition: dict[str, Any] | None,
    selected_feed_seed: dict[str, Any] | None,
    clip: ClipContextText,
) -> dict[str, Any] | None:
    if not _mandatory_post_required(mandatory_context):
        return None
    if not isinstance(composition, dict):
        composition = _normalize_independent_topic_composition(
            ctx,
            {"source": "base_topic"},
            mandatory_context=mandatory_context,
            clip=clip,
        )
    writing = _writing_from_topic_composition(
        composition, selected_feed_seed=selected_feed_seed, clip=clip
    )
    if not isinstance(writing, dict) or writing.get("mode") == "none":
        return None
    return writing


def _restore_mandatory_root_writing(
    ctx: ResidentPlanningContext,
    plan: dict[str, Any],
    *,
    mandatory_context: dict[str, Any],
    composition: dict[str, Any] | None,
    selected_feed_seed: dict[str, Any] | None,
    clip: ClipContextText,
) -> dict[str, Any]:
    if not _mandatory_post_required(mandatory_context):
        return plan
    writing = plan.get("writing") if isinstance(plan, dict) else None
    if isinstance(writing, dict) and writing.get("mode") != "none":
        return plan
    restored = _mandatory_root_writing_from_composition(
        ctx,
        mandatory_context=mandatory_context,
        composition=composition,
        selected_feed_seed=selected_feed_seed,
        clip=clip,
    )
    if restored is None:
        return plan
    restored = dict(restored)
    original_skip_reason = (
        writing.get("skip_reason") if isinstance(writing, dict) else None
    )
    if original_skip_reason:
        restored["restored_from_skip_reason"] = original_skip_reason
    restored["mandatory_backend_selected"] = True
    updated = dict(plan)
    updated["writing"] = restored
    updated["mandatory_root_post_enforced"] = True
    return updated
