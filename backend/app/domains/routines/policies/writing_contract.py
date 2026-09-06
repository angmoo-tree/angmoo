"""Determine required post output and keep the original writer result contract."""

from __future__ import annotations
from typing import Any


_OWNER_FEED_CUE_MODE = "owner_feed_cue"


_RELATIONSHIP_POINT_MODE = "relationship_point"


_POST_TEXT_WRITING_MODES = {
    "independent",
    "post_seed",
    "arc_continuation",
    _OWNER_FEED_CUE_MODE,
    _RELATIONSHIP_POINT_MODE,
}


_PERSONA_WRITER_MISSING_POST_TEXT = "persona_writer_missing_post_text"


def _coerce_writing_form(value: Any) -> str:
    text = str(value or "").strip()
    if text in {"thought", "community_observation", "monologue", "action"}:
        return text
    return "thought"


def _coerce_action_step_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(3, count))


def _subjective_plan_fields(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "motivation_kind",
            "motivation_text",
            "emotion_label",
            "emotion_text",
            "emotion_intensity",
        )
        if value.get(key) is not None
    }


def _mandatory_post_required(mandatory_context: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(mandatory_context, dict)
        and mandatory_context.get("post_required")
        and not mandatory_context.get("blocked_reason")
    )


def _writing_plan_requires_post_text(action_plan: dict[str, Any]) -> bool:
    writing = action_plan.get("writing") if isinstance(action_plan, dict) else None
    mode = writing.get("mode") if isinstance(writing, dict) else None
    return str(mode or "") in _POST_TEXT_WRITING_MODES


def _persona_writer_validation_meta(
    action_plan: dict[str, Any],
    writing: dict[str, Any],
    *,
    repair_attempted: bool,
    repair_succeeded: bool,
) -> dict[str, Any]:
    has_title = bool(
        str(writing.get("post_title") or "").strip()
        if isinstance(writing, dict)
        else ""
    )
    has_body = bool(
        str(writing.get("post_body") or "").strip() if isinstance(writing, dict) else ""
    )
    required = _writing_plan_requires_post_text(action_plan)
    meta: dict[str, Any] = {
        "required_post_text": required,
        "has_post_title": has_title,
        "has_post_body": has_body,
        "repair_attempted": repair_attempted,
        "repair_succeeded": repair_succeeded,
    }
    if required and not (has_title and has_body):
        meta["failure_class"] = _PERSONA_WRITER_MISSING_POST_TEXT
    return meta


def _persona_writer_has_required_post_text(
    action_plan: dict[str, Any], writing: dict[str, Any]
) -> bool:
    meta = _persona_writer_validation_meta(
        action_plan,
        writing,
        repair_attempted=False,
        repair_succeeded=False,
    )
    if not meta["required_post_text"]:
        return True
    return bool(meta["has_post_title"] and meta["has_post_body"])


def _with_persona_writer_validation(
    action_plan: dict[str, Any],
    writing: dict[str, Any],
    *,
    repair_attempted: bool,
    repair_succeeded: bool,
) -> dict[str, Any]:
    result = dict(writing) if isinstance(writing, dict) else {}
    result["persona_writer_validation"] = _persona_writer_validation_meta(
        action_plan,
        result,
        repair_attempted=repair_attempted,
        repair_succeeded=repair_succeeded,
    )
    return result
