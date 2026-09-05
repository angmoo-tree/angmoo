"""Match planner actions to observed items and allowed relationship actions."""

from __future__ import annotations
from typing import Any
from collections.abc import Iterable
from app.domains.routines.contracts.planning_context import ActivityPlanningContext


def _action_name_for_policy(action_type: str) -> str:
    return "post" if action_type == "create_post" else action_type


def _relationship_allowed_actions(ctx: ActivityPlanningContext) -> list[str]:
    allowed = set(ctx.activity_policy.allowed_actions)
    result: list[str] = []
    if "follow" in allowed:
        result.append("follow")
    if "unfollow" in allowed:
        result.extend(["unfollow_watch", "unfollow"])
    return result


def _strip_action_from_affordance(
    affordance: dict[str, Any], action_type: str
) -> dict[str, Any]:
    updated = dict(affordance)
    available = list(updated.get("available_actions") or [])
    updated["available_actions"] = [item for item in available if item != action_type]
    targets = dict(updated.get("action_targets") or {})
    targets.pop(action_type, None)
    updated["action_targets"] = targets
    return updated


def _dedupe_relationship_candidates(
    candidates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    evidence_counts: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        target_id = str(candidate.get("target_id") or "").strip()
        action_type = str(candidate.get("candidate_action") or "").strip()
        source_key = str(
            candidate.get("post_id") or candidate.get("notification_id") or ""
        )
        key = (action_type, target_id, source_key)
        if not target_id or not action_type or key in seen:
            continue
        seen.add(key)
        evidence_key = (action_type, target_id)
        evidence_counts[evidence_key] = evidence_counts.get(evidence_key, 0) + 1
        updated = dict(candidate)
        updated["evidence_count"] = evidence_counts[evidence_key]
        deduped.append(updated)
    return deduped[:12]


def _coerce_item_index(value: Any) -> int | None:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    return index if index >= 0 else None


def _observation_items(observation: dict[str, Any], *, scope: str) -> list[Any]:
    items_key = "selected_posts" if scope == "feed" else "items"
    items = observation.get(items_key, [])
    return items if isinstance(items, list) else []


def _normalize_planned_action_for_item(
    action: dict[str, Any],
    *,
    scope: str,
    item: dict[str, Any],
    action_type: str,
) -> dict[str, Any] | None:
    available = item.get("available_actions")
    if not isinstance(available, list) or action_type not in available:
        return None
    all_targets = item.get("action_targets")
    if not isinstance(all_targets, dict):
        return None
    target = all_targets.get(action_type)
    if not isinstance(target, dict):
        return None
    target_post_id = str(target.get("post_id") or "").strip() or None
    target_type = str(target.get("target_type") or "").strip() or None
    target_id = str(target.get("target_id") or "").strip() or None
    normalized = {
        key: value
        for key, value in action.items()
        if key not in {"item_index", "source_item_index"}
    }
    normalized["scope"] = scope
    normalized["action_type"] = action_type
    if target_post_id:
        normalized["post_id"] = target_post_id
    if target_type and target_id:
        normalized["target_type"] = target_type
        normalized["target_id"] = target_id
    if scope == "inbox" and item.get("notification_id") is not None:
        normalized["notification_id"] = int(item["notification_id"])
        notification_type = str(item.get("notification_type") or "").strip()
        if notification_type in {"reply", "mention", "joint_activity_started"}:
            normalized["notification_type"] = notification_type
        activity_proposal = item.get("activity_proposal")
        if isinstance(activity_proposal, dict):
            normalized["activity_proposal"] = dict(activity_proposal)
    return normalized


def _normalize_planned_action(
    action: dict[str, Any], *, scope: str, observation: dict[str, Any]
) -> dict[str, Any] | None:
    action_type = str(action.get("action_type") or "").strip()
    if not action_type:
        return None
    items = _observation_items(observation, scope=scope)
    if "item_index" in action:
        item_index = _coerce_item_index(action.get("item_index"))
        if item_index is None or item_index >= len(items):
            return None
        item = items[item_index]
        if not isinstance(item, dict):
            return None
        return _normalize_planned_action_for_item(
            action, scope=scope, item=item, action_type=action_type
        )
    for item in items:
        if not isinstance(item, dict):
            continue
        available = item.get("available_actions")
        if not isinstance(available, list) or action_type not in available:
            continue
        all_targets = item.get("action_targets")
        if not isinstance(all_targets, dict):
            continue
        target = all_targets.get(action_type)
        if not isinstance(target, dict):
            continue
        target_post_id = str(target.get("post_id") or "").strip() or None
        target_type = str(target.get("target_type") or "").strip() or None
        target_id = str(target.get("target_id") or "").strip() or None
        action_post_id = str(action.get("post_id") or "").strip() or None
        action_target_id = str(action.get("target_id") or "").strip() or None
        action_notification_id = action.get("notification_id")
        item_notification_id = item.get("notification_id")
        matched = False
        if scope == "inbox" and action_notification_id is not None:
            try:
                matched = int(action_notification_id) == int(item_notification_id or -1)
            except (TypeError, ValueError):
                matched = False
        if not matched and action_post_id and target_post_id:
            matched = action_post_id == target_post_id
        if not matched and action_target_id and target_id:
            matched = action_target_id == target_id
        if not matched and scope == "feed" and action_post_id == item.get("post_id"):
            matched = True
        if not matched:
            continue
        return _normalize_planned_action_for_item(
            action, scope=scope, item=item, action_type=action_type
        )
    return None


def _relationship_candidate_counts(
    candidates: list[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        action_type = str(candidate.get("candidate_action") or "").strip()
        target_id = str(candidate.get("target_id") or "").strip()
        if not action_type or not target_id:
            continue
        key = (action_type, target_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _matching_relationship_candidate(
    candidates: list[dict[str, Any]], *, action_type: str, target_id: str
) -> dict[str, Any] | None:
    for candidate in candidates:
        if (
            str(candidate.get("candidate_action") or "") == action_type
            and str(candidate.get("target_id") or "") == target_id
        ):
            return candidate
    return None
