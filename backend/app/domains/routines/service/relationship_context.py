"""Activity selection from relationship signals, without foreign owner SQL."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.domains.routines.contracts.context_reads import (
    RelationshipContextWorkflows,
    ResidentReadContext,
)
from app.domains.routines.service import activity_logs

_RELATIONSHIP_MEMORY_EVENT_TYPES = {
    "observation_feed",
    "observation_inbox",
    "relationship_review",
    "unfollow_watch",
}

_REPLY_TARGET_ALREADY_ANSWERED = "reply_target_already_answered_by_character"


def _tendency_action_note(
    ctx: ResidentReadContext, action: str, *, workflows: RelationshipContextWorkflows
) -> str:
    ranges = getattr(ctx.activity_policy, "tendency_action_ranges", None)
    if not isinstance(ranges, dict):
        return ""
    item = ranges.get(action)
    if not isinstance(item, dict):
        return ""
    return workflows.clip(item.get("note"), 500)


def _relationship_daypart_memory(
    ctx: ResidentReadContext, *, workflows: RelationshipContextWorkflows
) -> list[dict[str, Any]]:
    memory: list[dict[str, Any]] = []
    for event in workflows.history(ctx):
        if event.get("event_type") not in _RELATIONSHIP_MEMORY_EVENT_TYPES:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        memory.append(
            {
                "event_type": event.get("event_type"),
                "source_post_id": event.get("source_post_id"),
                "notification_id": event.get("notification_id"),
                "summary": event.get("summary"),
                "payload": {
                    key: payload.get(key)
                    for key in (
                        "author_character_id",
                        "actor_character_id",
                        "target_character_id",
                        "available_actions",
                        "relationship_target",
                        "relationship_signal",
                        "reason_tag",
                        "decision",
                    )
                    if key in payload
                },
                "provided_at": event.get("provided_at"),
            }
        )
    return memory[-24:]


def _relationship_candidate_from_item(
    *,
    ctx: ResidentReadContext,
    source: Literal["feed", "inbox"],
    item: dict[str, Any],
    action_type: Literal["follow", "unfollow_watch"],
    workflows: RelationshipContextWorkflows,
) -> dict[str, Any] | None:
    if action_type == "follow" and "follow" not in set(
        ctx.activity_policy.allowed_actions
    ):
        return None
    if action_type == "unfollow_watch" and "unfollow" not in set(
        ctx.activity_policy.allowed_actions
    ):
        return None
    target_type = "character"
    target_id = None
    all_targets = item.get("action_targets") if isinstance(item, dict) else None
    if action_type == "follow" and isinstance(all_targets, dict):
        target = all_targets.get("follow")
        if isinstance(target, dict):
            target_type = str(target.get("target_type") or "")
            target_id = str(target.get("target_id") or "").strip() or None
    if action_type == "unfollow_watch":
        target_id = (
            str(
                item.get("author_character_id")
                or item.get("actor_character_id")
                or item.get("target_character_id")
                or ""
            ).strip()
            or None
        )
    if target_type != "character" or not target_id or target_id == ctx.character.id:
        return None
    currently_following = workflows.following(ctx, target_id)
    if action_type == "follow" and currently_following:
        return None
    if action_type == "unfollow_watch" and not currently_following:
        return None
    return {
        "source": source,
        "candidate_action": action_type,
        "target_type": "character",
        "target_id": target_id,
        "target_name": item.get("author") or item.get("actor_name"),
        "currently_following": currently_following,
        "post_id": item.get("post_id") or item.get("source_post_id"),
        "notification_id": item.get("notification_id"),
        "semantic_summary": workflows.clip(item.get("semantic_summary"), 500),
        "relationship_signal": workflows.clip(item.get("why_it_mattered"), 300)
        or "daypart observation",
    }


def _relationship_candidates_from_daypart_memory(
    ctx: ResidentReadContext, *, workflows: RelationshipContextWorkflows
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    allowed_actions = set(ctx.activity_policy.allowed_actions)
    if not ({"follow", "unfollow"} & allowed_actions):
        return candidates
    for event in _relationship_daypart_memory(ctx, workflows=workflows):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        relationship_target = payload.get("relationship_target")
        if "follow" in allowed_actions and isinstance(relationship_target, dict):
            target_id = str(relationship_target.get("target_id") or "").strip()
            if (
                str(relationship_target.get("candidate_action") or "") == "follow"
                and target_id
                and target_id != ctx.character.id
                and not workflows.following(ctx, target_id)
            ):
                candidates.append(
                    {
                        **relationship_target,
                        "source": "daypart_memory",
                        "candidate_action": "follow",
                        "target_type": "character",
                        "target_id": target_id,
                        "post_id": event.get("source_post_id")
                        or relationship_target.get("post_id"),
                        "notification_id": event.get("notification_id")
                        or relationship_target.get("notification_id"),
                        "semantic_summary": workflows.clip(
                            relationship_target.get("semantic_summary")
                            or event.get("summary"),
                            500,
                        ),
                        "relationship_signal": workflows.clip(
                            relationship_target.get("relationship_signal")
                            or event.get("summary"),
                            300,
                        ),
                    }
                )
        if "unfollow" not in allowed_actions:
            continue
        target_id = str(
            payload.get("target_character_id")
            or payload.get("actor_character_id")
            or payload.get("author_character_id")
            or ""
        ).strip()
        if not target_id or not workflows.following(ctx, target_id):
            continue
        signal = str(
            payload.get("relationship_signal")
            or payload.get("decision")
            or event.get("summary")
            or ""
        ).strip()
        if not signal:
            continue
        candidates.append(
            {
                "source": "daypart_memory",
                "candidate_action": "unfollow_watch",
                "target_type": "character",
                "target_id": target_id,
                "target_name": None,
                "currently_following": True,
                "post_id": event.get("source_post_id"),
                "notification_id": event.get("notification_id"),
                "semantic_summary": workflows.clip(event.get("summary"), 500),
                "relationship_signal": workflows.clip(signal, 300),
            }
        )
    return candidates


def _has_unfollow_watch(
    ctx: ResidentReadContext,
    *,
    target_id: str,
    reason_tag: str | None,
    workflows: RelationshipContextWorkflows,
) -> bool:
    if not target_id:
        return False
    for event in _relationship_daypart_memory(ctx, workflows=workflows):
        if event.get("event_type") != "unfollow_watch":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if str(payload.get("target_character_id") or "") != target_id:
            continue
        if reason_tag and str(payload.get("reason_tag") or "") != reason_tag:
            continue
        return True
    return False


def _inbox_lane_relationship_memory(
    ctx: ResidentReadContext, *, workflows: RelationshipContextWorkflows
) -> dict[str, Any]:
    logs = activity_logs.list_recent_activity(ctx.db, ctx.character.id, limit=12)
    return {
        "recent_activity": [
            {
                "action_type": log.action_type,
                "target_post_id": log.target_post_id,
                "reason": workflows.clip(log.reason, 240),
                "result": workflows.clip(log.result, 500),
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "daypart_history": workflows.history_prompt(ctx),
        "relationship_daypart_memory": _relationship_daypart_memory(
            ctx, workflows=workflows
        ),
        "relationship_point_candidates": [],
        "active_topic_arc": None,
    }


def _suppress_already_answered_reply_affordance(
    affordance: dict[str, Any],
    *,
    db: Session,
    character_id: str,
    post_id: str | None,
    workflows: RelationshipContextWorkflows,
) -> tuple[dict[str, Any], bool]:
    available_raw = affordance.get("available_actions")
    available = list(available_raw) if isinstance(available_raw, list) else []
    targets_raw = affordance.get("action_targets")
    targets = dict(targets_raw) if isinstance(targets_raw, dict) else {}
    blocked_raw = affordance.get("blocked_actions")
    blocked = dict(blocked_raw) if isinstance(blocked_raw, dict) else {}
    has_reply_signal = (
        "reply" in available
        or "reply" in targets
        or blocked.get("reply") == "reply_not_available"
    )
    if not has_reply_signal or not workflows.already_replied(
        db, character_id=character_id, post_id=post_id
    ):
        return affordance, False

    updated = dict(affordance)
    updated["available_actions"] = [item for item in available if item != "reply"]
    targets.pop("reply", None)
    updated["action_targets"] = targets
    blocked["reply"] = _REPLY_TARGET_ALREADY_ANSWERED
    updated["blocked_actions"] = blocked
    return updated, True
