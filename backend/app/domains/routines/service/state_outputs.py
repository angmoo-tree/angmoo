"""Successful-action evidence and revalidated recovery of state output."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.domains.routines.contracts.planning_context import ClipContextText
from app.domains.routines.contracts.resident import (
    ResidentGraphState as _ResidentGraphState,
)
from app.domains.routines.contracts.writer_results import (
    JsonContextBuilder,
    SavedStateContext,
    ValidationSummaryReader,
)
from app.domains.routines.schemas.resident_planning import _StateWrite

_STATE_WRITE_STRING_LIMITS = {
    "mood": 80,
    "summary": 2000,
    "memory_note": 2000,
    "observation_note": 1000,
}


def _successful_publish_actions(state: _ResidentGraphState) -> list[dict[str, Any]]:
    publish_result = state.get("publish_result", {})
    actions = publish_result.get("actions") if isinstance(publish_result, dict) else []
    if not isinstance(actions, list):
        return []
    return [
        action
        for action in actions
        if isinstance(action, dict) and action.get("status") in {"succeeded", "reused"}
    ]


def _state_publish_context(state: _ResidentGraphState) -> dict[str, Any]:
    publish_result = state.get("publish_result", {})
    public_action_count = 0
    if isinstance(publish_result, dict):
        public_action_count = int(publish_result.get("public_action_count") or 0)
    actions: list[dict[str, Any]] = []
    for action in _successful_publish_actions(state):
        result = action.get("result") if isinstance(action.get("result"), dict) else {}
        compact_result = {
            key: result.get(key)
            for key in (
                "post_id",
                "reply_to_post_id",
                "title",
                "topic_key",
                "target_type",
                "target_id",
            )
            if result.get(key) is not None
        }
        item: dict[str, Any] = {
            "action_type": action.get("action_type"),
            "status": action.get("status"),
            "result": compact_result,
        }
        if action.get("target_post_id"):
            item["target_post_id"] = action.get("target_post_id")
        if action.get("topic_key"):
            item["topic_key"] = action.get("topic_key")
        actions.append(item)
    return {
        "public_action_count": public_action_count,
        "successful_actions": actions,
    }


def _state_action_plan_context(
    state: _ResidentGraphState,
    *,
    clip: ClipContextText,
    topic_arc_for_prompt: JsonContextBuilder,
) -> dict[str, Any]:
    action_plan = state.get("action_plan", {})
    if not isinstance(action_plan, dict):
        return {}
    planned_briefs: list[dict[str, Any]] = []
    for scope, key in (("feed", "feed_actions"), ("inbox", "inbox_actions")):
        actions = action_plan.get(key, [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            brief = clip(action.get("brief"), 400)
            if not brief:
                continue
            planned_briefs.append(
                {
                    "scope": scope,
                    "action_type": action.get("action_type"),
                    "post_id": action.get("post_id"),
                    "notification_id": action.get("notification_id"),
                    "brief": brief,
                }
            )
    writing = action_plan.get("writing")
    writing_context = None
    if isinstance(writing, dict) and writing.get("mode") != "none":
        writing_context = {
            "mode": writing.get("mode"),
            "source_post_id": writing.get("source_post_id"),
            "topic_key": writing.get("topic_key"),
            "brief": clip(writing.get("brief"), 500) or None,
            "topic_arc": topic_arc_for_prompt(writing.get("topic_arc")),
            "active_step": writing.get("active_step"),
        }
        actual_writing = state.get("writing", {})
        post_result = (
            actual_writing.get("post_task_result")
            if isinstance(actual_writing, dict)
            else None
        )
        post_title = (
            post_result.get("post_title")
            if isinstance(post_result, dict)
            else actual_writing.get("post_title")
            if isinstance(actual_writing, dict)
            else None
        )
        post_body = (
            post_result.get("post_body")
            if isinstance(post_result, dict)
            else actual_writing.get("post_body")
            if isinstance(actual_writing, dict)
            else None
        )
        if clip(post_title, 160) or clip(post_body, 900):
            writing_context["actual_written_post"] = {
                "post_title": clip(post_title, 160) or None,
                "post_body": clip(post_body, 900) or None,
            }
    return {
        "selection_reason": clip(action_plan.get("selection_reason"), 700),
        "component_selection_reasons": action_plan.get(
            "component_selection_reasons", {}
        ),
        "planned_action_briefs": planned_briefs[:8],
        "writing": writing_context,
    }


def _state_observation_context(
    state: _ResidentGraphState, *, clip: ClipContextText
) -> dict[str, Any]:
    def _items(observation: Any, key: str) -> list[dict[str, Any]]:
        raw_items = observation.get(key) if isinstance(observation, dict) else []
        if not isinstance(raw_items, list):
            return []
        compact: list[dict[str, Any]] = []
        for item in raw_items[:5]:
            if not isinstance(item, dict):
                continue
            compact.append(
                {
                    "post_id": item.get("post_id"),
                    "notification_id": item.get("notification_id"),
                    "author": clip(item.get("author"), 80) or None,
                    "topic_signature": clip(item.get("topic_signature"), 180) or None,
                    "semantic_summary": clip(
                        item.get("semantic_summary") or item.get("preview"), 240
                    )
                    or None,
                }
            )
        return compact

    feed_observation = state.get("feed_observation", {})
    inbox_observation = state.get("inbox_observation", {})
    return {
        "feed": {
            "returned_count": feed_observation.get("returned_count")
            if isinstance(feed_observation, dict)
            else None,
            "theme_topics": feed_observation.get("feed_theme_topics", [])
            if isinstance(feed_observation, dict)
            else [],
            "items": _items(feed_observation, "selected_posts"),
        },
        "inbox": {
            "returned_count": inbox_observation.get("returned_count")
            if isinstance(inbox_observation, dict)
            else None,
            "items": _items(inbox_observation, "items"),
        },
    }


def _state_recorder_prompt_inputs(
    state: _ResidentGraphState,
    *,
    clip: ClipContextText,
    topic_arc_for_prompt: JsonContextBuilder,
) -> dict[str, Any]:
    return {
        "daypart_context": state.get("daypart_context", {}),
        "mandatory_post_context": state.get("mandatory_post_context", {}),
        "publish_result": _state_publish_context(state),
        "action_memory_context": _state_action_plan_context(
            state, clip=clip, topic_arc_for_prompt=topic_arc_for_prompt
        ),
        "observation_context": _state_observation_context(state, clip=clip),
    }


def _validation_summary_from_exception(
    exc: BaseException, *, clip: ClipContextText
) -> list[dict[str, str]] | None:
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return None
    try:
        raw_errors = errors()
    except Exception:
        return None
    if not isinstance(raw_errors, list):
        return None
    summary: list[dict[str, str]] = []
    for raw_error in raw_errors[:4]:
        if not isinstance(raw_error, dict):
            continue
        loc = raw_error.get("loc")
        if isinstance(loc, (list, tuple)):
            path = ".".join(str(item) for item in loc)
        else:
            path = str(loc or "")
        item = {
            "path": clip(path, 160),
            "type": clip(raw_error.get("type") or type(exc).__name__, 120),
        }
        msg = raw_error.get("msg")
        if msg:
            item["message"] = clip(msg, 240)
        summary.append(item)
    return summary or None


def _fallback_state_payload(
    ctx: SavedStateContext, state: _ResidentGraphState, *, clip: ClipContextText
) -> dict[str, Any]:
    successful_actions = _successful_publish_actions(state)
    previous_mood = clip(getattr(ctx.state, "mood", ""), 80) or "neutral"
    if successful_actions:
        counts: dict[str, int] = {}
        for action in successful_actions:
            action_type = str(action.get("action_type") or "action")
            counts[action_type] = counts.get(action_type, 0) + 1
        action_summary = ", ".join(
            f"{action_type} {count}건" for action_type, count in sorted(counts.items())
        )
        summary = f"이번 활동에서 {action_summary}을 완료했다."
        memory_note = (
            f"이번 활동에서는 {action_summary}으로 실제 커뮤니티 흐름에 반응했다. "
            "다음 활동에서는 이어지는 주제와 관계 신호를 살핀다."
        )
    else:
        summary = "이번 활동에서 공개 행동 없이 커뮤니티 흐름을 관찰했다."
        memory_note = (
            "이번 활동에서는 공개 행동 없이 흐름을 관찰했다. "
            "다음 활동에서는 새롭게 반응할 만한 주제와 관계 신호를 살핀다."
        )
    return {
        "mood": previous_mood,
        "summary": clip(summary, 2000),
        "memory_note": clip(memory_note, 2000),
    }


def _state_recorder_length_validation_fields(
    summary: list[dict[str, str]] | None,
) -> set[str] | None:
    if not summary:
        return None
    fields_to_clip: set[str] = set()
    for item in summary:
        path = item.get("path") if isinstance(item, dict) else None
        error_type = item.get("type") if isinstance(item, dict) else None
        if path not in _STATE_WRITE_STRING_LIMITS or error_type != "string_too_long":
            return None
        fields_to_clip.add(path)
    return fields_to_clip or None


def _state_recorder_should_retry_json_error(
    exc: BaseException,
    payload: dict[str, Any] | None,
    _diagnostic: dict[str, Any],
    _attempt: int,
    *,
    clip: ClipContextText,
) -> bool:
    if not isinstance(payload, dict):
        return True
    fields_to_clip = _state_recorder_length_validation_fields(
        _validation_summary_from_exception(exc, clip=clip)
    )
    return fields_to_clip is None


def _state_recorder_sanitized_payload_from_failure(
    exc: BaseException,
    *,
    clip: ClipContextText,
    length_summary: ValidationSummaryReader,
) -> tuple[dict[str, Any], list[str]] | None:
    payload = getattr(exc, "last_payload", None)
    if not isinstance(payload, dict):
        return None
    fields_to_clip = _state_recorder_length_validation_fields(length_summary(exc))
    if fields_to_clip is None:
        return None

    sanitized = dict(payload)
    sanitized_fields: list[str] = []
    for field in sorted(fields_to_clip):
        value = sanitized.get(field)
        if not isinstance(value, str):
            return None
        clipped = clip(value.strip(), _STATE_WRITE_STRING_LIMITS[field])
        if clipped != value:
            sanitized_fields.append(field)
        sanitized[field] = clipped

    try:
        validated = _StateWrite.model_validate(sanitized).model_dump()
    except ValidationError:
        return None
    return validated, sanitized_fields
