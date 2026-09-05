"""Post writer plan defaults, task matching and validated result assembly."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.domains.routines.contracts.planning_context import ClipContextText
from app.domains.routines.policies.writing_contract import (
    _with_persona_writer_validation,
)

_POST_WRITER_PLAN_CONSTRAINTS = [
    "Do not change the selected post_task topic, mode, action, or brief.",
    "Use current_time_reference and arc_continuity_context to keep time framing coherent.",
    "Treat topic_arc.active_step as continuation intent, not wording to copy.",
    "For delayed gaps, acknowledge elapsed time without pretending the previous action is happening now.",
    "Use carryover_time_context for today/future event framing when present.",
    "Do not expose topic-arc structure labels such as standalone, setup, development, or conclusion.",
    "Use character_lore_context only as private reference material.",
    "Do not copy character_lore_context sentences verbatim.",
    "Do not expose lore_chunk_id, retrieval_mode, lore_query_mode, or source filenames.",
]


def _clean_lore_chunk_ids(value: Any, *, clip: ClipContextText) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in ids:
            ids.append(clip(text, 80))
    return ids[:5]


def _dedupe_clipped_items(
    items: Iterable[Any], *, max_items: int, max_chars: int, clip: ClipContextText
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        clipped = clip(item, max_chars)
        if not clipped or clipped in seen:
            continue
        result.append(clipped)
        seen.add(clipped)
        if len(result) >= max_items:
            break
    return result


def _post_writer_plan_defaults(
    post_task: dict[str, Any], *, clip: ClipContextText
) -> dict[str, Any]:
    active_step = post_task.get("active_step")
    active_step_brief = (
        str(active_step.get("brief") or "").strip()
        if isinstance(active_step, dict)
        else ""
    )
    continuity_context = post_task.get("arc_continuity_context")
    continuity_mode = (
        str(continuity_context.get("continuity_mode") or "").strip()
        if isinstance(continuity_context, dict)
        else ""
    )
    carryover_context = post_task.get("carryover_time_context")
    carryover_phase = (
        str(carryover_context.get("phase") or "").strip()
        if isinstance(carryover_context, dict)
        else ""
    )
    carryover_label = (
        str(carryover_context.get("label") or "").strip()
        if isinstance(carryover_context, dict)
        else ""
    )
    brief = str(post_task.get("brief") or "").strip()
    topic_focus = clip(active_step_brief or brief or post_task.get("topic_key"), 400)
    time_framing = clip(
        carryover_label
        or carryover_phase
        or continuity_mode
        or post_task.get("current_time_reference")
        or "Use current_time_reference for final framing.",
        160,
    )
    body_beats = _dedupe_clipped_items(
        (
            active_step_brief,
            brief,
            topic_focus,
            carryover_label,
            "Adapt relative time words to current_time_reference.",
            "Keep lore private and avoid metadata leakage.",
        ),
        max_items=5,
        max_chars=300,
        clip=clip,
    )
    return {
        "time_framing": time_framing,
        "topic_focus": topic_focus,
        "title_direction": "Write a concise public title for the selected topic.",
        "body_beats": body_beats,
        "tone_notes": "Follow persona and established speech style.",
        "constraints": list(_POST_WRITER_PLAN_CONSTRAINTS),
    }


def _mandatory_post_writer_constraints(
    raw_constraints: Iterable[Any], *, clip: ClipContextText
) -> list[str]:
    return _dedupe_clipped_items(
        [*raw_constraints, *_POST_WRITER_PLAN_CONSTRAINTS],
        max_items=9,
        max_chars=240,
        clip=clip,
    )


def _post_writer_plan_result(
    *,
    status: str,
    task_id_matched: bool,
    fallback_used: bool,
    error: dict[str, Any] | None = None,
    validation_summary: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": status,
        "task_id_matched": task_id_matched,
        "fallback_used": fallback_used,
        "failure_class": None,
        "parse_error_type": None,
        "attempt_count": None,
        "validation_summary": validation_summary,
    }
    if error:
        result["failure_class"] = error.get("failure_class")
        result["parse_error_type"] = error.get("parse_error_type")
        result["attempt_count"] = error.get("attempt_count")
        result["validation_summary"] = error.get("validation_summary")
        result["json_error_diagnostics"] = error.get("json_error_diagnostics")
    return result


def _fallback_post_writer_plan(
    post_task: dict[str, Any],
    *,
    status: str,
    error: dict[str, Any] | None = None,
    validation_summary: list[dict[str, Any]] | None = None,
    clip: ClipContextText,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_task_id = str(post_task.get("task_id") or "").strip()
    defaults = _post_writer_plan_defaults(post_task, clip=clip)
    plan = {
        "task_id": expected_task_id or None,
        "time_framing": defaults["time_framing"],
        "topic_focus": defaults["topic_focus"],
        "title_direction": defaults["title_direction"],
        "body_beats": defaults["body_beats"],
        "tone_notes": defaults["tone_notes"],
        "constraints": defaults["constraints"],
        "status": status,
        "fallback_used": True,
    }
    return plan, _post_writer_plan_result(
        status=status,
        task_id_matched=True,
        fallback_used=True,
        error=error,
        validation_summary=validation_summary,
    )


def _normalize_post_writer_plan(
    output: dict[str, Any], post_task: dict[str, Any], *, clip: ClipContextText
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_task_id = str(post_task.get("task_id") or "").strip()
    returned_task_id = str(output.get("task_id") or "").strip()
    if returned_task_id != expected_task_id:
        validation_summary = [
            {
                "path": "task_id",
                "type": "task_id_mismatch",
                "message": "PostWriterPlanner returned a different task_id.",
            }
        ]
        plan, result = _fallback_post_writer_plan(
            post_task,
            status="fallback_task_id_mismatch",
            validation_summary=validation_summary,
            clip=clip,
        )
        result["task_id_matched"] = False
        return plan, result
    defaults = _post_writer_plan_defaults(post_task, clip=clip)
    body_beats = _dedupe_clipped_items(
        output.get("body_beats", []), max_items=5, max_chars=300, clip=clip
    ) or list(defaults["body_beats"])
    plan = {
        "task_id": expected_task_id,
        "time_framing": clip(output.get("time_framing"), 160)
        or defaults["time_framing"],
        "topic_focus": clip(output.get("topic_focus"), 400) or defaults["topic_focus"],
        "title_direction": clip(output.get("title_direction"), 240)
        or defaults["title_direction"],
        "body_beats": body_beats,
        "tone_notes": clip(output.get("tone_notes"), 300) or defaults["tone_notes"],
        "constraints": _mandatory_post_writer_constraints(
            output.get("constraints", []), clip=clip
        ),
        "status": "succeeded",
        "fallback_used": False,
    }
    return plan, _post_writer_plan_result(
        status="succeeded",
        task_id_matched=True,
        fallback_used=False,
    )


def _post_identity_for_prompt(post_task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": post_task.get("task_id"),
        "mode": post_task.get("mode"),
        "topic_key": post_task.get("topic_key"),
        "source_post_id": post_task.get("source_post_id"),
        "feed_cue_id": post_task.get("feed_cue_id"),
        "relationship_point_id": post_task.get("relationship_point_id"),
        "source_mix": post_task.get("source_mix"),
        "mention_required": post_task.get("mention_required"),
        "mention_target_handle": post_task.get("mention_target_handle"),
        "writing_form": post_task.get("writing_form"),
        "action_step_count": post_task.get("action_step_count"),
    }


def _apply_post_writer_output(
    action_plan: dict[str, Any],
    writing: dict[str, Any],
    post_task: dict[str, Any],
    output: dict[str, Any],
    *,
    repair_attempted: bool,
    writer_node: str,
    clip: ClipContextText,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = dict(writing) if isinstance(writing, dict) else {}
    expected_task_id = str(post_task.get("task_id") or "")
    returned_task_id = (
        str(output.get("task_id") or "").strip() if isinstance(output, dict) else ""
    )
    title = (
        str(output.get("post_title") or "").strip() if isinstance(output, dict) else ""
    )
    body = (
        str(output.get("post_body") or "").strip() if isinstance(output, dict) else ""
    )
    matched = returned_task_id == expected_task_id and bool(title and body)
    if matched:
        result["post_title"] = title
        result["post_body"] = body
        lore_chunk_ids = _clean_lore_chunk_ids(
            post_task.get("lore_chunk_ids"), clip=clip
        )
        retrieval_mode = clip(post_task.get("retrieval_mode"), 80) or None
        lore_query_mode = clip(post_task.get("lore_query_mode"), 80) or None
        if lore_chunk_ids:
            result["lore_chunk_ids"] = lore_chunk_ids
        if retrieval_mode:
            result["retrieval_mode"] = retrieval_mode
        if lore_query_mode:
            result["lore_query_mode"] = lore_query_mode
    result["post_task_result"] = {
        "task_id": expected_task_id,
        "returned_task_id": returned_task_id or None,
        "post_title": title,
        "post_body": body,
        "writer_node": writer_node,
        "repair_attempted": repair_attempted,
        "repair_succeeded": repair_attempted and matched,
        "task_id_matched": returned_task_id == expected_task_id,
        "lore_chunk_ids": _clean_lore_chunk_ids(
            post_task.get("lore_chunk_ids"), clip=clip
        ),
        "retrieval_mode": clip(post_task.get("retrieval_mode"), 80) or None,
        "lore_query_mode": clip(post_task.get("lore_query_mode"), 80) or None,
    }
    result = _with_persona_writer_validation(
        action_plan,
        result,
        repair_attempted=repair_attempted,
        repair_succeeded=matched,
    )
    writer_result = {
        "writer_node": writer_node,
        "task_id": expected_task_id,
        "returned_task_id": returned_task_id or None,
        "written": matched,
        "repair_attempted": repair_attempted,
    }
    return result, writer_result
