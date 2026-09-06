"""Deterministic execution identities, result matching and successful evidence."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.domains.routines.contracts.action_planning import ReplyTaskIdentifier
from app.domains.routines.contracts.planning_context import ResidentPlanningContext
from app.domains.routines.contracts.resident import (
    ResidentGraphState as _ResidentGraphState,
)
from app.domains.routines.contracts.writer_results import (
    ExecutionCallTrace,
    JsonContextBuilder,
)
from app.domains.routines.policies.writer_outputs import _reply_task_results_by_id


def _brief_hash(*parts: Any) -> str:
    text = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _action_signature(
    *,
    run_id: str,
    scope: str,
    action_type: str,
    target_id: str | None,
    brief_hash: str | None,
) -> str:
    raw = "|".join([run_id, scope, action_type, target_id or "", brief_hash or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_reply_body_for_duplicate(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(r"([.!?…~ㅋㅎㅠㅜ])\1+", r"\1", text)
    return text.casefold()


def _skipped_public_action(
    *,
    action_type: str,
    target_post_id: str | None,
    failure_class: str,
    writer_validation: dict[str, Any] | None = None,
    blocked_field: str | None = None,
    blocked_category: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "skipped",
        "action_type": action_type,
        "target_post_id": target_post_id,
        "result": {},
        "failure_class": failure_class,
    }
    if writer_validation is not None:
        payload["writer_validation"] = writer_validation
    if blocked_field is not None:
        payload["blocked_field"] = blocked_field
    if blocked_category is not None:
        payload["blocked_category"] = blocked_category
    if message is not None:
        payload["message"] = message
    return payload


def _record_topic_arc_progress(
    ctx: ResidentPlanningContext,
    *,
    writing_plan: dict[str, Any],
    post_id: str,
    coerce_topic_arc: JsonContextBuilder,
) -> dict[str, Any] | None:
    topic_arc = coerce_topic_arc(writing_plan.get("topic_arc"))
    if not topic_arc:
        return None
    return {
        "status": "ignored",
        "reason": "topic_arc_disabled_v8",
        "arc_id": topic_arc.get("arc_id"),
    }


def _reply_body(
    writing: dict[str, Any],
    *,
    scope: str,
    index: int,
    post_id: str,
    reply_task_id: ReplyTaskIdentifier,
) -> tuple[str | None, str | None, dict[str, Any]]:
    task_id = reply_task_id(scope=scope, index=index, post_id=post_id)
    writer_validation: dict[str, Any] = {
        "task_id": task_id,
        "target_post_id": post_id,
        "repair_attempted": False,
        "repair_succeeded": False,
    }
    task_result = _reply_task_results_by_id(writing).get(task_id)
    if isinstance(task_result, dict):
        writer_validation.update(
            {
                "writer_node": task_result.get("writer_node"),
                "repair_attempted": bool(task_result.get("repair_attempted")),
                "repair_succeeded": bool(task_result.get("repair_succeeded")),
            }
        )
        if str(task_result.get("post_id") or "").strip() != post_id:
            return None, "reply_body_post_id_mismatch", writer_validation
        body = str(task_result.get("body") or "").strip()
        if body:
            return body, None, writer_validation
        return None, "reply_body_missing", writer_validation

    matched_scope_index = False
    for item in writing.get("reply_bodies", []) if isinstance(writing, dict) else []:
        if (
            isinstance(item, dict)
            and item.get("scope") == scope
            and int(item.get("index", -1)) == index
        ):
            matched_scope_index = True
            if str(item.get("post_id") or "").strip() != post_id:
                continue
            body = str(item.get("body") or "").strip()
            if body:
                writer_validation.update(
                    {
                        "task_id": item.get("task_id") or task_id,
                        "writer_node": item.get("writer_node") or "legacy_reply_bodies",
                    }
                )
                return body, None, writer_validation
    if matched_scope_index:
        return None, "reply_body_post_id_mismatch", writer_validation
    return None, "reply_body_missing", writer_validation


def _successful_action_results(
    state: _ResidentGraphState, action_type: str
) -> list[dict[str, Any]]:
    publish_result = state.get("publish_result", {})
    actions = publish_result.get("actions") if isinstance(publish_result, dict) else []
    if not isinstance(actions, list):
        return []
    return [
        action
        for action in actions
        if isinstance(action, dict)
        and action.get("action_type") == action_type
        and action.get("status") in {"succeeded", "reused"}
        and isinstance(action.get("result"), dict)
    ]


def _writing_success_post_id(state: _ResidentGraphState) -> str | None:
    for action in _successful_action_results(state, "post"):
        result = action.get("result")
        if isinstance(result, dict) and result.get("post_id"):
            return str(result["post_id"])
    return None


def _inbox_lane_planner_invoked(tracker: ExecutionCallTrace) -> bool:
    return any(call.get("lane") == "inbox_action_planner" for call in tracker.calls)


def _inbox_lane_target_post_id(
    *,
    selected_actions: list[dict[str, Any]],
    action_results: list[dict[str, Any]],
    observation_items: list[dict[str, Any]],
) -> str | None:
    item_by_notification_id = {
        int(item["notification_id"]): item
        for item in observation_items
        if item.get("notification_id") is not None
    }
    for index, result in enumerate(action_results):
        if result.get("status") not in {"succeeded", "reused"}:
            continue
        action = selected_actions[index] if index < len(selected_actions) else {}
        post_id = str(action.get("post_id") or "").strip()
        if post_id:
            return post_id
        notification_id = action.get("notification_id")
        try:
            item = item_by_notification_id.get(int(notification_id))
        except (TypeError, ValueError):
            item = None
        if isinstance(item, dict):
            source_post_id = str(item.get("source_post_id") or "").strip()
            if source_post_id:
                return source_post_id
    return None
